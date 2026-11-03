"""Helpers the Linux providers share: read commands, steps, lock checks, ``Memo``.

``run_c`` runs a read-only command with ``LC_ALL=C``. ``system_step`` builds a
step the engine wraps in sudo; ``user_step`` one that never is. The lock
checks read ``/proc/locks`` and pid files. ``Memo`` is the per-run cache for
bulk reads.
"""

from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING, Callable, Dict, Iterable, Mapping, NamedTuple, Optional, Sequence, Set, Tuple, TypeVar

from aiup.model import Action, Step

if TYPE_CHECKING:
    from aiup.engine.context import Context


READ_TIMEOUT = 10.0                 # local database reads
INVENTORY_MAX_BYTES = 8 * 1024 * 1024
SMALL_MAX_BYTES = 1024 * 1024
LOCKED_NOTE = "another package manager is running"
NEEDS_TERMINAL_NOTE = "needs a terminal; run aiup in a terminal"
_T = TypeVar("_T")


class ReadOut(NamedTuple):
    """What a read command printed. ``code`` is None when it did not finish."""

    code: Optional[int]
    out: str
    err: str


def run_c(ctx: "Context", argv: Sequence[str], timeout: float = READ_TIMEOUT,
          max_bytes: int = SMALL_MAX_BYTES, env: Sequence[str] = ()) -> ReadOut:
    """Run a read-only command with ``LC_ALL=C`` (untranslated output).

    Variables are set through ``env NAME=value`` in argv, so the call keeps
    the ``ctx.run_read(argv, timeout, max_bytes)`` contract. A command that
    did not start, timed out or overflowed ``max_bytes`` gives ``code=None``.
    """
    full = ["env", "LC_ALL=C"] + list(env) + list(argv)
    try:
        result = ctx.run_read(full, timeout, max_bytes)
    except (OSError, ValueError) as exc:
        return ReadOut(None, "", str(exc))
    if result.error or result.timed_out or result.truncated:
        return ReadOut(None, "", result.stderr or result.error)
    return ReadOut(result.returncode, result.stdout, result.stderr)


def which(ctx: "Context", command: str) -> Optional[str]:
    """Absolute path of ``command`` on PATH, or None."""
    try:
        return ctx.platform.which(command)
    except (OSError, ValueError):
        return None


def is_linux(ctx: "Context") -> bool:
    """True when aiup runs on Linux."""
    return (getattr(ctx, "os_name", "") or getattr(ctx.platform, "name", "")) == "linux"


def setting(ctx: "Context", key: str, default: str) -> str:
    """One value from ``settings`` (``system``, ``aur``), attribute or mapping."""
    settings = getattr(ctx, "settings", None)
    if settings is None:
        return default
    value = getattr(settings, key, None)
    if value is None and isinstance(settings, Mapping):
        value = settings.get(key)
    return value if isinstance(value, str) and value else default


def distro_ids(ctx: "Context") -> Tuple[str, ...]:
    """os-release ``ID`` followed by the ``ID_LIKE`` words, lower case."""
    info = getattr(ctx, "distro", None)
    if info is None:
        return ()
    ident = str(getattr(info, "id", "") or "").lower()
    like = tuple(str(word).lower() for word in (getattr(info, "id_like", ()) or ()))
    return ((ident,) if ident else ()) + like


def system_step(ctx: "Context", argv: Sequence[str], label: str,
                timeout: Optional[float] = None, env: Optional[Mapping[str, str]] = None) -> Step:
    """A step a system manager runs with sudo.

    argv never contains ``sudo``: ``engine/privilege.py`` adds ``sudo`` (with
    a terminal) or ``sudo -n`` (without one). The step asks for the terminal
    only when aiup has one, so sudo can prompt on screen.
    """
    return Step(argv=tuple(argv), label=label, privilege="sudo",
                interactive=bool(ctx.interactive), env=dict(env or {}), timeout=timeout)


def asking_remove(ctx: "Context", manager: str, package: str, argv: Sequence[str]) -> Action:
    """A system remove the manager confirms on the terminal, since it may remove more.

    Without a terminal the manager's question would read end of file and stop,
    so the action is deferred instead.
    """
    if not ctx.interactive:
        return Action(tool=package, op="remove", channel=manager, steps=(), result="deferred",
                      note=NEEDS_TERMINAL_NOTE)
    step = Step(argv=tuple(argv), label=" ".join(argv), privilege="sudo", interactive=True)
    note = "{} shows every package it would remove and asks before it does.".format(argv[0])
    return Action(tool=package, op="remove", channel=manager, steps=(step,), note=note)


def user_step(argv: Sequence[str], label: str, interactive: bool = False,
              env: Optional[Mapping[str, str]] = None, privilege: str = "none",
              timeout: Optional[float] = None) -> Step:
    """A step that runs as the user (never under sudo)."""
    return Step(argv=tuple(argv), label=label, privilege=privilege,
                interactive=interactive, env=dict(env or {}), timeout=timeout)


def posix_lock_held(paths: Iterable[str]) -> bool:
    """True when another process holds an fcntl or flock lock on one of ``paths``.

    Reads ``/proc/locks`` and matches device and inode, so it works as a
    normal user even when the lock file itself is not readable.
    """
    wanted: Set[Tuple[int, int, int]] = set()
    for path in paths:
        try:
            info = os.stat(path)
        except OSError:
            continue
        wanted.add((os.major(info.st_dev), os.minor(info.st_dev), info.st_ino))
    if not wanted:
        return False
    try:
        with open("/proc/locks", "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read(1024 * 1024).splitlines()
    except OSError:
        return False
    for line in lines:
        key = _proc_lock_key(line)
        if key is not None and key in wanted:
            return True
    return False


def _proc_lock_key(line: str) -> Optional[Tuple[int, int, int]]:
    """``(major, minor, inode)`` from one ``/proc/locks`` line."""
    for field in line.split():
        parts = field.split(":")
        if len(parts) != 3:
            continue
        try:
            return int(parts[0], 16), int(parts[1], 16), int(parts[2])
        except ValueError:
            continue
    return None


def pidfile_held(path: str) -> bool:
    """True when ``path`` names a running process other than aiup itself."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(64).strip()
    except OSError:
        return False
    if not text.isdigit():
        return False
    pid = int(text)
    return pid > 0 and pid != os.getpid() and os.path.isdir("/proc/{}".format(pid))


class Memo:
    """A small thread-safe in-process cache with a time limit per entry.

    Bulk reads (installed database, update lists) run once and serve every
    per-tool question that follows in the same run.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: Dict[str, Tuple[float, object]] = {}

    def get(self, key: str, ttl: float, produce: Callable[[], _T]) -> _T:
        """The cached value for ``key``, produced again when older than ``ttl``."""
        now = time.monotonic()
        with self._lock:
            hit = self._values.get(key)
            if hit is not None and now - hit[0] < ttl:
                return hit[1]  # type: ignore[return-value]
        value = produce()
        with self._lock:
            self._values[key] = (time.monotonic(), value)
        return value

    def peek(self, key: str, ttl: float) -> Tuple[bool, object]:
        """``(True, value)`` when ``key`` holds a value younger than ``ttl``."""
        with self._lock:
            hit = self._values.get(key)
            if hit is not None and time.monotonic() - hit[0] < ttl:
                return True, hit[1]
        return False, None

    def put(self, key: str, value: object) -> None:
        """Store ``value`` under ``key``."""
        with self._lock:
            self._values[key] = (time.monotonic(), value)

    def drop(self, key: str) -> None:
        """Forget one key."""
        with self._lock:
            self._values.pop(key, None)

    def clear(self) -> None:
        """Forget everything (after a mutation)."""
        with self._lock:
            self._values.clear()


def fetch_json(ctx: "Context", url: str, timeout: float, max_bytes: int = SMALL_MAX_BYTES) -> Optional[object]:
    """GET an HTTPS JSON document through ``ctx.net.fetch``; None on any failure."""
    if not url.startswith("https://"):
        return None
    try:
        result = ctx.net.fetch(url, max_bytes=max_bytes, timeout=timeout)
        return result.json() if result.ok else None
    except Exception:  # noqa: BLE001  network, TLS, size and JSON errors all mean "unverified"
        return None


def mtime_of(path: str) -> float:
    """Modification time of ``path``, 0.0 when missing."""
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0.0
