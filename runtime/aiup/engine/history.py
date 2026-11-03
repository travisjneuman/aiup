"""Saved runs: history, logs, retry, resume, prune (port of macOS ``run_history``).

Runs live in ``<state>/logs`` as ``update-YYYYmmdd-HHMMSS.<rand>`` with
``.json`` (schema aiup-run-v1) and ``.active`` (pid of a running aiup).
A run whose aiup is still alive is never pruned. Liveness uses
``Platform.pid_alive``; aiup never sends a signal to check.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, TextIO, Tuple

from aiup.errors import AiupError

from aiup.engine import host
from aiup.engine.cache import read_text_bounded, remove_quietly

if TYPE_CHECKING:
    from aiup.engine.context import Context

_LOG_NAME = re.compile(r"update-\d{8}-\d{6}\.[A-Za-z0-9]+")
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_META_MAX_BYTES = 8 * 1024 * 1024
LEGACY_PROTECT_SECONDS = 86400

RESUME_RESULTS = ("failed", "pending", "deferred", "cancelled")
RETRY_RESULTS = ("failed", "deferred", "cancelled")


def plain(value: object) -> str:
    """Text safe to print: no escape sequences, no control characters."""
    return _CONTROL.sub("", _ANSI.sub("", str(value)))


@dataclass(frozen=True)
class RunRecord:
    """One saved run."""

    mtime: float
    log: Path
    meta: Path
    active: Path
    alive: bool
    data: Optional[Dict[str, object]]

    def tools(self) -> List[Dict[str, object]]:
        """The tool rows of the run file (empty for a legacy log)."""
        rows = self.data.get("tools") if self.data else None
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _logs_root(ctx: "Context") -> Path:
    root = ctx.dirs.state / "logs"
    if root.is_symlink():
        raise AiupError("Refusing a symbolic-link log directory")
    return root


def _alive(ctx: "Context", active: Path) -> bool:
    if not active.is_file():
        return False
    text = read_text_bounded(active, 64)
    try:
        pid = int((text or "").strip())
    except ValueError:
        return True  # unclear: keep the run
    return pid > 0 and host.pid_alive(ctx.platform, pid)


def _read_meta(meta: Path, log_name: str) -> Tuple[bool, Optional[Dict[str, object]]]:
    """(usable, data). A run file that does not match its log is skipped."""
    if not meta.is_file():
        return True, None
    text = read_text_bounded(meta, _META_MAX_BYTES)
    try:
        data = json.loads(text or "")
    except ValueError:
        return False, None
    if not isinstance(data, dict) or data.get("schema") != "aiup-run-v1" or data.get("log") != log_name:
        return False, None
    rows = data.get("tools")
    if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get("tool"), str) for r in rows):
        return False, None
    return True, data


def records(ctx: "Context") -> List[RunRecord]:
    """Saved runs, newest first."""
    root = _logs_root(ctx)
    if not root.is_dir():
        return []
    found: List[RunRecord] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return []
    for log in entries:
        if not _LOG_NAME.fullmatch(log.name) or log.is_symlink() or not log.is_file():
            continue
        meta, active = Path(str(log) + ".json"), Path(str(log) + ".active")
        if meta.is_symlink() or active.is_symlink():
            continue
        usable, data = _read_meta(meta, log.name)
        if not usable:
            continue
        try:
            mtime = log.stat().st_mtime
        except OSError:
            continue
        alive = _alive(ctx, active)
        # Older runtimes wrote no markers: protect a recent legacy log.
        if data is None and time.time() - mtime < LEGACY_PROTECT_SECONDS:
            alive = True
        found.append(RunRecord(mtime, log, meta, active, alive, data))
    found.sort(key=lambda r: (r.mtime, r.log.name), reverse=True)
    return found


def prune(ctx: "Context") -> None:
    """Keep the newest ``AIUP_LOG_LIMIT`` finished runs. Never raises."""
    try:
        runs = records(ctx)
    except AiupError:
        return
    finished = 0
    for run in runs:
        if run.alive:
            continue
        finished += 1
        if finished <= ctx.config.log_limit:
            continue
        for path in (run.meta, run.active, run.log):
            remove_quietly(path)
        lanes = Path(str(run.log) + ".lanes")
        if lanes.is_dir() and not lanes.is_symlink():
            try:
                for item in list(lanes.iterdir()):
                    remove_quietly(item)
                lanes.rmdir()
            except OSError:
                pass


def _selected(ctx: "Context", tool: str) -> List[RunRecord]:
    runs = records(ctx)
    if not tool:
        return runs
    return [r for r in runs if any(row.get("tool") == tool for row in r.tools())]


def _ink(text: str, code: str = "38;5;141", stream: Optional[TextIO] = None) -> str:
    out = stream or sys.stdout
    try:
        tty = out.isatty()
    except (AttributeError, ValueError, OSError):
        tty = False
    if tty and not os.environ.get("NO_COLOR"):
        return "\033[" + code + "m" + text + "\033[0m"
    return text


def tools_to_rerun(ctx: "Context", action: str) -> List[Tuple[str, str]]:
    """(tool, result) pairs for ``aiup resume`` or ``aiup retry``.

    Each tool's newest kept result decides, so a later partial run does not
    hide a tool an earlier run deferred or failed.
    """
    runs = _selected(ctx, "")
    if not runs:
        return []
    if runs[0].alive:
        raise AiupError("Latest run is still active; wait for it to finish")
    wanted = RESUME_RESULTS if action == "resume" else RETRY_RESULTS
    latest: Dict[str, str] = {}
    for run in runs:
        if run.alive or not run.data:
            continue
        for row in run.tools():
            name = row.get("tool")
            if isinstance(name, str) and name and name not in latest:
                latest[name] = str(row.get("result", ""))
    return [(tool, result) for tool, result in latest.items() if result in wanted]


def print_warnings(ctx: "Context") -> int:
    """Warnings recorded in the latest run (``aiup attention``)."""
    runs = _selected(ctx, "")
    rows = [r for r in runs[0].tools() if r.get("warning")] if runs and runs[0].data else []
    for row in rows:
        print("  ! " + plain(row.get("tool", "")) + ": " + plain(row.get("note", ""))
              + " · aiup logs " + plain(row.get("tool", "")))
    if not rows:
        print("  No recorded setup warnings in the latest run.")
    return 0


def latest_rows(ctx: "Context") -> List[Dict[str, object]]:
    """Tool rows of the newest finished run (for ``aiup attention``)."""
    for run in _selected(ctx, ""):
        if not run.alive and run.data:
            return run.tools()
    return []


def print_logs(ctx: "Context", tool: str = "") -> int:
    """The latest run log, or one tool's part of it (``aiup logs [TOOL]``)."""
    runs = _selected(ctx, tool)
    if not runs:
        print("No saved log for " + (tool or "an update run") + ".")
        return 1
    run = runs[0]
    try:
        start, end = 0, run.log.stat().st_size
    except OSError:
        print("No saved log for " + (tool or "an update run") + ".")
        return 1
    if tool:
        row = next((r for r in run.tools() if r.get("tool") == tool), {})
        start, end = _int(row.get("start")), _int(row.get("end"))
    try:
        print(_ink("Run log: " + str(run.log)))
        _copy_range(run.log, start, end)
        sys.stdout.flush()
    except BrokenPipeError:
        # The pager closed before the end of the log.
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass
    except OSError:
        print("Could not read the saved log " + plain(run.log.name) + ".")
        return 1
    return 0


def _copy_range(path: Path, start: int, end: int) -> None:
    with open(path, "rb") as handle:
        handle.seek(max(0, start))
        remaining = max(0, end - start)
        while remaining:
            raw = handle.read(min(65536, remaining))
            if not raw:
                break
            remaining -= len(raw)
            text = _ANSI.sub("", raw.decode("utf-8", "replace"))
            sys.stdout.write("".join(c for c in text if c in "\n\t" or (ord(c) >= 32 and not 127 <= ord(c) <= 159)))


def _int(value: object) -> int:
    try:
        return int(str(value))
    except ValueError:
        return 0


def print_history(ctx: "Context", tool: str = "") -> int:
    """``aiup history [TOOL]``."""
    root = _logs_root(ctx)
    if not root.is_dir():
        print("No saved runs yet.")
        return 0
    runs = _selected(ctx, tool)
    print(_ink("\naiup · history\n"))
    if not runs:
        print("No matching saved runs.")
    for run in runs[: ctx.config.log_limit]:
        print(_ink(plain(run.log.name), "38;5;81"))
        if not run.data:
            print("  Legacy log · aiup logs to read the latest run")
            continue
        rows = [r for r in run.tools() if not tool or r.get("tool") == tool]
        counts = Counter(str(r.get("result", "unknown")) for r in rows)
        status = "running" if run.alive else ("interrupted" if run.data.get("status") == "running" else "complete")
        print("  " + status + " · " + str(run.data.get("duration", 0)) + "s · "
              + " · ".join(str(n) + " " + plain(k) for k, n in counts.items()))
        for row in rows if tool else []:
            print("  " + _history_row(row))
    return 0


def _history_row(row: Dict[str, object]) -> str:
    before, after = row.get("before", "unknown"), row.get("after", "unknown")
    value = str(before) + " → " + str(after) if before != after else str(after)
    line = plain(row.get("tool", "")) + " · " + plain(value) + " · " + str(row.get("duration", 0)) + "s"
    return line + (" · ! warning" if row.get("warning") else "")


def print_cleanup_history(ctx: "Context") -> int:
    """``aiup cleanup history``: cleanups recorded in kept runs."""
    print(_ink("\naiup · cleanup history"))
    count = 0
    if _logs_root(ctx).is_dir():
        for run in _selected(ctx, "")[: ctx.config.log_limit]:
            for row in run.tools():
                if row.get("result") == "cleaned":
                    print("  " + plain(run.log.name) + " · " + plain(row.get("tool", "")) + " · " + plain(row.get("note", "")))
                    count += 1
    if not count:
        print("  No recorded cleanups in retained run history.")
    return 0


def tool_names(pairs: Sequence[Tuple[str, str]]) -> List[str]:
    """Just the tool ids of :func:`tools_to_rerun`."""
    return [tool for tool, _ in pairs]
