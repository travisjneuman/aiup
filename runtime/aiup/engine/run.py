"""Update runs, ``aiup system``, named removal and single package installs.

Ports macOS ``main_update`` and ``cmd_remove_named``. ``install_packages``
installs packages outside the catalog (``aiup import``) and ``run_actions``
runs prepared actions for packages and detected items (``aiup remove
pkg:...|det:...``), both through the same step runner, locks and log rules.

An update run: plan every tool, ask the one ``settings system`` question when
a system step needs it, run the main lane in order with parallel lanes beside
it, clean user-level caches, then show the table (or ``--json``) and the
"Newer on another channel" hints. What's new prints after ``check`` only, as on macOS.

Ctrl-C stops starting work and stops the lanes. The running tool becomes
``cancelled``, tools not reached stay ``pending``, the results still print,
and the exit code is 130. ``aiup resume`` picks them up.
"""

from __future__ import annotations

import datetime
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from aiup.errors import AiupError
from aiup.model import Action, Step, Target

from aiup.engine import cleanup, lanes
from aiup.engine.channels import channel_hints, channel_label, find_copies, load_choices, print_channel_hints
from aiup.engine.context import RunLog
from aiup.engine.execute import Outcome, RunState, execute_job, lock_note, run_steps, skipped_row
from aiup.engine.latest import forget
from aiup.engine.lanes import Lanes, Sink
from aiup.engine.plan import PACKAGE_PREFIX, Job, empty_result, installed_ids, plan_jobs
from aiup.engine.prefs import IdRules, load_preferences
from aiup.engine.privilege import (NEEDS_TERMINAL, ask_system, elevated_note, needs_question, root_refusal,
                                   shown_command)
from aiup.engine.report import INTERRUPTED_NOTE, Progress, Report, Row, logs_dir, open_report, row_for

from aiup.providers.base import Provider

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.engine.context import Context

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_INTERRUPTED = 130
FULL_UPGRADE_NOTE = "This runs a full system upgrade: "
REMOVE_LOG = "remove.log"
LOG_LIMIT = 1024 * 1024


@dataclass(frozen=True)
class RunRequest:
    """What the command asked for.

    ``explicit`` is True for ``only``, ``install`` and picker actions, and
    False for plain runs, ``resume`` and ``retry`` (section 7.5). Only an
    explicit request installs a missing tool.

    ``installed_only`` is the plain run: with no ``tools`` it plans every
    catalog tool offered here plus the package extras, reads each one's
    installed copies once, and leaves out what is not installed instead of
    listing it as skipped.
    """

    tools: Tuple[str, ...]
    op: str = "update"            # update | install
    explicit: bool = False
    show_unchanged: bool = False
    installed_only: bool = False


# ----- update runs -----------------------------------------------------------------


def run(ctx: "Context", catalog: "Catalog", request: RunRequest) -> int:
    """One update run. Returns the exit code (0, 1 or 130)."""
    _refuse_root(ctx)
    note = elevated_note(ctx)
    if note:
        ctx.say("  " + note)
    prefs = load_preferences(ctx.dirs, IdRules(catalog.ids()))
    choices = load_choices(ctx)
    report = open_report(ctx, "update")
    ctx.say("  Reading installed versions…")
    try:
        tools: Sequence[str] = request.tools
        if request.installed_only and not tools:
            tools = installed_ids(ctx, catalog)
        jobs = plan_jobs(ctx, catalog, tools, request.op, request.explicit, prefs, choices,
                         installed_only=request.installed_only)
    except KeyboardInterrupt:
        report.interrupted = True
        report.close()
        ctx.say("")
        return EXIT_INTERRUPTED
    except BaseException:
        report.close()
        raise
    report.begin([row_for(j.tool, j.category, j.channel, j.before) for j in jobs])
    for job in jobs:
        if job.status != "run":
            report.record(skipped_row(job))
    runnable = [job for job in jobs if job.status == "run"]
    state = RunState(ctx=ctx, report=report, progress=None)
    with _signals_as_interrupt():
        try:
            _approve(state, runnable)
            _run_all(state, runnable)
        except KeyboardInterrupt:
            state.cancel.set()
        except BaseException:
            report.close()
            raise
    return _finish(state, jobs, request)


def _refuse_root(ctx: "Context") -> None:
    refusal = root_refusal(ctx)
    if refusal:
        raise AiupError(refusal)


def _approve(state: RunState, jobs: Sequence[Job]) -> None:
    """Ask the one ``settings system ask`` question before any system step runs."""
    ctx = state.ctx
    commands: List[str] = []
    notes: List[str] = []
    refreshed: Dict[str, bool] = {}
    for job in jobs:
        provider, action = job.provider, job.action
        if provider is None or action is None:
            continue
        steps = list(action.steps)
        if provider.name not in refreshed:
            refreshed[provider.name] = True
            steps = _refresh_steps(ctx, provider) + steps
        for step in steps:
            if not needs_question(step, provider, job.op, job.explicit, ctx):
                continue
            command = shown_command(step, provider, ctx)
            if command not in commands:
                commands.append(command)
            if not provider.targeted_update:
                full = FULL_UPGRADE_NOTE + command
                if full not in notes:
                    notes.append(full)
    if commands:
        ask_system(ctx, commands, notes)


def _refresh_steps(ctx: "Context", provider: "Provider") -> List[Step]:
    try:
        action = provider.metadata_refresh(ctx)
    except (NotImplementedError, OSError, ValueError):
        return []
    return list(action.steps) if action is not None else []


def _run_all(state: RunState, jobs: Sequence[Job]) -> None:
    """Main lane in order, with the parallel lanes beside it (macOS ``main_update``)."""
    ctx, report = state.ctx, state.report
    log_path = report.log_path
    use_lanes = lanes.enabled(ctx, state.interrupted) and log_path is not None
    main, groups = lanes.split(jobs) if use_lanes else (list(jobs), {})
    state.progress = Progress(ctx, report, len(main))
    main_sink = Sink(log_path, ctx.log) if log_path is not None else None
    first = lanes.runtimes_first(main, groups) if groups else []
    first_ids = {id(job) for job in first}
    for job in first:
        if state.interrupted:
            return
        _run_main(state, job, main_sink)
    lane_set: Optional[Lanes] = None
    if groups and not state.interrupted and log_path is not None:
        lane_set = Lanes(ctx, log_path, state.cancel,
                         lambda job, sink, in_lane: execute_job(state, job, sink, in_lane))
        try:
            lane_set.start(groups)
        except (OSError, AiupError):
            # No lane folder: every job runs in the main lane instead.
            lane_set = None
            main = list(jobs)
            state.progress.total = len(main)
    later: List[Job] = []
    try:
        for job in main:
            if state.interrupted:
                break
            if id(job) in first_ids:
                continue
            if lane_set is not None and lanes.conflicts(job, lane_set.running):
                later.append(job)
                continue
            _run_main(state, job, main_sink)
    except KeyboardInterrupt:
        # Stop the lanes too, so the wait below does not run them to the end.
        state.cancel.set()
    finally:
        if lane_set is not None:
            _finish_lanes(state, lane_set)
    for job in later:
        if state.interrupted:
            break
        _run_main(state, job, main_sink)


def _run_main(state: RunState, job: Job, sink: Optional[Sink]) -> None:
    """One main-lane job with its progress line."""
    if sink is None:
        return
    progress = state.progress
    if progress is not None:
        progress.start(job.tool)
    start = sink.size()
    try:
        row = execute_job(state, job, sink, False)
    except KeyboardInterrupt:
        state.cancel.set()
        row = row_for(job.tool, job.category, job.channel, job.before)
        row.result, row.note = "cancelled", INTERRUPTED_NOTE
        row.start, row.end = start, sink.size()
    except Exception as exc:  # noqa: BLE001  one tool must not stop the run (as in a lane)
        row = row_for(job.tool, job.category, job.channel, job.before)
        row.start = start
        row.result = "failed"
        row.note = "Failed: " + type(exc).__name__ + ". aiup logs " + job.tool + " shows the output."
        sink.log.write("FAILED: " + job.tool + ": " + str(exc)[:300])
        row.end = sink.size()
    finally:
        if progress is not None:
            progress.finish()
    state.report.record(row)


def _finish_lanes(state: RunState, lane_set: Lanes) -> None:
    """Wait for the lanes, then record their tools in order (macOS ``lanes_finish``)."""
    if state.interrupted:
        state.cancel.set()
    names = lane_set.running
    if names and state.progress is not None:
        state.progress.note("  finishing the " + " and ".join(names) + " updates")
    for _, row in lane_set.finish():
        if state.interrupted and row.result == "failed":
            row.result, row.note = "cancelled", INTERRUPTED_NOTE
        state.report.record(row)


def _finish(state: RunState, jobs: Sequence[Job], request: RunRequest) -> int:
    """Cleanup, the report, hints and the exit code."""
    ctx, report = state.ctx, state.report
    freed = 0
    try:
        freed = cleanup.run_cleanup(ctx, lambda: state.interrupted)
    except KeyboardInterrupt:
        state.cancel.set()
    report.interrupted = state.interrupted
    report.close()
    if ctx.json_output:
        report.print_json()
    else:
        report.print_table(request.show_unchanged)
        line = cleanup.freed_line(freed)
        if line:
            ctx.say(line)
    if not state.interrupted and not ctx.json_output:
        _hints(ctx, jobs)
    if state.interrupted:
        return EXIT_INTERRUPTED
    failed = [row.tool for row in report.rows.values() if row.result == "failed"]
    if failed:
        sys.stderr.write("\nFailed tools: " + " ".join(failed) + "\n")
        return EXIT_FAILED
    return EXIT_OK


def _hints(ctx: "Context", jobs: Sequence[Job]) -> None:
    items = [(job.entry, job.resolution, job.latest.version) for job in jobs
             if job.entry is not None and job.resolution is not None and job.latest is not None
             and job.latest.version]
    if not items:
        return
    try:
        print_channel_hints(ctx, channel_hints(ctx, items, load_choices(ctx).policy))
    except (OSError, ValueError):
        pass


class _signals_as_interrupt:
    """SIGTERM and SIGHUP stop a run like Ctrl-C does (macOS ``trap ... INT TERM HUP``)."""

    def __init__(self) -> None:
        self._saved: List[Tuple[int, Any]] = []

    def __enter__(self) -> "_signals_as_interrupt":
        for name in ("SIGTERM", "SIGHUP"):
            number = getattr(signal, name, None)
            if number is None:
                continue
            try:
                self._saved.append((number, signal.signal(number, _raise_interrupt)))
            except (ValueError, OSError):
                pass  # not the main thread, or not allowed here
        return self

    def __exit__(self, *exc: object) -> None:
        for number, handler in self._saved:
            try:
                signal.signal(number, handler)
            except (ValueError, OSError, TypeError):
                pass


def _raise_interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


# ----- aiup system --------------------------------------------------------------------


def system_actions(ctx: "Context") -> List[Tuple["Provider", Action]]:
    """(provider, action) for each available system manager with a full upgrade.

    An action without steps (held, not configured ...) stays in the list so
    its row shows why; it never counts as updated.
    """
    found: List[Tuple["Provider", Action]] = []
    for provider in ctx.providers():
        try:
            action = provider.system_upgrade(ctx)
        except (NotImplementedError, OSError, ValueError):
            continue
        if action is not None:
            found.append((provider, action))
    return found


def run_system(ctx: "Context") -> int:
    """``aiup system``: each system manager's full upgrade, after one [y/N] question."""
    _refuse_root(ctx)
    actions = system_actions(ctx)
    if not actions:
        ctx.say("  No system package manager with a full upgrade was found here.")
        return EXIT_OK
    commands = [shown_command(step, provider, ctx) for provider, action in actions for step in action.steps]
    if commands and ctx.settings.system != "auto" and not ctx.dry_run:
        if not ctx.interactive:
            ctx.say("  aiup system " + NEEDS_TERMINAL + ".")
            return EXIT_FAILED
        if not ask_system(ctx, commands, ("This runs a full system upgrade.",), heading="aiup system runs:"):
            ctx.say("  Nothing changed.")
            return EXIT_OK
    ctx.system_approved = True
    report = open_report(ctx, "update")
    rows = [_system_row(provider) for provider, _ in actions]
    report.begin(rows)
    state = RunState(ctx=ctx, report=report, progress=Progress(ctx, report, len(actions)))
    sink = Sink(report.log_path, ctx.log) if report.log_path is not None else None
    with _signals_as_interrupt():
        try:
            for provider, action in actions:
                if state.interrupted or sink is None:
                    break
                _system_one(state, provider, action, sink)
        except KeyboardInterrupt:
            state.cancel.set()
    report.interrupted = state.interrupted
    report.close()
    upgraded = [provider for provider, _ in actions if _ran(report, provider)]
    if ctx.json_output:
        report.print_json()
    else:
        report.print_table(True)
    _system_notices(ctx, upgraded)
    if state.interrupted:
        return EXIT_INTERRUPTED
    return EXIT_FAILED if any(r.result == "failed" for r in report.rows.values()) else EXIT_OK


def _ran(report: Report, provider: "Provider") -> bool:
    """True when the manager's upgrade ran (worked or failed part way)."""
    row = report.rows.get(provider.name)
    return row is not None and row.result in ("updated", "failed")


def _system_one(state: RunState, provider: "Provider", action: Action, sink: Sink) -> None:
    row = _system_row(provider)
    row.start = sink.size()
    started = datetime.datetime.now()
    progress = state.progress
    if progress is not None:
        progress.start(provider.name)
    sink.log.write("========== TOOL START: " + provider.name + " ==========")
    try:
        outcome = _system_steps(state, provider, action, sink)
    except KeyboardInterrupt:
        state.cancel.set()
        outcome = None
    finally:
        if progress is not None:
            progress.finish()
    if outcome is None or outcome.result == "cancelled":
        row.result, row.note = "cancelled", INTERRUPTED_NOTE
    elif outcome.result == "ok":
        row.result = "planned" if state.ctx.dry_run else "updated"
        row.note = " ".join(part for part in (action.note, outcome.note) if part)
    else:
        row.result, row.note = outcome.result, outcome.note
    sink.log.write("========== TOOL DONE: " + provider.name + " ==========")
    row.end = sink.size()
    row.duration = int((datetime.datetime.now() - started).total_seconds())
    state.report.record(row)


def _system_steps(state: RunState, provider: "Provider", action: Action, sink: Sink) -> "Outcome":
    """The lock check, then the steps. An action without steps reports its own result."""
    if not action.steps:
        sink.log.write("NOT RUN: " + (action.note or "nothing to run"))
        return Outcome(empty_result(action), action.note or "Nothing to run.")
    held = lock_note(state.ctx, provider)
    if held:
        sink.log.write("DEFERRED: " + held)
        return Outcome("deferred", held)
    return run_steps(state, provider.name, provider, action.steps, "system", True, sink, False)


def _system_row(provider: "Provider") -> Row:
    """A row for one manager's full upgrade; it has no single version."""
    row = row_for(provider.name, "updates", provider.name, "")
    row.before = row.after = ""
    return row


def _system_notices(ctx: "Context", providers: Sequence["Provider"]) -> None:
    """Lines a manager wants shown after an upgrade (``Provider.notices``; pacman: new .pacnew files).

    They go to stderr, so they also show beside ``--json``. A dry run changes
    nothing, so it shows none.
    """
    if ctx.dry_run:
        return
    for provider in providers:
        try:
            lines = list(provider.notices(ctx))
        except (AttributeError, NotImplementedError, OSError, ValueError):
            continue
        for line in lines:
            if line:
                ctx.say("  " + str(line))


# ----- aiup remove TOOL ... -------------------------------------------------------------


def remove_tools(ctx: "Context", catalog: "Catalog", tools: Sequence[str]) -> int:
    """Uninstall every copy of each named tool with its own manager (macOS ``cmd_remove_named``).

    User data is left alone here; the remove command decides about it.
    Output goes to ``<state>/logs/remove.log``.
    """
    _refuse_root(ctx)
    log_path = _named_log(ctx, REMOVE_LOG, "aiup remove")
    ctx.log = RunLog(log_path)
    report = Report(ctx=ctx, mode="remove", log_path=log_path)
    state = RunState(ctx=ctx, report=report, progress=None)
    sink = Sink(log_path, ctx.log)
    code = EXIT_OK
    with _signals_as_interrupt():
        try:
            for name in tools:
                if state.interrupted:
                    break
                if not _remove_one(state, catalog, name, sink):
                    code = EXIT_FAILED
        except KeyboardInterrupt:
            state.cancel.set()
    if state.interrupted:
        ctx.say("  Interrupted; nothing else was removed.")
        return EXIT_INTERRUPTED
    if code != EXIT_OK:
        ctx.say("  Log: " + str(log_path))
    return code


def _remove_one(state: RunState, catalog: "Catalog", name: str, sink: Sink) -> bool:
    ctx = state.ctx
    entry = catalog.get(catalog.resolve(name) or name)
    if entry is None:
        ctx.say("  " + name + ": not in the catalog")
        return False
    copies = find_copies(entry, ctx)
    if not copies:
        ctx.say("  " + entry.id + ": not installed")
        return True
    ok = True
    sink.log.write("========== REMOVE START: " + entry.id + " ==========")
    for target, _ in copies:
        ok = _remove_copy(state, entry.id, target, sink) and ok
    sink.log.write("========== REMOVE DONE: " + entry.id + " ==========")
    return ok


def _remove_copy(state: RunState, tool: str, target: Target, sink: Sink) -> bool:
    ctx = state.ctx
    provider = ctx.provider(target.channel)
    where = channel_label(target.channel)
    if provider is None:
        ctx.say("  " + tool + ": " + where + " is not available here")
        return False
    try:
        action = provider.remove(ctx, target)
    except (NotImplementedError, OSError, ValueError) as exc:
        ctx.say("  " + tool + ": could not remove from " + where + ": " + str(exc)[:160])
        return False
    if not action.steps:
        # Never counted as removed: the provider held, refused or deferred it.
        result = empty_result(action)
        sink.log.write(tool + ": not removed from " + where + " (" + result + "): " + (action.note or "nothing to run"))
        ctx.say("  " + tool + ": not removed from " + where + (": " + action.note if action.note else ""))
        return False
    held = lock_note(ctx, provider)
    if held:
        ctx.say("  " + tool + ": not removed from " + where + ": " + held)
        return False
    outcome = run_steps(state, tool, provider, action.steps, "remove", True, sink, False)
    if outcome.result == "ok":
        verb = "Would remove" if ctx.dry_run else "Removed"
        if not ctx.dry_run:
            forget(ctx, tool, target.channel)
        notes = " · ".join(part for part in (action.note, outcome.note) if part)
        ctx.say("  " + verb + " " + tool + " from " + where + (" · " + notes if notes else ""))
        return True
    ctx.say("  " + tool + ": " + (outcome.note or "not removed from " + where))
    return False


# ----- single packages outside the catalog --------------------------------------------


class _OwnUninstaller(Provider):
    """Stands in for a provider when a detected app's own uninstaller runs (channel "arp").

    Privilege rules see a user-scope channel that updates one package at a
    time; ``uac-possible`` steps still need a desktop session or elevation.
    """

    name = "arp"
    oses = frozenset({"windows"})

    def available(self, ctx: "Context") -> bool:
        return False


def run_actions(ctx: "Context", actions: Sequence[Tuple[str, Action]], op: str = "remove",
                log_name: str = REMOVE_LOG, title: str = "aiup remove") -> int:
    """Run prepared actions (``(label, action)``) for items outside the catalog, as explicit requests.

    Each action's channel picks its provider; the "arp" channel is a detected
    app's own uninstaller. Returns 0, 1 or 130. Output goes to
    ``<state>/logs/<log_name>``.
    """
    if not actions:
        return EXIT_OK
    _refuse_root(ctx)
    log_path = _named_log(ctx, log_name, title)
    ctx.log = RunLog(log_path)
    state = RunState(ctx=ctx, report=Report(ctx=ctx, mode=op, log_path=log_path), progress=None)
    sink = Sink(log_path, ctx.log)
    code = EXIT_OK
    with _signals_as_interrupt():
        try:
            for label, action in actions:
                if state.interrupted:
                    break
                provider = _OwnUninstaller() if action.channel == "arp" else ctx.provider(action.channel)
                if provider is None:
                    ctx.say("  " + label + ": " + channel_label(action.channel) + " is not available here")
                    code = EXIT_FAILED
                    continue
                if not _run_action(state, label, provider, action, op, sink):
                    code = EXIT_FAILED
        except KeyboardInterrupt:
            state.cancel.set()
    if state.interrupted:
        ctx.say("  Interrupted; nothing else was changed.")
        return EXIT_INTERRUPTED
    if code != EXIT_OK:
        ctx.say("  Log: " + str(log_path))
    return code


_DONE = {"remove": ("Removed", "Would remove", "not removed"),
         "install": ("Installed", "Would install", "not installed"),
         "update": ("Updated", "Would update", "not updated")}


def _run_action(state: RunState, label: str, provider: "Provider", action: Action, op: str, sink: Sink,
                tool: str = "") -> bool:
    """One prepared action: the provider's lock, then its steps. True when it finished.

    ``label`` is what the lines show; ``tool`` (default ``label``) names it in the log and deferred notes.
    """
    ctx = state.ctx
    done, would, failed = _DONE.get(op, ("Done", "Would run", "not changed"))
    where = "its own uninstaller" if action.channel == "arp" else channel_label(action.channel)
    if not action.steps:
        ctx.say("  " + label + ": " + failed + " (" + empty_result(action) + ")"
                + (": " + action.note if action.note else ""))
        return False
    held = lock_note(ctx, provider)
    if held:
        ctx.say("  " + label + ": " + failed + ": " + held)
        return False
    sink.log.write("========== " + op.upper() + " START: " + label + " ==========")
    outcome = run_steps(state, tool or label, provider, action.steps, op, True, sink, False)
    sink.log.write("========== " + op.upper() + " DONE: " + label + " ==========")
    if outcome.result == "ok":
        notes = " · ".join(part for part in (action.note, outcome.note) if part)
        ctx.say("  " + (would if ctx.dry_run else done) + " " + label + " with " + where
                + (" · " + notes if notes else ""))
        return True
    ctx.say("  " + label + ": " + (outcome.note or failed + " with " + where))
    return False


def install_packages(ctx: "Context", packages: Sequence[Tuple[str, str]],
                     log_name: str = "import.log", title: str = "aiup import") -> Tuple[int, bool]:
    """Install each (manager, package) with its own manager, outside the catalog.

    Each install goes through the provider's install action, the manager's
    lock check and ``run_steps`` (privilege rules included) as an explicit
    request. Returns (failures, interrupted). Output goes to
    ``<state>/logs/<log_name>``.
    """
    if not packages:
        return 0, False
    _refuse_root(ctx)
    log_path = _named_log(ctx, log_name, title)
    ctx.log = RunLog(log_path)
    state = RunState(ctx=ctx, report=Report(ctx=ctx, mode="install", log_path=log_path), progress=None)
    sink = Sink(log_path, ctx.log)
    failed = 0
    with _signals_as_interrupt():
        try:
            for manager, name in packages:
                if state.interrupted:
                    break
                if not _install_one(state, manager, name, sink):
                    failed += 1
        except KeyboardInterrupt:
            state.cancel.set()
    if state.interrupted:
        ctx.say("  Interrupted; nothing else was installed.")
        return failed, True
    if failed:
        ctx.say("  Log: " + str(log_path))
    return failed, False


def _install_one(state: RunState, manager: str, name: str, sink: Sink) -> bool:
    ctx = state.ctx
    where = channel_label(manager)
    provider = ctx.provider(manager) if ctx.provider_available(manager) else None
    if provider is None:
        ctx.say("  " + name + ": " + where + " is not available here")
        return False
    try:
        action = provider.install(ctx, Target(channel=manager, package=name))
    except (NotImplementedError, OSError, ValueError) as exc:
        ctx.say("  " + name + ": could not install with " + where + ": " + str(exc)[:160])
        return False
    return _run_action(state, name, provider, action, "install", sink, PACKAGE_PREFIX + manager + ":" + name)


def _named_log(ctx: "Context", name: str, title: str) -> Path:
    """``<state>/logs/<name>``; the previous one moves to ``<name>.1`` past 1 MiB. Never a symbolic link."""
    path = logs_dir(ctx) / name
    try:
        if path.is_file() and not path.is_symlink() and path.stat().st_size > LOG_LIMIT:
            os.replace(str(path), str(path) + ".1")
    except OSError:
        pass
    if path.is_symlink():
        raise AiupError("Refusing a symbolic-link log file: " + str(path))
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    RunLog(path).write("---------- " + title + " " + stamp + " ----------")
    return path
