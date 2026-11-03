"""The engine's only calls into the platform layer and the provider registry.

``aiup.platform`` (WP5) and ``aiup.providers`` are written beside the engine.
Every call the engine makes into them goes through this module, so a change
there is fixed here once.

Used interfaces:

- ``aiup.platform.current() -> Platform`` and the ``Platform`` methods
  ``which``, ``pid_alive``, ``process_tree_has``, ``kill_tree``,
  ``is_elevated``, ``desktop_session``, ``trash``, ``distro``.
- ``aiup.platform.proc.run_read`` and ``run_step``.
- ``aiup.providers.all_providers()`` and ``aiup.providers.get(name)``.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import IO, TYPE_CHECKING, Callable, List, Mapping, Optional, Sequence, Tuple, TypeVar

if TYPE_CHECKING:
    from aiup.platform.base import DistroInfo, Platform
    from aiup.platform.proc import ReadResult, StepResult
    from aiup.providers.base import Provider


_T = TypeVar("_T")
_R = TypeVar("_R")


def map_threads(workers: int, work: Callable[[_T], _R], items: Sequence[_T]) -> List[_R]:
    """``work`` over ``items`` on up to ``workers`` threads, results in order.

    Ctrl-C (or an error) drops the items not started yet instead of waiting
    for every one of them; the reads already running end on their timeouts.
    """
    pool = ThreadPoolExecutor(max_workers=max(1, workers))
    try:
        results = list(pool.map(work, items))
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    return results


def current_platform() -> "Platform":
    """The platform object for this computer."""
    from aiup.platform import current

    return current()


def platform_name(platform: "Platform") -> str:
    """The platform name: linux, windows or darwin."""
    return str(getattr(platform, "name", "") or "")


def distro(platform: "Platform") -> "DistroInfo":
    """What operating system and version this computer runs."""
    return platform.distro()


def which(platform: "Platform", command: str) -> Optional[str]:
    """Full path of a command on PATH, or None."""
    return platform.which(command)


def pid_alive(platform: "Platform", pid: int) -> bool:
    """True when a process with this id is running. Never signals it."""
    try:
        return bool(platform.pid_alive(pid))
    except OSError:
        return True  # unsure: keep the run's files


def sudo_running_under(platform: "Platform", root_pid: int) -> bool:
    """True when a sudo process is a descendant of ``root_pid``."""
    try:
        return bool(platform.process_tree_has(root_pid, ("sudo",)))
    except OSError:
        return False


def process_running(platform: "Platform", names: Sequence[str]) -> bool:
    """True when any process with one of ``names`` runs on this computer."""
    try:
        # The platform's form: Linux cuts names to 15 characters, Windows drops ".exe".
        wanted = frozenset(name.lower() for name in platform._normalize_names(names))
        table = platform.process_table()
    except OSError:
        return True  # unsure: treat the cache as in use
    me = os.getpid()
    return any(name.lower() in wanted for pid, (_, name) in table.items() if pid != me)


def kill_tree(platform: "Platform", pid: int) -> None:
    """Stop a child process and everything it started. Never raises."""
    try:
        platform.kill_tree(pid)
    except OSError:
        pass


def is_elevated(platform: "Platform") -> bool:
    """True when aiup runs as root (Linux) or elevated (Windows)."""
    try:
        return bool(platform.is_elevated())
    except OSError:
        return False


def desktop_session(platform: "Platform") -> bool:
    """True when a person can see dialogs from this session (not over SSH)."""
    try:
        return bool(platform.desktop_session())
    except OSError:
        return False


def trash(platform: "Platform", path: Path) -> Path:
    """Move one path to the Trash or Recycle Bin and return where it went.

    Raises the platform's ``TrashError`` when that is not possible.
    """
    return Path(platform.trash(str(path)))


def run_read(argv: Sequence[str], timeout: float, max_bytes: int,
             env: Optional[Mapping[str, str]] = None, cwd: Optional[str] = None) -> "ReadResult":
    """A bounded read-only command (``proc.run_read``)."""
    from aiup.platform import proc

    return proc.run_read(tuple(argv), timeout=timeout, max_bytes=max_bytes, env=env, cwd=cwd)


def run_step(argv: Sequence[str], log_path: Path, *, echo: Optional[IO[str]],
             timeout: Optional[float], env: Optional[Mapping[str, str]],
             interactive: bool, cancel: Optional[threading.Event],
             on_tick: Optional[Callable[[float], None]], grace: float,
             cwd: Optional[str] = None, stdout_to_stderr: bool = False) -> "StepResult":
    """Run one logged step (``proc.run_step``)."""
    from aiup.platform import proc

    return proc.run_step(
        tuple(argv), str(log_path), echo=echo, timeout=timeout, env=env, cwd=cwd,
        interactive=interactive, cancel=cancel, on_tick=on_tick,
        tick_seconds=1.0, grace=grace, stdout_to_stderr=stdout_to_stderr,
    )


def all_providers() -> Tuple["Provider", ...]:
    """Every registered provider."""
    from aiup import providers

    return tuple(providers.all_providers())


def get_provider(name: str) -> Optional["Provider"]:
    """The provider for one channel name, or None when none is registered."""
    from aiup import providers

    try:
        return providers.get(name)
    except (KeyError, LookupError):
        return None


def is_root() -> bool:
    """True when the effective user is root (Linux and macOS)."""
    geteuid = getattr(os, "geteuid", None)
    return geteuid is not None and geteuid() == 0
