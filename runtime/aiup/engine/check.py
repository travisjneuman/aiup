"""``aiup check`` and the check data ``aiup plan`` and ``aiup notify`` read (port of macOS ``cmd_check``).

Read-only: installed versions, then the newest version each tool's active
channel offers (design doc section 6). Results are ``update``, ``current``,
``self-updated``, ``unverified``, ``skipped`` and ``absent``. Without named
tools only installed tools are listed, plus the package extras a plain run
updates (``pkg:`` ids), so the check matches the run. The table (or ``--json``) goes to
stdout, then the "Newer on another channel" hints (stderr) and what's new for
the tools with an update.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

from aiup.errors import AiupError
from aiup.model import PENDING_UPDATE_NOTE, CatalogEntry

from aiup.engine import host
from aiup.engine.channels import (Resolution, channel_hints, channel_label, find_copies, load_choices,
                                  print_channel_hints)
from aiup.engine.latest import classify, prefetch_outdated, read_latest, self_updated_note
from aiup.engine.plan import Job, installed_ids, plan_note, resolve_jobs
from aiup.engine.prefs import IdRules, load_preferences
from aiup.engine.report import Row, open_report, row_for

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.engine.context import Context

EXIT_OK = 0
EXIT_INTERRUPTED = 130

NO_SOURCE_NOTE = "No read-only release source for this tool yet. A normal run still updates it."
NO_ANSWER_NOTE = ("The latest release could not be read just now, so this is not confirmed current. "
                  "A normal run still updates it.")
NO_VERSION_NOTE = "The installed version could not be read. A normal run still updates it."
NONE_INSTALLED = "No installed catalog tools found."
UNKNOWN_VERSION = "unknown"


@dataclass
class CheckItem:
    """One checked tool: its row and the planning record behind it."""

    job: Job
    row: Row


def check_items(ctx: "Context", catalog: "Catalog", tools: Sequence[str]) -> List[CheckItem]:
    """Check data for the named tools, or for what a plain run updates when none are named.

    Unknown names raise :class:`AiupError` (macOS ``resolve_tools``). Never
    changes a tool. Ctrl-C propagates.
    """
    names = _names(ctx, catalog, tools)
    prefs = load_preferences(ctx.dirs, IdRules(catalog.ids()))
    jobs = resolve_jobs(ctx, catalog, names, "update", False, prefs, load_choices(ctx), installed_only=not tools)
    for job in jobs:
        if job.resolution is None and job.entry is not None and job.status == "skipped":
            _fill_skipped(ctx, job)
    readable = [job for job in jobs if job.status == "run" and job.provider is not None]
    prefetch_outdated(ctx, {job.provider.name: job.provider for job in readable
                            if job.provider is not None}.values())
    if readable:
        workers = max(1, min(len(readable), ctx.config.check_workers))
        host.map_threads(workers, lambda job: _read_latest(ctx, job), readable)
    if not tools:
        jobs = [job for job in jobs if job.before != "not installed"]
    return [CheckItem(job, _row(job)) for job in jobs]


def _fill_skipped(ctx: "Context", job: Job) -> None:
    """The installed version of a tool preferences skip, read without resolving a channel."""
    entry = job.entry
    if entry is None:
        return
    try:
        copies = find_copies(entry, ctx)
    except (OSError, ValueError):
        return
    if copies:
        job.before = copies[0][1].version or "unknown"


def _names(ctx: "Context", catalog: "Catalog", tools: Sequence[str]) -> List[str]:
    if not tools:
        return installed_ids(ctx, catalog)
    found: List[str] = []
    for name in tools:
        tool = catalog.resolve(name)
        if tool is None:
            raise AiupError("Unknown tool: " + name)
        found.append(tool)
    return found


def _current(job: Job) -> str:
    """The installed version a check compares: the active copy, else the first copy found."""
    if job.installed is not None:
        return job.installed.version
    if job.resolution is not None and job.resolution.installed:
        return job.resolution.installed[0][1].version
    return ""


def _read_latest(ctx: "Context", job: Job) -> None:
    provider, target = job.provider, job.target
    if provider is None or target is None:
        return
    job.latest = read_latest(ctx, provider, target, job.tool, _current(job))


def _row(job: Job) -> Row:
    """The check row for one resolved job."""
    row = row_for(job.tool, job.category, job.channel, job.before)
    if job.status != "run":
        _settled(job, row)
        return row
    current = _current(job)
    latest = job.latest
    kind = classify(current, latest)
    row.result = kind
    if kind == "update" and latest is not None:
        row.after = latest.version or UNKNOWN_VERSION
        if not latest.version:
            row.note = latest.unverified_reason or PENDING_UPDATE_NOTE
    elif kind == "skipped" and latest is not None:
        row.after = ""
        row.note = latest.managed
    elif kind == "self-updated" and latest is not None:
        row.note = self_updated_note(current, channel_label(job.channel), latest.version)
    elif kind == "unverified":
        row.note = _unverified_note(current, latest.unverified_reason if latest is not None else "")
    moving = plan_note(job)
    if moving:
        row.note = (row.note + " " + moving).strip()
    return row


def _settled(job: Job, row: Row) -> None:
    """Rows for tools the plan stopped before reading versions."""
    res = job.resolution
    if job.status == "skipped" and res is not None and res.active is not None and not res.installed:
        row.result, row.note = "absent", "Install explicitly with: aiup only " + job.tool
    elif job.status == "failed":
        # A provider that is missing here: the check cannot read it.
        row.result, row.note = "unverified", job.note
    else:
        row.result, row.note = "skipped", job.note


def _unverified_note(current: str, reason: str) -> str:
    if not current or current == "unknown":
        return NO_VERSION_NOTE
    if reason.endswith("cannot read versions yet"):
        return NO_SOURCE_NOTE
    return NO_ANSWER_NOTE


def run_check(ctx: "Context", catalog: "Catalog", tools: Sequence[str], show_all: bool = False) -> int:
    """``aiup check [tools...]``. Returns 0 when the check ran, 130 after Ctrl-C."""
    report = open_report(ctx, "check")
    ctx.say("  Reading installed versions…")
    try:
        items = check_items(ctx, catalog, tools)
    except KeyboardInterrupt:
        report.interrupted = True
        report.close()
        ctx.say("")
        return EXIT_INTERRUPTED
    except BaseException:
        report.close()
        raise
    if not items and not ctx.json_output:
        report.close()
        print(NONE_INSTALLED)
        return EXIT_OK
    report.begin([item.row for item in items])
    report.close()
    if ctx.json_output:
        report.print_json()
        return EXIT_OK
    report.print_table(show_all)
    _hints(ctx, items)
    updates = [(item.row.tool, item.row.after) for item in items
               if item.row.result == "update" and item.row.after != UNKNOWN_VERSION]
    if updates:
        from aiup.engine.releasenotes import print_release_notes

        print_release_notes(ctx, catalog, updates)
    return EXIT_OK


def _hints(ctx: "Context", items: Sequence[CheckItem]) -> None:
    work: List[Tuple[CatalogEntry, Resolution, str]] = []
    for item in items:
        job = item.job
        latest = job.latest
        if job.entry is not None and job.resolution is not None and latest is not None and latest.version:
            work.append((job.entry, job.resolution, latest.version))
    if not work:
        return
    try:
        print_channel_hints(ctx, channel_hints(ctx, work, load_choices(ctx).policy))
    except (OSError, ValueError, AiupError):
        pass


def update_rows(items: Sequence[CheckItem]) -> List[Row]:
    """Rows with a newer version (``aiup notify`` and ``aiup plan``)."""
    return [item.row for item in items if item.row.result == "update"]


def find_item(items: Sequence[CheckItem], tool: str) -> Optional[CheckItem]:
    """The checked item for one tool id."""
    for item in items:
        if item.job.tool == tool:
            return item
    return None
