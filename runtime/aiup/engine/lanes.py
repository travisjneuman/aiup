"""Parallel lanes for user-level updates (design doc 9.1; macOS ``lanes_start``, ``lanes_finish``).

Jobs are grouped by ``Provider.lane``. Each lane (npm, python, rust, go,
brew, scoop, flatpak, nix) runs in its own thread, one tool at a time,
while the main lane goes on. A lane writes to ``<log>.lanes/<lane>``; when the
lanes finish, each tool's part is added to the run log in order, so the log
and the results look like a one-at-a-time run.

What stays in the main lane: exclusive providers (the system lane), any job
with a privileged or interactive step, jobs that retire copies, and jobs whose
tool is a lane's own runtime. A lane never prompts. The main lane takes the
:class:`Gate` alone for an interactive step, so lanes pause before it starts
and nothing runs beside it.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from aiup.paths import ensure_dir, refuse_symlink

from aiup.engine.cache import remove_quietly
from aiup.engine.context import RunLog
from aiup.engine.privilege import PRIVILEGED

if TYPE_CHECKING:
    from aiup.engine.context import Context
    from aiup.engine.plan import Job
    from aiup.engine.report import Row

# Tools that are a lane's own runtime run in the main lane first, so the lane
# uses the new version (macOS ``lanes_runtimes_first``).
LANE_RUNTIMES: Mapping[str, Tuple[str, ...]] = {
    "npm": ("node", "nodejs", "npm", "pnpm", "bun"),
    "python": ("uv", "python", "pipx"),
    "rust": ("rust", "rustup", "cargo"),
    "go": ("go",),
}
_WAIT_SLICE = 0.2

# Lanes that may run beside the main lane. Vendor installers and the
# system managers always run in the main lane.
PARALLEL_LANES = frozenset({"npm", "python", "rust", "go", "brew", "scoop", "flatpak", "nix"})


@dataclass
class Sink:
    """Where one job's output goes: a log file and its writer."""

    path: Path
    log: RunLog

    def size(self) -> int:
        """Bytes in the file so far."""
        try:
            return self.path.stat().st_size
        except OSError:
            return 0


class Gate:
    """Lane steps share the gate; a main-lane interactive step takes it alone.

    A waiting exclusive holder blocks new shared holders, so lanes pause
    before the interactive step instead of starving it.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._shared = 0
        self._exclusive = False
        self._waiting = 0

    @contextmanager
    def shared(self, cancel: threading.Event) -> Iterator[bool]:
        """Hold the gate beside other lane steps. Yields False when cancelled while waiting."""
        with self._cond:
            while (self._exclusive or self._waiting) and not cancel.is_set():
                self._cond.wait(_WAIT_SLICE)
            if cancel.is_set():
                ok = False
            else:
                self._shared += 1
                ok = True
        try:
            yield ok
        finally:
            if ok:
                with self._cond:
                    self._shared -= 1
                    self._cond.notify_all()

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        """Hold the gate alone: waits for running lane steps to end."""
        with self._cond:
            self._waiting += 1
            try:
                while self._exclusive or self._shared:
                    self._cond.wait(_WAIT_SLICE)
            finally:
                self._waiting -= 1
            self._exclusive = True
        try:
            yield
        finally:
            with self._cond:
                self._exclusive = False
                self._cond.notify_all()


def enabled(ctx: "Context", interrupted: bool) -> bool:
    """macOS ``lanes_enabled``: off with AIUP_PARALLEL=0, --verbose, --dry-run or after Ctrl-C."""
    return bool(ctx.config.parallel) and not ctx.verbose and not ctx.dry_run and not interrupted


def lane_for(job: "Job") -> str:
    """The lane a planned job may run in, or "main"."""
    if job.status != "run" or job.action is None or job.provider is None:
        return "main"
    lane = job.lane
    if lane not in PARALLEL_LANES or job.retire:
        return "main"
    if any(step.privilege in PRIVILEGED or step.interactive or step.confirm for step in job.action.steps):
        return "main"
    if job.tool in LANE_RUNTIMES.get(lane, ()):
        return "main"
    return lane


def split(jobs: Sequence["Job"]) -> Tuple[List["Job"], Dict[str, List["Job"]]]:
    """(main-lane jobs, lane name -> jobs), each in run order."""
    main: List["Job"] = []
    lanes: Dict[str, List["Job"]] = {}
    for job in jobs:
        lane = lane_for(job)
        if lane == "main":
            main.append(job)
        else:
            lanes.setdefault(lane, []).append(job)
    return main, lanes


def runtimes_first(main: Sequence["Job"], lanes: Mapping[str, Sequence["Job"]]) -> List["Job"]:
    """Main-lane jobs that must finish before the lanes start.

    A lane's runtime (node for npm, uv for python ...), and every full
    system upgrade, which may replace a runtime under a running lane.
    """
    wanted = {tool for lane in lanes for tool in LANE_RUNTIMES.get(lane, ())}
    first: List["Job"] = []
    for job in main:
        provider = job.provider
        full_upgrade = provider is not None and not provider.targeted_update and job.status == "run"
        if job.tool in wanted or full_upgrade:
            first.append(job)
    return first


def conflicts(job: "Job", running: Sequence[str]) -> bool:
    """True when a main-lane job uses a manager a running lane also uses."""
    if job.lane in running:
        return True
    for target, _ in job.retire:
        if target.channel in _LANE_CHANNELS.get_any(running):
            return True
    return False


class _LaneChannels:
    """Which channels belong to which lane, read from the providers once."""

    def __init__(self) -> None:
        self._map: Optional[Dict[str, Tuple[str, ...]]] = None

    def get_any(self, lanes: Sequence[str]) -> Tuple[str, ...]:
        if self._map is None:
            from aiup.engine import host

            found: Dict[str, List[str]] = {}
            for provider in host.all_providers():
                found.setdefault(provider.lane, []).append(provider.name)
            self._map = {lane: tuple(names) for lane, names in found.items()}
        out: List[str] = []
        for lane in lanes:
            out.extend(self._map.get(lane, ()))
        return tuple(out)


_LANE_CHANNELS = _LaneChannels()


Execute = Callable[["Job", Sink, bool], "Row"]


class Lanes:
    """The running lanes of one update run."""

    def __init__(self, ctx: "Context", log_path: Path, cancel: threading.Event, execute: Execute) -> None:
        self.ctx = ctx
        self.log_path = log_path
        self.folder = Path(str(log_path) + ".lanes")
        self.cancel = cancel
        self.execute = execute
        self._threads: Dict[str, threading.Thread] = {}
        self._done: Dict[str, List[Tuple["Job", "Row"]]] = {}
        self._sinks: Dict[str, Sink] = {}
        self._order: List[str] = []

    @property
    def running(self) -> List[str]:
        """Lanes whose thread has not ended."""
        return [name for name, thread in self._threads.items() if thread.is_alive()]

    @property
    def started(self) -> bool:
        """True when at least one lane was started."""
        return bool(self._threads)

    def start(self, groups: Mapping[str, Sequence["Job"]]) -> None:
        """Start one thread per lane. Logs the lane line to the run log."""
        refuse_symlink(self.folder)
        ensure_dir(self.folder)
        for lane, jobs in groups.items():
            if not jobs:
                continue
            path = self.folder / _safe(lane)
            sink = Sink(path, RunLog(path))
            self._sinks[lane] = sink
            self._done[lane] = []
            self._order.append(lane)
            self.ctx.log.write(lane + " lane: " + " ".join(job.tool for job in jobs))
            thread = threading.Thread(target=self._run, args=(lane, list(jobs), sink),
                                      name="aiup-lane-" + lane, daemon=True)
            self._threads[lane] = thread
            thread.start()

    def _run(self, lane: str, jobs: List["Job"], sink: Sink) -> None:
        for job in jobs:
            if self.cancel.is_set():
                break
            try:
                row = self.execute(job, sink, True)
            except Exception as exc:  # noqa: BLE001  one tool must not stop its lane
                from aiup.engine.report import row_for

                row = row_for(job.tool, job.category, job.channel, job.before)
                row.result = "failed"
                row.note = "Failed: " + type(exc).__name__ + ". aiup logs " + job.tool + " shows the output."
                sink.log.write("FAILED: " + job.tool + ": " + str(exc)[:300])
            self._done[lane].append((job, row))

    def wait(self) -> None:
        """Wait for every lane thread. Ctrl-C while waiting stops them, then waits again."""
        for thread in self._threads.values():
            while thread.is_alive():
                try:
                    thread.join(_WAIT_SLICE)
                except KeyboardInterrupt:
                    self.cancel.set()

    def finish(self) -> List[Tuple["Job", "Row"]]:
        """Wait, then add each finished tool's lane log to the run log in order.

        Returns (job, row) pairs with log offsets in the run log. Jobs a lane
        never started are not returned; they stay ``pending``.
        """
        self.wait()
        finished: List[Tuple["Job", "Row"]] = []
        for lane in self._order:
            sink = self._sinks[lane]
            for job, row in self._done.get(lane, []):
                start = _size(self.log_path)
                _append_range(sink.path, row.start, row.end, self.log_path)
                row.start, row.end = start, _size(self.log_path)
                finished.append((job, row))
        self._cleanup()
        return finished

    def _cleanup(self) -> None:
        for sink in self._sinks.values():
            remove_quietly(sink.path)
        try:
            self.folder.rmdir()
        except OSError:
            pass


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name) or "lane"


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _append_range(source: Path, start: int, end: int, dest: Path) -> None:
    """Copy bytes [start, end) of ``source`` to the end of ``dest``. Never raises."""
    if end <= start:
        return
    try:
        flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(dest), flags)
        with open(source, "rb") as src, os.fdopen(fd, "ab") as out:
            src.seek(start)
            remaining = end - start
            while remaining > 0:
                chunk = src.read(min(65536, remaining))
                if not chunk:
                    break
                out.write(chunk)
                remaining -= len(chunk)
    except OSError:
        pass
