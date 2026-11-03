"""Run logs, the result table, ``--json`` and the progress line (design doc 9.2, 9.3).

Port of macOS ``update_report_begin``, ``update_report_record``,
``update_report_warnings``, ``print_update_report`` and the progress part of
``run_with_heartbeat``. Field names in the saved run file and in ``--json``
are the macOS ones; this runtime adds ``platform`` at the top level and
``channel`` per tool.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import secrets
import string
import sys
import textwrap
import threading
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, TextIO, Tuple

from aiup.errors import AiupError
from aiup.paths import ensure_dir, refuse_symlink
from aiup.versions import scheme_for, version_cmp

from aiup.engine.cache import atomic_write_json, remove_quietly
from aiup.engine.context import RunLog

if TYPE_CHECKING:
    from aiup.engine.context import Context

RUN_SCHEMA = "aiup-run-v1"
CHECK_SCHEMA = "aiup-check-v1"

ORDER = ("failed", "downgraded", "updated", "installed", "cleaned", "deferred", "cancelled", "pending",
         "skipped", "unverified", "planned", "update", "self-updated", "current", "unchanged")

CATEGORY_COLORS: Mapping[str, str] = {
    "updates": "38;5;82", "infra": "38;5;39", "coding-agents": "38;5;171",
    "community-agents": "38;5;165", "agent-tools": "38;5;177", "orchestrators": "38;5;207",
    "workspaces": "38;5;219", "editors": "38;5;111", "terminals": "38;5;81", "mcp": "38;5;141",
    "sandboxes": "38;5;109", "chat": "38;5;51", "browsers": "38;5;45", "local-apps": "38;5;85",
    "voice": "38;5;204", "image-gen": "38;5;199", "media": "38;5;213", "media-tools": "38;5;175",
    "automation": "38;5;184", "dev-utils": "38;5;75", "local-ai": "38;5;48", "llm-utils": "38;5;208",
    "adapters": "38;5;220", "detected": "38;5;250",
}
DEFAULT_CATEGORY_COLOR = "38;5;250"

INTERRUPTED_NOTE = "Interrupted. aiup resume runs it again."

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# An epoch ("1:2.3-1") and "~" / "^" belong to pacman, dpkg and rpm versions.
_VERSION_IN_TEXT = re.compile(r"(?:\d+:)?\d+\.\d+[^\s]*")
_KNOWN_VERSION = re.compile(r"(?:v?\d[0-9A-Za-z._,+:~^-]*|r\d+)")
_LOG_CHARS = string.ascii_letters + string.digits


def clean(text: object) -> str:
    """Text without escape sequences or control characters."""
    return _CONTROL.sub("", _ANSI.sub("", str(text)))


def version_text(text: str) -> str:
    """The version inside a ``--version`` line, else the cleaned text."""
    value = clean(text)
    match = _VERSION_IN_TEXT.search(value)
    return match.group(0) if match else value


def category_color(category: str) -> str:
    """The ANSI color for a category's tool names."""
    return CATEGORY_COLORS.get(category.split("/", 1)[0], DEFAULT_CATEGORY_COLOR)


@dataclass
class Row:
    """One tool in a report."""

    tool: str
    result: str
    before: str = ""
    after: str = ""
    note: str = ""
    warning: bool = False
    duration: int = 0
    start: int = 0
    end: int = 0
    category: str = ""
    channel: str = ""


def remap(result: str, before: str, after: str, scheme: str = "generic") -> str:
    """macOS ``print_update_report``: a finished change becomes what actually happened.

    ``scheme`` is the version order of the channel that made the change.
    """
    if result not in ("completed", "current"):
        return result
    if before == "not installed" and _KNOWN_VERSION.fullmatch(after):
        return "installed"
    if _KNOWN_VERSION.fullmatch(before) and _KNOWN_VERSION.fullmatch(after):
        if before == after:
            return "unchanged"
        return "downgraded" if version_cmp(after, before, scheme) < 0 else "updated"
    return "unverified"


# ----- warnings in a tool's part of the log ------------------------------------------

_WARN_LINE = re.compile(r"\s*(?:==>\s*)?(?:npm\s+)?(?:warn(?:ing)?\b|error\b|err!)", re.I)
_WARN_IGNORE = re.compile(r"already installed|not upgrading|not linked because \S+ is already linked", re.I)
_ALLOW_SCRIPTS_NOTICE = re.compile(
    r"(?m)^.*allow-scripts setting is being ignored because --allow-scripts was passed.*\n?")
_HELD_SCRIPTS = re.compile(r"install-scripts\s+(@?[^@\s]+)@\S+\s+\(")
_UNNEEDED_SCRIPTS = ("@google/genai", "protobufjs")


def log_warning(path: Path, start: int, end: int, tool: str) -> str:
    """The warning note for one tool's part of the log, or "" (``update_report_warnings``)."""
    if end <= start:
        return ""
    try:
        with open(path, "rb") as handle:
            handle.seek(start)
            text = handle.read(min(end - start, 8 * 1024 * 1024)).decode("utf-8", "replace")
    except OSError:
        return ""
    return warning_from_text(_ANSI.sub("", text), tool)


def warning_from_text(text: str, tool: str) -> str:
    """The warning rules on already-cleaned log text."""
    text = _ALLOW_SCRIPTS_NOTICE.sub("", text)
    lines = [line.strip() for line in text.splitlines()
             if _WARN_LINE.match(line) and not _WARN_IGNORE.search(line)]
    if not lines:
        return ""
    held = list(dict.fromkeys(_HELD_SCRIPTS.findall(text)))
    unneeded = [name for name in held if name in _UNNEEDED_SCRIPTS]
    held = [name for name in held if name not in _UNNEEDED_SCRIPTS]
    reviewed_only = bool(unneeded) and not held
    if reviewed_only:
        lines = [line for line in lines if "install-scripts" not in line]
        if not lines:
            return ""
    if held:
        more = " and more" if len(held) > 4 else ""
        return ("npm held back install scripts for " + ", ".join(held[:4]) + more
                + " (its default protection); if " + tool + " misbehaves, aiup logs " + tool
                + " shows how to allow them.")
    lowered = text.lower()
    if not reviewed_only and ("install-scripts" in text or ("blocked" in lowered and "script" in lowered)):
        return ("Setup scripts need review; installation may be incomplete. Run aiup logs "
                + tool + " for details.")
    return "; ".join(dict.fromkeys(lines))[:400]


# ----- the report -------------------------------------------------------------------


@dataclass
class Report:
    """One update run or check: its log, its rows and how they are shown."""

    ctx: "Context"
    mode: str                                   # "update" | "check"
    log_path: Optional[Path] = None
    started: float = field(default_factory=time.time)
    rows: "OrderedDict[str, Row]" = field(default_factory=OrderedDict)
    interrupted: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def log(self) -> RunLog:
        """The run log sink."""
        return self.ctx.log

    def seconds(self) -> int:
        """Whole seconds since the run started."""
        return int(time.time() - self.started)

    def log_size(self) -> int:
        """Bytes in the run log so far."""
        if self.log_path is None:
            return 0
        try:
            return self.log_path.stat().st_size
        except OSError:
            return 0

    # ----- rows ------------------------------------------------------------------

    def begin(self, rows: Sequence[Row]) -> None:
        """Every tool starts as ``pending`` / "Not started" (update runs save at once)."""
        with self._lock:
            for row in rows:
                if self.mode == "update" and not row.result:
                    row.result, row.note, row.after = "pending", "Not started", row.before
                self.rows[row.tool] = row
        self.save()

    def record(self, row: Row) -> None:
        """Store a finished tool and save the run file (``update_report_record``)."""
        row.before = clean(row.before).replace("\t", " ")
        row.after = clean(row.after).replace("\t", " ")
        row.note = clean(row.note).replace("\t", " ")
        if self.ctx.dry_run and self.mode == "update":
            # Only a change that would run is "planned"; skipped, held, deferred
            # and failed tools keep their result and note.
            if row.result == "completed":
                row.result = "planned"
            row.warning = False
        if self.mode == "update":
            row.result = remap(row.result, version_text(row.before), version_text(row.after),
                               scheme_for(row.channel))
        with self._lock:
            self.rows[row.tool] = row
        self.save()

    def counts(self) -> "OrderedDict[str, int]":
        """Results counted, in the macOS order."""
        counted = Counter(row.result for row in self.rows.values())
        ordered = sorted(counted, key=lambda s: ORDER.index(s) if s in ORDER else len(ORDER))
        return OrderedDict((state, counted[state]) for state in ordered)

    # ----- files -----------------------------------------------------------------

    def save(self, final: bool = False) -> None:
        """Write ``<log>.json`` (update runs only). Never raises."""
        if self.mode != "update" or self.log_path is None:
            return
        with self._lock:
            tools = [{"tool": r.tool, "result": r.result, "before": version_text(r.before),
                      "after": version_text(r.after), "note": r.note, "start": r.start, "end": r.end,
                      "warning": bool(r.warning), "duration": r.duration, "channel": r.channel}
                     for r in self.rows.values()]
        data = {"schema": RUN_SCHEMA, "platform": self.ctx.os_name, "started": self.started,
                "duration": self.seconds(), "status": "complete" if final else "running",
                "log": self.log_path.name, "tools": tools}
        try:
            atomic_write_json(Path(str(self.log_path) + ".json"), data)
        except (OSError, ValueError, AiupError):
            pass

    def close(self) -> None:
        """Final save, drop the ``.active`` marker, prune old runs."""
        self.save(final=True)
        if self.log_path is not None:
            remove_quietly(Path(str(self.log_path) + ".active"))
        if self.mode == "update" and not self.ctx.dry_run:
            from aiup.engine.history import prune

            prune(self.ctx)

    # ----- output ------------------------------------------------------------------

    def json_document(self) -> Dict[str, object]:
        """The ``--json`` document."""
        update = self.mode == "update"
        tools: List[Dict[str, object]] = []
        for r in self.rows.values():
            item: Dict[str, object] = {"tool": r.tool, "result": r.result}
            item["before" if update else "installed"] = version_text(r.before)
            item["after" if update else "latest"] = version_text(r.after)
            item["note"] = r.note
            item["warning"] = bool(r.warning)
            if update:
                item["duration"] = r.duration
            item["channel"] = r.channel
            tools.append(item)
        doc: Dict[str, object] = {
            "schema": RUN_SCHEMA if update else CHECK_SCHEMA, "mode": self.mode,
            "platform": self.ctx.os_name, "duration": self.seconds(),
            "interrupted": self.interrupted, "counts": dict(self.counts()), "tools": tools,
        }
        if update and self.log_path is not None:
            doc["log"] = str(self.log_path)
        return doc

    def print_json(self, out: Optional[TextIO] = None) -> None:
        """Write the JSON document to the context's JSON stream (the real stdout in --json mode)."""
        stream = out or self.ctx.json_out or sys.stdout
        json.dump(self.json_document(), stream, indent=2)
        stream.write("\n")
        stream.flush()

    def print_table(self, show_all: bool = False, out: Optional[TextIO] = None) -> None:
        """The result table (macOS ``print_update_report``)."""
        stream = out or sys.stdout
        for line in table_lines(self, show_all, _color_on(self.ctx, stream), _width(stream)):
            stream.write(line + "\n")
        stream.flush()


def _color_on(ctx: "Context", stream: TextIO) -> bool:
    if ctx.config.no_color:
        return False
    try:
        from aiup.platform import term

        return bool(term.color_enabled(stream))
    except ImportError:
        return _isatty(stream)


def _isatty(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def _width(stream: TextIO) -> int:
    if not _isatty(stream):
        return 80
    try:
        from aiup.platform import term

        columns = term.columns()
    except ImportError:
        columns = 80
    return max(30, min(columns, 140))


def _ink(color: bool, text: str, code: str) -> str:
    return "\033[" + code + "m" + text + "\033[0m" if color else text


def _versions(row: Row) -> str:
    before, after = version_text(row.before), version_text(row.after)
    if row.result == "planned":
        return before
    return before + " → " + after if before != after and after else (after or before)


def _status_code(status: str) -> str:
    if status in ("failed", "unverified", "downgraded"):
        return "38;5;203"
    if status in ("skipped", "planned", "deferred", "cancelled"):
        return "38;5;220"
    if status in ("updated", "installed", "update", "cleaned"):
        return "38;2;57;255;20"
    return "38;5;245"


def _quiet(row: Row) -> bool:
    return ((row.result == "unchanged" and not row.warning and not row.note)
            or (row.result == "self-updated" and not row.warning) or row.result == "pending")


def table_lines(report: Report, show_all: bool, color: bool, width: int) -> List[str]:
    """Lines of the result table. Narrow terminals (under 76 columns) stack each row."""
    mode, rows, counts = report.mode, list(report.rows.values()), report.counts()
    hidden = not_started = 0
    visible = rows
    if mode == "update" and not show_all:
        visible = [r for r in rows if not _quiet(r)]
        hidden = sum(1 for r in rows if _quiet(r) and r.result != "pending")
        not_started = counts.get("pending", 0)
    warnings = sum(1 for r in rows if r.warning)
    out: List[str] = ["", _ink(color, "  aiup · " + ("update check" if mode == "check" else "results"), "1;38;5;141")]
    summary = " · ".join(str(n) + " " + state for state, n in counts.items()) + " · " + str(report.seconds()) + "s"
    out.extend(_ink(color, "  " + part, "38;5;245") for part in textwrap.wrap(summary, width - 4))
    if warnings:
        out.append(_ink(color, "  " + str(warnings) + (" tool needs" if warnings == 1 else " tools need")
                        + " a look (marked !)", "38;5;220"))
    rule = _ink(color, "  " + "─" * (width - 4), "38;5;60")
    out.append(rule)
    tool_width = min(32, max(19, max((len(r.tool) + 2 for r in rows), default=19)))
    wide = width >= 76
    if wide:
        out.append(_ink(color, "  " + "TOOL".ljust(tool_width) + "RESULT".ljust(13) + "VERSION", "38;5;81"))
    for row in visible:
        out.extend(_row_lines(mode, row, color, width, tool_width, wide))
    out.append(rule)
    plural = (lambda n: "tool" if n == 1 else "tools")
    if hidden:
        out.append(_ink(color, "  " + str(hidden) + " current " + plural(hidden)
                        + " hidden · --show-unchanged lists them", "38;5;245"))
    if not_started:
        out.append(_ink(color, "  " + str(not_started) + " " + plural(not_started)
                        + " not started (run interrupted)", "38;5;220"))
    if mode == "update":
        steps: List[str] = []
        if any(r.result in ("failed", "deferred", "cancelled", "pending") for r in rows):
            steps.append("aiup resume")
        if warnings or counts.get("downgraded"):
            steps.append("aiup attention")
        if steps:
            out.extend(_ink(color, "  " + part, "38;5;81")
                       for part in textwrap.wrap("Next: " + " · ".join(steps), width - 4))
        if report.log_path is not None:
            out.append(_ink(color, "  Run log: " + str(report.log_path), "38;5;245"))
    else:
        out.append(_ink(color, "  Read-only check · no tools changed", "38;5;245"))
    return out


def _row_lines(mode: str, row: Row, color: bool, width: int, tool_width: int, wide: bool) -> List[str]:
    lines: List[str] = []
    versions = _versions(row)
    if mode == "update":
        versions += " · " + str(row.duration) + "s"
    status = row.result + (" !" if row.warning else "")
    code = _status_code(row.result)
    name_code = category_color(row.category) if row.category else DEFAULT_CATEGORY_COLOR
    display = row.tool
    if wide and len(row.tool) >= tool_width:
        lines.extend("  " + _ink(color, part, name_code) for part in textwrap.wrap(row.tool, width - 4))
        display = ""
    if wide:
        name = _ink(color, display.ljust(tool_width), name_code)
        parts = textwrap.wrap(versions, max(12, width - tool_width - 17)) or ["unknown"]
        lines.append("  " + name + _ink(color, status.ljust(13), code) + parts[0])
        lines.extend(" " * (tool_width + 15) + part for part in parts[1:])
    else:
        lines.append("  " + _ink(color, row.tool, name_code) + "  " + _ink(color, status, code))
        lines.extend("      " + part for part in textwrap.wrap(versions, width - 6))
    if row.note:
        lines.extend(_ink(color, "      " + part, "38;5;220") for part in textwrap.wrap(row.note, width - 6))
    return lines


# ----- opening a run ------------------------------------------------------------------


def logs_dir(ctx: "Context") -> Path:
    """``<state>/logs``, created private; a symbolic link is refused."""
    folder = ctx.dirs.state / "logs"
    refuse_symlink(folder)
    ensure_dir(folder)
    return folder


def open_report(ctx: "Context", mode: str) -> Report:
    """Start a report. Update runs get a new private log and a ``.active`` marker."""
    report = Report(ctx=ctx, mode=mode)
    if mode == "update":
        from aiup.engine.history import prune

        prune(ctx)
        report.log_path = _new_log(logs_dir(ctx))
        _write_private(Path(str(report.log_path) + ".active"), str(os.getpid()) + "\n")
        ctx.log = RunLog(report.log_path)
    print_header(ctx)
    return report


def _new_log(folder: Path) -> Path:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for _ in range(20):
        name = "update-" + stamp + "." + "".join(secrets.choice(_LOG_CHARS) for _ in range(6))
        path = folder / name
        try:
            _write_private(path, "", exclusive=True)
            return path
        except FileExistsError:
            continue
    raise OSError("could not create a run log in " + str(folder))


def _write_private(path: Path, text: str, exclusive: bool = False) -> None:
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    fd = os.open(str(path), flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


def print_header(ctx: "Context") -> None:
    """``aiup · tool operations`` (stderr)."""
    stream = ctx.out
    if _isatty(stream) and not ctx.config.no_color:
        ctx.say("\n\033[1;38;5;141m  aiup\033[0m \033[38;5;81m· tool operations\033[0m\n")
    else:
        ctx.say("\naiup · tool operations\n")


# ----- progress line -----------------------------------------------------------------


class Progress:
    """The ``[i/N] tool · Ns elapsed`` line, and the visible sudo prompt.

    While a sudo runs anywhere under aiup the line reads "sudo password:" and
    is not redrawn, so sudo's own prompt stays readable (macOS 2026.10.23-01).
    """

    def __init__(self, ctx: "Context", report: Report, total: int) -> None:
        self.ctx = ctx
        self.report = report
        self.total = total
        self.done = 0
        self.tool = ""
        self.live = (_isatty(ctx.out) and not ctx.verbose and not ctx.config.no_color)
        self._sudo_shown = False
        self._last_beat = 0.0
        self._lock = threading.Lock()

    def label(self) -> str:
        """``[3/40] tool`` with the tool cut to 24 characters."""
        if self.done < self.total:
            return "[{}/{}] {}".format(self.done + 1, self.total, self.tool[:24])
        return self.tool[:24]

    def start(self, tool: str) -> None:
        """A tool begins."""
        with self._lock:
            self.tool = tool
            self._sudo_shown = False
            self._last_beat = time.monotonic()
            if self.live:
                self._draw("{} · {}s elapsed".format(self.label(), self.report.seconds()))
            else:
                self.ctx.say("  [{}/{}] {}".format(self.done + 1, self.total, tool))

    def finish(self) -> None:
        """A tool ended: clear the line."""
        with self._lock:
            self.done += 1
            if self.live:
                self._draw("", prefix="")
            self._sudo_shown = False

    def tick(self, step_label: str, elapsed: float) -> None:
        """Called about once a second while a step runs."""
        now = time.monotonic()
        if now - self._last_beat < self.ctx.config.heartbeat_seconds:
            return
        self._last_beat = now
        self.report.log.write("still working: {} ({}s elapsed)".format(step_label, int(elapsed)))
        if not self.live:
            return
        from aiup.engine import host

        with self._lock:
            if host.sudo_running_under(self.ctx.platform, os.getpid()):
                if not self._sudo_shown:
                    self._draw("{} · sudo password: ".format(self.label()))
                self._sudo_shown = True
            else:
                self._sudo_shown = False
                self._draw("{} · {}s elapsed".format(self.label(), self.report.seconds()))

    def clear(self) -> None:
        """Clear the progress line before aiup asks a question."""
        with self._lock:
            if self.live:
                self._draw("", prefix="")

    def note(self, text: str) -> None:
        """Print a line above the progress line."""
        with self._lock:
            if self.live:
                self._draw("", prefix="")
            self.ctx.say(text)

    def _draw(self, text: str, prefix: str = "  ") -> None:
        try:
            self.ctx.out.write("\r\033[2K" + (prefix + text if text else ""))
            self.ctx.out.flush()
        except (OSError, ValueError):
            pass


def row_for(tool: str, category: str, channel: str, before: str) -> Row:
    """A fresh row before a tool runs."""
    return Row(tool=tool, result="", before=before or "not installed", after=before or "not installed",
               category=category, channel=channel)


def run_paths(log_path: Path) -> Tuple[Path, Path]:
    """``<log>.json`` and ``<log>.active``."""
    return Path(str(log_path) + ".json"), Path(str(log_path) + ".active")
