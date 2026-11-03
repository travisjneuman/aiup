"""Platform protocol and the data types every platform module shares.

The engine, providers and commands talk to the operating system only through
a ``Platform`` object (``aiup.platform.current()``) and the helpers in
``aiup.platform.proc`` and ``aiup.platform.term``. Each method here states the
contract all three implementations keep.
"""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

if TYPE_CHECKING:
    from pathlib import Path

    from aiup.paths import Dirs


class TrashError(Exception):
    """A path could not be moved to the Trash or Recycle Bin. Nothing was deleted."""


@dataclass(frozen=True)
class DistroInfo:
    """What this computer runs.

    Linux fills ``id``, ``id_like`` and ``version_id`` from os-release.
    Windows sets ``id`` to ``"windows"``, ``version_id`` to
    ``major.minor.build``, and fills ``build`` (``build.ubr``) and ``edition``
    (for example ``Professional`` or ``ServerStandard``).
    """

    system: str                      # "linux" | "windows" | "darwin"
    id: str                          # "arch", "ubuntu", "fedora", "windows", "macos", ...
    id_like: Tuple[str, ...] = ()    # os-release ID_LIKE words, lower case
    version_id: str = ""
    name: str = ""                   # human name, for example "Arch Linux" or "Windows 11 Pro"
    build: str = ""
    edition: str = ""
    variant: str = ""                # os-release VARIANT_ID; Windows "Client" or "Server"

    def is_like(self, family: str) -> bool:
        """True when ``family`` is this distro's id or one of its ID_LIKE words."""
        family = family.lower()
        return family == self.id or family in self.id_like


# One row of the process table: parent pid and process name.
ProcessTable = Mapping[int, Tuple[int, str]]


def split_path(path_value: Optional[str]) -> Tuple[str, ...]:
    """PATH entries in order, without empty, relative or repeated entries.

    Empty and relative entries would make lookups depend on the current
    folder, so they are skipped. Repeats are dropped (compared with
    ``os.path.normcase``, so case-insensitive on Windows).
    """
    if path_value is None:
        path_value = os.environ.get("PATH", "")
    seen: Set[str] = set()
    entries: List[str] = []
    for raw in path_value.split(os.pathsep):
        entry = raw.strip().strip('"')
        if not entry or not os.path.isabs(entry):
            continue
        key = os.path.normcase(os.path.normpath(entry))
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)
    return tuple(entries)


def descendants_of(root: int, table: ProcessTable) -> Tuple[int, ...]:
    """Every pid below ``root`` in ``table``, parents before children."""
    children: Dict[int, List[int]] = {}
    for pid, row in table.items():
        ppid = row[0]
        if pid != ppid:
            children.setdefault(ppid, []).append(pid)
    found: List[int] = []
    seen: Set[int] = {root}
    queue: List[int] = [root]
    while queue:
        current = queue.pop(0)
        for child in children.get(current, ()):
            if child in seen:
                continue
            seen.add(child)
            found.append(child)
            queue.append(child)
    return tuple(found)


class Platform(abc.ABC):
    """Operating-system services for one platform.

    Methods that talk to the desktop (``notify``, ``open_url``,
    ``copy_text``) never raise: they return False and the caller prints one
    line. ``trash`` raises ``TrashError`` instead of ever deleting.
    """

    name: str = ""

    # ----- folders and commands -------------------------------------------

    def dirs(self, env: Optional[Mapping[str, str]] = None) -> "Dirs":
        """aiup's config, data, state, cache and runtime folders (section 9.2)."""
        from aiup.paths import dirs_for

        return dirs_for(self.name, os.environ if env is None else env)

    def which(self, command: str, path: Optional[str] = None) -> Optional[str]:
        """First match for ``command`` on PATH (or ``path``), or None."""
        found = self.which_all(command, path)
        return found[0] if found else None

    @abc.abstractmethod
    def which_all(self, command: str, path: Optional[str] = None) -> Tuple[str, ...]:
        """Every match for ``command`` in PATH order, one per folder.

        Absolute paths, not resolved through symbolic links, so callers can
        tell two PATH entries for the same file apart (``aiup duplicates``).
        A command that already names a folder is checked as given.
        """

    # ----- privileges and sessions ----------------------------------------

    @abc.abstractmethod
    def is_elevated(self) -> bool:
        """True when aiup runs as root (Linux, macOS) or elevated (Windows)."""

    @abc.abstractmethod
    def desktop_session(self) -> bool:
        """True when a person can see dialogs from this session.

        False over SSH, in services and scheduled jobs without a desktop.
        Windows uses it to defer steps that may raise a UAC prompt (7.4).
        """

    # ----- processes -------------------------------------------------------

    @abc.abstractmethod
    def pid_alive(self, pid: int) -> bool:
        """True when ``pid`` names a running process. Never signals it."""

    @abc.abstractmethod
    def process_table(self) -> Dict[int, Tuple[int, str]]:
        """Snapshot of running processes: pid -> (parent pid, name).

        Names are lower case base names without ``.exe`` on Windows; on Linux
        they are the kernel's ``comm`` value (at most 15 characters).
        """

    def descendants(self, pid: int) -> Tuple[int, ...]:
        """Every running process below ``pid``, parents first."""
        return self._descendants_in(pid, self.process_table())

    def _descendants_in(self, pid: int, table: ProcessTable) -> Tuple[int, ...]:
        """Descendants of ``pid`` in ``table``. Windows adds a pid-reuse guard."""
        return descendants_of(pid, table)

    def process_tree_has(self, root: int, names: Iterable[str]) -> bool:
        """True when a process called one of ``names`` runs anywhere below ``root``.

        The engine uses it to show ``sudo password:`` while sudo waits for
        input (macOS ``process_tree_has_sudo``).
        """
        wanted = self._normalize_names(names)
        if not wanted:
            return False
        table = self.process_table()
        return any(table[pid][1] in wanted for pid in self._descendants_in(root, table) if pid in table)

    def _normalize_names(self, names: Iterable[str]) -> FrozenSet[str]:
        """Process names in the form ``process_table`` reports them."""
        return frozenset(name for name in names if name)

    @abc.abstractmethod
    def kill_tree(self, pid: int, grace: float = 2.0) -> None:
        """Stop ``pid`` and everything below it. Never raises.

        Linux and macOS send SIGTERM, wait up to ``grace`` seconds, then send
        SIGKILL to what is left. Windows ends the tree at once (there is no
        polite signal for a console tree), so callers wait first.
        """

    # ----- desktop ---------------------------------------------------------

    @abc.abstractmethod
    def notify(self, title: str, body: str) -> bool:
        """Show a desktop notification. Returns False on failure, never raises."""

    @abc.abstractmethod
    def trash(self, path: str) -> "Path":
        """Move one file or folder to the Trash and return where it went.

        Raises ``TrashError`` when that is not possible. Never deletes
        anything permanently, and never follows a symbolic link: a link is
        trashed as the link itself.
        """

    @abc.abstractmethod
    def open_url(self, url: str) -> bool:
        """Open an http or https URL in the default browser. False on failure."""

    @abc.abstractmethod
    def copy_text(self, text: str) -> bool:
        """Put ``text`` on the clipboard. The text never goes in a command line."""

    @abc.abstractmethod
    def distro(self) -> DistroInfo:
        """What operating system and version this computer runs."""


def url_is_web(url: str) -> bool:
    """True for an http or https URL without control characters."""
    lowered = url.lower()
    if not (lowered.startswith("https://") or lowered.startswith("http://")):
        return False
    return not any(ord(ch) < 32 or ord(ch) == 127 for ch in url)


def executable_candidates(command: str, pathext: Sequence[str]) -> Tuple[str, ...]:
    """File names to try for ``command``: as given, then with each PATHEXT suffix.

    With an empty ``pathext`` (Linux, macOS) only the name itself is tried.
    On Windows a name that already ends in a PATHEXT suffix is tried as given
    first, as cmd.exe does.
    """
    if not pathext:
        return (command,)
    lowered = command.lower()
    names: List[str] = []
    if any(lowered.endswith(ext.lower()) for ext in pathext):
        names.append(command)
    names.extend(command + ext for ext in pathext)
    return tuple(names)
