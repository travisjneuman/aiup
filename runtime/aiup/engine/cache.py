"""Atomic writes and TTL caches (design doc section 9.1).

Every cache file is written to a temp file in the same folder and moved into
place with ``os.replace``, so a reader sees the old file or the new one, never
half of one. Symbolic links are refused for every file and folder here, as the
macOS Python helpers do. A cache is never trusted for a change to a tool: the
engine reads the installed version live before it changes anything.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from aiup.errors import AiupError
from aiup.paths import PRIVATE_FILE_MODE, ensure_dir, refuse_symlink

JSON_MAX_BYTES = 4 * 1024 * 1024
_WINDOWS = os.name == "nt"


def atomic_write_bytes(path: Path, data: bytes, mode: int = PRIVATE_FILE_MODE) -> None:
    """Write ``data`` to ``path`` through a temp file and ``os.replace``.

    Creates the parent folder (private) when needed. Refuses a path that is a
    symbolic link. The file is mode 600 on Linux by default.
    """
    ensure_dir(path.parent)
    refuse_symlink(path)
    fd, temp_name = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".next", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if not _WINDOWS:
            os.chmod(temp, mode)
        os.replace(temp, path)
    except BaseException:
        try:
            temp.unlink()
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, mode: int = PRIVATE_FILE_MODE) -> None:
    """Write UTF-8 text atomically (see :func:`atomic_write_bytes`)."""
    atomic_write_bytes(path, text.encode("utf-8"), mode)


def atomic_write_json(path: Path, data: object, mode: int = PRIVATE_FILE_MODE) -> None:
    """Write JSON with two-space indents and a final newline, atomically."""
    atomic_write_text(path, json.dumps(data, indent=2) + "\n", mode)


def read_bytes_bounded(path: Path, max_bytes: int) -> Optional[bytes]:
    """The file's bytes, or None when missing, a link, too big or unreadable."""
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if path.stat().st_size > max_bytes:
            return None
        return path.read_bytes()
    except OSError:
        return None


def read_text_bounded(path: Path, max_bytes: int = JSON_MAX_BYTES) -> Optional[str]:
    """The file as UTF-8 text (bad bytes replaced), or None (see above)."""
    raw = read_bytes_bounded(path, max_bytes)
    return None if raw is None else raw.decode("utf-8", errors="replace")


def read_json(path: Path, max_bytes: int = JSON_MAX_BYTES) -> Optional[object]:
    """Parsed JSON from a file, or None when it is missing or not valid."""
    text = read_text_bounded(path, max_bytes)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def remove_quietly(path: Path) -> None:
    """Delete one file (never a folder or what a link points at)."""
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
    except OSError:
        pass


def cache_key(text: str) -> str:
    """A file name for a cache key: every unsafe character percent-encoded."""
    return urllib.parse.quote(text, safe="-._@+")


class Stamp:
    """Empty stamp files whose age says when something last ran.

    Used for package-manager metadata (``<cache>/metadata/<manager>.stamp``)
    and the daily pnpm store prune (macOS ``brew-metadata.stamp``,
    ``pnpm-store-prune.stamp``).
    """

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def path(self, name: str) -> Path:
        """Where the stamp for ``name`` lives."""
        return self.folder / (cache_key(name) + ".stamp")

    def age(self, name: str, now: Optional[float] = None) -> Optional[float]:
        """Seconds since the stamp was touched, or None when there is none."""
        path = self.path(name)
        try:
            if path.is_symlink():
                return None
            mtime = path.stat().st_mtime
        except OSError:
            return None
        return max(0.0, (time.time() if now is None else now) - mtime)

    def fresh(self, name: str, ttl: float, now: Optional[float] = None) -> bool:
        """True when the stamp is younger than ``ttl`` seconds."""
        age = self.age(name, now)
        return age is not None and age < ttl

    def touch(self, name: str) -> None:
        """Mark ``name`` as done now."""
        try:
            atomic_write_bytes(self.path(name), b"")
        except (OSError, AiupError):
            pass

    def clear(self, name: str) -> None:
        """Forget the stamp, so the next run does the work again."""
        remove_quietly(self.path(name))


@dataclass(frozen=True)
class CachedVersion:
    """One available-version answer (macOS ``available_cache_read``)."""

    at: float
    current: str        # the installed version the answer was read for
    status: str         # "newer" | "current" | "failure"
    version: str        # the newer version, when status is "newer"


_STATUSES = ("newer", "current", "failure")
_VERSION_TEXT = re.compile(r"^[A-Za-z0-9._+,~:@-]*$")


class AvailableVersionCache:
    """Latest-version answers per tool and channel, with TTLs and a size limit.

    One file per key under ``<cache>/available-versions/``, holding one line
    ``epoch<TAB>current<TAB>status<TAB>version``. Answers are kept 900 seconds,
    failures 60 seconds, and at most 512 files (oldest removed first).
    An answer only counts for the installed version it was read for.
    """

    def __init__(self, folder: Path, ttl: int, failure_ttl: int, limit: int) -> None:
        self.folder = folder
        self.ttl = ttl
        self.failure_ttl = failure_ttl
        self.limit = max(1, limit)
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        return self.folder / (cache_key(key) + ".tsv")

    def get(self, key: str, current: str, now: Optional[float] = None) -> Optional[CachedVersion]:
        """A fresh answer for ``key`` read for installed version ``current``."""
        text = read_text_bounded(self._path(key), 4096)
        if not text:
            return None
        fields = text.rstrip("\n").split("\t")
        if len(fields) != 4 or fields[2] not in _STATUSES:
            return None
        try:
            at = float(fields[0])
        except ValueError:
            return None
        if fields[1] != current:
            return None
        ttl = self.failure_ttl if fields[2] == "failure" else self.ttl
        if (time.time() if now is None else now) - at >= ttl:
            return None
        return CachedVersion(at=at, current=fields[1], status=fields[2], version=fields[3])

    def put(self, key: str, current: str, status: str, version: str) -> None:
        """Store an answer. Values with tabs or line breaks are not stored."""
        if status not in _STATUSES:
            return
        if not _VERSION_TEXT.match(current) or not _VERSION_TEXT.match(version):
            return
        line = "%d\t%s\t%s\t%s\n" % (int(time.time()), current, status, version)
        with self._lock:
            try:
                atomic_write_text(self._path(key), line)
            except (OSError, AiupError):
                return
            self._prune()

    def forget(self, key: str) -> None:
        """Drop one answer (after a tool changed)."""
        remove_quietly(self._path(key))

    def _prune(self) -> None:
        try:
            entries = [p for p in self.folder.iterdir() if p.suffix == ".tsv" and not p.is_symlink()]
        except OSError:
            return
        if len(entries) <= self.limit:
            return
        def mtime(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0
        entries.sort(key=mtime)
        for path in entries[: len(entries) - self.limit]:
            remove_quietly(path)


class Caches:
    """Every cache the engine keeps, under one ``<cache>`` folder."""

    def __init__(self, root: Path, ttl: int, failure_ttl: int, limit: int) -> None:
        self.root = root
        self.available = AvailableVersionCache(root / "available-versions", ttl, failure_ttl, limit)
        self.metadata = Stamp(root / "metadata")
        self.release_notes = root / "release-notes"
        self.downloads = root / "downloads"
        self._memo: Dict[str, object] = {}
        self._memo_lock = threading.Lock()
        self._generation = 0

    def remember(self, key: str, value: object) -> None:
        """Keep a value for the rest of this process (not written to disk)."""
        with self._memo_lock:
            self._memo[key] = value

    def generation(self) -> int:
        """A number that goes up each time scans are forgotten."""
        with self._memo_lock:
            return self._generation

    def forget_scans(self, keys: Iterable[str]) -> None:
        """Drop ``keys`` and start a new generation, so a read that began before is not kept."""
        with self._memo_lock:
            self._generation += 1
            for key in keys:
                self._memo.pop(key, None)

    def remember_from(self, generation: int, key: str, value: object) -> bool:
        """Keep ``value`` only when no scans were forgotten since ``generation`` was read."""
        with self._memo_lock:
            if generation != self._generation:
                return False
            self._memo[key] = value
            return True

    def recall(self, key: str) -> Optional[object]:
        """A value kept with :meth:`remember`, or None."""
        with self._memo_lock:
            return self._memo.get(key)
