"""Run one planned job: live check, steps, verify, retire old copies (port of macOS ``run_tool_update``).

Every step goes through :mod:`aiup.engine.privilege` first. A step that may
not run defers the tool with the reason; nothing is elevated without the
rules there. Script steps download their installer into a private folder
first and remove it afterwards. The installed version is read live before
and after the change (macOS ``mutation_authoritative_preflight``); caches are
never trusted for a mutation.

Provider hooks used here: ``lock_held`` before any step, ``explain_exit``
for every finished step, ``forget`` after every step that ran. An action
without steps is never a success (``plan.empty_result``).
"""

from __future__ import annotations

import os
import secrets
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Iterator, List, Optional, Sequence, Set, Tuple

from aiup.errors import AiupError
from aiup.model import Installed, Step, Target
from aiup.paths import ensure_dir, private_mkdir, refuse_symlink

from aiup.engine import host
from aiup.engine.channels import Copy, channel_label, hook_for, retire_label, write_method
from aiup.engine.lanes import Gate, Sink
from aiup.engine.latest import forget
from aiup.engine.net import NetError
from aiup.engine.plan import Job, empty_result, plan_note
from aiup.engine.privilege import (NEEDS_TERMINAL, SUDO_NEEDS_TERMINAL, PrivilegeDecision, confirm_step, decide,
                                   sudo_password_refused, wrapped_argv)
from aiup.engine.report import INTERRUPTED_NOTE, Row, log_warning, row_for

if TYPE_CHECKING:
    from aiup.engine.context import Context
    from aiup.engine.report import Progress, Report
    from aiup.providers.base import Provider

FILE_PLACEHOLDER = "{file}"
# What a provider's explain_exit may turn a failed step into ("" keeps failed).
EXIT_RESULTS = frozenset({"failed", "deferred", "cancelled", "skipped", "unchanged", "self-updated"})
METADATA_TTL = 900.0
STEP_GRACE = 5.0


@dataclass
class RunState:
    """What every job of one run shares."""

    ctx: "Context"
    report: "Report"
    progress: Optional["Progress"]
    cancel: threading.Event = field(default_factory=threading.Event)
    gate: Gate = field(default_factory=Gate)
    upgraded: Set[str] = field(default_factory=set)     # non-targeted providers already run
    refreshed: Set[str] = field(default_factory=set)    # metadata refreshed this run
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def interrupted(self) -> bool:
        """True once Ctrl-C was pressed."""
        return self.cancel.is_set()


@dataclass(frozen=True)
class Outcome:
    """How a job or a list of steps ended."""

    result: str          # completed | failed | deferred | cancelled | skipped | ok, or a provider's exit reading
    note: str = ""       # with "ok": notes the steps left (a restart is needed ...)
    after: str = ""


_OK = Outcome("ok")


def failure_note(label: str, detail: str, tool: str) -> str:
    """``Failed: npm install -g x (exit 1). aiup logs x shows the output.``"""
    return "Failed: {} ({}). aiup logs {} shows the output.".format(label, detail, tool)


# ----- one job ----------------------------------------------------------------------


def skipped_row(job: Job) -> Row:
    """The row for a job the plan already settled (skipped, current, deferred ...)."""
    row = row_for(job.tool, job.category, job.channel, job.before)
    row.result = "current" if job.status == "current" else job.status
    row.note = job.note
    if job.status == "self-updated":
        row.after = job.before
    return row


def execute_job(state: RunState, job: Job, sink: Sink, in_lane: bool) -> Row:
    """Run one planned job and return its finished row (not yet recorded)."""
    row = row_for(job.tool, job.category, job.channel, job.before)
    row.start = sink.size()
    began = time.monotonic()
    sink.log.write("========== TOOL START: " + job.tool + " ==========")
    try:
        outcome, before = _work(state, job, sink, in_lane)
    except KeyboardInterrupt:
        state.cancel.set()
        outcome, before = Outcome("cancelled", INTERRUPTED_NOTE), job.before
    row.before = before
    row.after = outcome.after or before
    row.result = outcome.result
    row.note = _join(plan_note(job), outcome.note) if outcome.result == "completed" else outcome.note
    marker = {"completed": "DONE", "cancelled": "INTERRUPTED"}.get(outcome.result, outcome.result.upper())
    sink.log.write("========== TOOL " + marker + ": " + job.tool + " ==========")
    row.end = sink.size()
    row.duration = int(time.monotonic() - began)
    warning = log_warning(sink.path, row.start, row.end, job.tool) if outcome.result != "cancelled" else ""
    if warning:
        row.warning = True
        row.note = _join(row.note, warning)
    return row


def _join(*parts: str) -> str:
    return " ".join(part for part in parts if part)


def _work(state: RunState, job: Job, sink: Sink, in_lane: bool) -> Tuple[Outcome, str]:
    """(outcome, version before)."""
    ctx, provider, target, action = state.ctx, job.provider, job.target, job.action
    if provider is None or target is None or action is None:
        return Outcome("failed", job.note or "Nothing planned."), job.before
    live = _installed(ctx, provider, target)
    before = (live.version or "unknown") if live is not None else job.before
    if job.op == "update" and live is None:
        again = "." if job.package else "; aiup only " + job.tool + " installs it again."
        return Outcome("skipped", "No longer installed through " + channel_label(target.channel) + again), job.before
    held = lock_note(ctx, provider)
    if held:
        return Outcome("deferred", held), before
    if not provider.targeted_update and _already_upgraded(state, provider):
        after = _installed(ctx, provider, target)
        return Outcome("completed", "Updated by this run's full system upgrade.",
                       after.version if after is not None else before), before
    refreshed = _refresh(state, job, provider, sink, in_lane)
    if refreshed.result in ("deferred", "cancelled"):
        return refreshed, before
    retire_first = hook_for(job.tool).retire_first and bool(job.retire)
    if retire_first:
        removed = retire_copies(state, job, job.retire, sink, in_lane)
        if removed.result != "ok":
            note = removed.note or ("Could not remove the copy from " + retire_label(job.retire)
                                    + "; nothing was installed.")
            return Outcome(_result_of(removed), note), before
    ran = run_steps(state, job.tool, provider, action.steps, job.op, job.explicit, sink, in_lane)
    if ran.result != "ok":
        return ran, before
    if not provider.targeted_update:
        with state.lock:
            state.upgraded.add(provider.name)
    done = _after_success(state, job, provider, target, sink, in_lane, retire_first)
    if ran.note:
        done = Outcome(done.result, _join(done.note, ran.note), done.after)
    return done, before


def _result_of(outcome: Outcome) -> str:
    return "failed" if outcome.result == "ok" else outcome.result


def _after_success(state: RunState, job: Job, provider: "Provider", target: Target, sink: Sink,
                   in_lane: bool, retired: bool) -> Outcome:
    ctx = state.ctx
    if ctx.dry_run:
        return Outcome("completed", "", job.before)
    after = _installed(ctx, provider, target)
    if after is None:
        return Outcome("failed", job.tool + " is not found after the " + job.op + ".")
    if not job.package:
        # Install methods are kept per catalog tool; a package's manager is part of its id.
        write_method(ctx, job.tool, target.channel)
    forget(ctx, job.tool, target.channel)
    note = ""
    if job.retire and not retired:
        removed = retire_copies(state, job, job.retire, sink, in_lane)
        if removed.result == "ok":
            note = "Removed the copy from " + retire_label(job.retire) + "."
        elif removed.result == "cancelled":
            note = "Installed; Ctrl-C stopped the removal of the copy from " + retire_label(job.retire) + "."
        else:
            note = ("Installed; could not remove the copy from " + retire_label(job.retire)
                    + ". aiup logs " + job.tool + " shows why.")
    return Outcome("completed", note, after.version or "unknown")


def _installed(ctx: "Context", provider: "Provider", target: Target) -> Optional[Installed]:
    try:
        return provider.installed(ctx, target)
    except (OSError, ValueError, NotImplementedError):
        return None


def lock_note(ctx: "Context", provider: "Provider") -> str:
    """A provider's "another manager is running" note (``Provider.lock_held``), or ""."""
    check: Optional[Callable[["Context"], str]] = getattr(provider, "lock_held", None)
    if check is None:
        return ""
    try:
        return str(check(ctx) or "")
    except (OSError, ValueError):
        return ""


def _already_upgraded(state: RunState, provider: "Provider") -> bool:
    with state.lock:
        return provider.name in state.upgraded


# ----- metadata refresh (once per manager per run, at most every 15 minutes) -----------


def _refresh(state: RunState, job: Job, provider: "Provider", sink: Sink, in_lane: bool) -> Outcome:
    ctx = state.ctx
    stamps = ctx.cache.metadata
    with state.lock:
        if provider.name in state.refreshed:
            return _OK
        state.refreshed.add(provider.name)
    if not ctx.refresh and stamps.fresh(provider.name, METADATA_TTL):
        return _OK
    try:
        action = provider.metadata_refresh(ctx)
    except (NotImplementedError, OSError, ValueError):
        return _OK
    if action is None or not action.steps:
        return _OK
    ran = run_steps(state, job.tool, provider, action.steps, "update", job.explicit, sink, in_lane)
    if ran.result == "ok" and not ctx.dry_run:
        stamps.touch(provider.name)
    if ran.result == "failed":
        sink.log.write("Metadata refresh failed for " + provider.name + "; going on with the cached lists.")
        return _OK
    return ran


# ----- retiring old copies ------------------------------------------------------------


def retire_copies(state: RunState, job: Job, copies: Sequence[Copy], sink: Sink, in_lane: bool) -> Outcome:
    """Remove each old copy with its own manager's remove action."""
    ctx = state.ctx
    for target, installed in copies:
        provider = ctx.provider(target.channel)
        if provider is None:
            return Outcome("failed", channel_label(target.channel) + " is not available to remove the old copy.")
        try:
            action = provider.remove(ctx, target)
        except (NotImplementedError, OSError, ValueError) as exc:
            return Outcome("failed", "Could not plan the removal from " + channel_label(target.channel)
                           + ": " + str(exc)[:160])
        sink.log.write("Removing the copy from " + channel_label(target.channel)
                       + (" at " + installed.path if installed.path else ""))
        if not action.steps:
            # Never counted as removed: the copy is still there.
            note = action.note or "nothing to run"
            sink.log.write("NOT REMOVED: " + note)
            return Outcome(empty_result(action), "The copy from " + channel_label(target.channel)
                           + " stays: " + note)
        held = lock_note(ctx, provider)
        if held:
            return Outcome("deferred", held)
        ran = run_steps(state, job.tool, provider, action.steps, "remove", job.explicit, sink, in_lane)
        if ran.result != "ok":
            return ran
    return _OK


# ----- steps ----------------------------------------------------------------------------


def run_steps(state: RunState, tool: str, provider: "Provider", steps: Sequence[Step], op: str,
              explicit: bool, sink: Sink, in_lane: bool) -> Outcome:
    """Run steps in order. ``on_fail="next"`` makes the following step a fallback.

    When a step with ``on_fail="next"`` fails, the next step runs; when it
    works, the fallbacks that follow it are skipped (one for a single
    ``"next"``, the whole chain for ``next, next, ...``). A step with
    ``confirm`` asks its question first; no (the default) skips the action,
    no terminal defers it. Returns ``ok`` (with any notes the steps left), or
    the failed, deferred, skipped or cancelled outcome.
    """
    index, count = 0, len(steps)
    notes: List[str] = []
    while index < count:
        if state.interrupted:
            return Outcome("cancelled", INTERRUPTED_NOTE)
        step = steps[index]
        decision = decide(step, provider, op, explicit, state.ctx, tool)
        if not decision.allowed:
            sink.log.write("DEFERRED: " + step.label + ": " + decision.defer_note)
            return Outcome("deferred", decision.defer_note)
        if in_lane and (decision.wrap or step.interactive or step.privilege != "none" or step.confirm):
            # Lanes never prompt; lane_for keeps such jobs in the main lane.
            return Outcome("deferred", NEEDS_TERMINAL)
        if step.confirm:
            refused = _confirm(state, step, sink)
            if refused is not None:
                return refused
        outcome = run_one(state, tool, step, decision, sink, in_lane, provider, op)
        if outcome.result == "ok":
            if outcome.note:
                notes.append(outcome.note)
            index += 1
            while index < count and steps[index - 1].on_fail == "next":
                index += 1
            continue
        if outcome.result == "failed" and step.on_fail == "next" and index + 1 < count:
            sink.log.write("Trying the next way: " + steps[index + 1].label)
            index += 1
            continue
        return outcome
    return Outcome("ok", _join(*dict.fromkeys(notes))) if notes else _OK


def _confirm(state: RunState, step: Step, sink: Sink) -> Optional[Outcome]:
    """Ask a step's own question. None when the answer is yes."""
    if state.progress is not None and not state.ctx.dry_run:
        state.progress.clear()
    answer = confirm_step(state.ctx, step.confirm)
    if answer == "yes":
        if state.ctx.dry_run:
            sink.log.write("DRY-RUN: would ask: " + step.confirm)
        return None
    if answer == "no-terminal":
        sink.log.write("DEFERRED: " + step.label + ": needs a yes in a terminal: " + step.confirm)
        return Outcome("deferred", "aiup asks first (" + step.confirm + "); run aiup in a terminal")
    sink.log.write("SKIPPED: " + step.label + ": answered no to: " + step.confirm)
    return Outcome("skipped", "Answered no to: " + step.confirm + " Nothing changed.")


def run_one(state: RunState, tool: str, step: Step, decision: PrivilegeDecision, sink: Sink,
            in_lane: bool, provider: Optional["Provider"] = None, op: str = "") -> Outcome:
    """Run one allowed step: download its script if any, run it logged, read the result."""
    ctx = state.ctx
    argv, env = wrapped_argv(decision, step)
    if ctx.dry_run:
        line = "DRY-RUN: " + step.label
        sink.log.write(line)
        if ctx.verbose:
            ctx.say("  " + line)
        return _OK
    folder: Optional[Path] = None
    try:
        if step.download:
            try:
                folder, path = download_installer(ctx, step.download)
            except (NetError, OSError, AiupError) as exc:
                sink.log.write("FAILED: download " + step.download + ": " + str(exc)[:300])
                return Outcome("failed", failure_note("download " + step.download, "no installer", tool))
            argv = tuple(str(path) if part == FILE_PLACEHOLDER else part for part in argv)
        return _launch(state, tool, step, decision, argv, env, sink, in_lane, provider, op)
    finally:
        if folder is not None:
            shutil.rmtree(str(folder), ignore_errors=True)


def _launch(state: RunState, tool: str, step: Step, decision: PrivilegeDecision, argv: Tuple[str, ...],
            env: Dict[str, str], sink: Sink, in_lane: bool, provider: Optional["Provider"] = None,
            op: str = "") -> Outcome:
    ctx = state.ctx
    sink.log.write("START: " + step.label)
    progress = None if in_lane else state.progress
    on_tick: Optional[Callable[[float], None]] = None
    if progress is not None:
        on_tick = lambda elapsed: progress.tick(step.label, elapsed)  # noqa: E731
    with _hold(state, step, decision, in_lane) as allowed:
        if not allowed:
            return Outcome("cancelled", INTERRUPTED_NOTE)
        try:
            result = host.run_step(argv, sink.path, echo=sys.stderr if ctx.verbose and not in_lane else None,
                                   timeout=step.timeout, env=env or None, interactive=step.interactive,
                                   cancel=state.cancel, on_tick=on_tick, grace=STEP_GRACE,
                                   stdout_to_stderr=ctx.json_output)
        finally:
            forget_provider(provider)
    if result.interrupted or (in_lane and state.interrupted and not result.ok(step.ok_codes)):
        state.cancel.set()
        sink.log.write("INTERRUPTED: " + step.label)
        return Outcome("cancelled", INTERRUPTED_NOTE)
    meaning = _explain(provider, op, result.returncode if not result.timed_out and not result.error else None)
    if result.ok(step.ok_codes):
        sink.log.write("DONE: " + step.label + (" (" + meaning[1] + ")" if meaning and meaning[1] else ""))
        return Outcome("ok", meaning[1]) if meaning and meaning[1] else _OK
    helper = step.privilege == "helper-sudo" and not ctx.interactive
    if sudo_password_refused(decision.wrap, result.tail, helper):
        sink.log.write("DEFERRED: " + step.label + ": sudo needs a password and there is no terminal")
        return Outcome("deferred", SUDO_NEEDS_TERMINAL)
    if step.privilege == "polkit" and not ctx.interactive and _polkit_refused(result.tail):
        sink.log.write("DEFERRED: " + step.label + ": polkit needs approval and there is no terminal")
        return Outcome("deferred", NEEDS_TERMINAL)
    detail = _detail(result.returncode, result.timed_out, result.error)
    sink.log.write("FAILED: " + step.label + " (" + detail + ")" + (": " + result.error if result.error else ""))
    if meaning is not None:
        kind, note = meaning
        if kind and kind != "failed":
            sink.log.write("aiup reads " + detail + " as " + kind + (": " + note if note else ""))
            return Outcome(kind, note)
        if note:
            return Outcome("failed", "Failed: {} ({}: {}). aiup logs {} shows the output.".format(
                step.label, detail, note, tool))
    return Outcome("failed", failure_note(step.label, detail, tool))


_POLKIT_MARKERS = ("not authorized", "org.freedesktop.flatpak", "polkit", "authentication is required")


def _polkit_refused(tail: Tuple[str, ...]) -> bool:
    """True when the output says polkit could not ask for approval (flatpak --noninteractive)."""
    text = "\n".join(tail).lower()
    return any(marker in text for marker in _POLKIT_MARKERS)


def _explain(provider: Optional["Provider"], op: str, code: Optional[int]) -> Optional[Tuple[str, str]]:
    """A provider's ``(result, note)`` for an exit status (``Provider.explain_exit``), or None."""
    if provider is None or code is None or code == 0:
        return None
    try:
        meaning = provider.explain_exit(op, code)
    except (AttributeError, NotImplementedError, ValueError):
        return None
    if meaning is None or len(meaning) != 2:
        return None
    kind, note = str(meaning[0] or ""), str(meaning[1] or "")
    return (kind if kind in EXIT_RESULTS else ""), note


def forget_provider(provider: Optional["Provider"]) -> None:
    """Drop a provider's cached reads after a step that may have changed something."""
    if provider is None:
        return
    try:
        provider.forget()
    except (AttributeError, NotImplementedError, OSError, ValueError):
        pass


def _detail(code: Optional[int], timed_out: bool, error: str) -> str:
    if timed_out:
        return "timed out"
    if error or code is None:
        return "could not start"
    return "exit " + str(code)


@contextmanager
def _hold(state: RunState, step: Step, decision: PrivilegeDecision, in_lane: bool) -> Iterator[bool]:
    """Lane steps share the gate; a main step that may use the terminal takes it alone."""
    if in_lane:
        with state.gate.shared(state.cancel) as ok:
            yield ok
        return
    if uses_terminal(step, decision):
        with state.gate.exclusive():
            yield True
        return
    yield True


def uses_terminal(step: Step, decision: PrivilegeDecision) -> bool:
    """True when the step may prompt: interactive, sudo with a terminal, helper-sudo or a UAC prompt.

    helper-sudo steps run a helper (yay, paru) that calls sudo itself, so its
    password prompt needs the terminal too.
    """
    return (step.interactive or decision.wrap == ("sudo",)
            or step.privilege in ("uac-possible", "helper-sudo"))


def _new_private_folder(base: Path, prefix: str) -> Path:
    """A new, empty private folder under ``base`` (``tempfile.mkdtemp`` sets a Windows ACL)."""
    for _ in range(20):
        folder = base / (prefix + secrets.token_hex(8))
        try:
            private_mkdir(folder)
        except FileExistsError:
            continue
        return folder
    raise OSError("could not create a private folder in " + str(base))


def download_installer(ctx: "Context", url: str) -> Tuple[Path, Path]:
    """Download an install script into a new private folder. Returns (folder, file)."""
    base = ctx.dirs.cache / "downloads"
    refuse_symlink(base)
    ensure_dir(base)
    folder = _new_private_folder(base, "installer-")
    name = "installer.ps1" if ctx.os_name == "windows" else "installer.sh"
    path = folder / name
    try:
        ctx.net.download(url, path)
    except BaseException:
        shutil.rmtree(str(folder), ignore_errors=True)
        raise
    if os.name != "nt":
        os.chmod(str(path), 0o600)
    return folder, path
