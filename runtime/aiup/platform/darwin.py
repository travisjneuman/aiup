"""macOS platform, kept minimal: enough for catalog export (section 3).

macOS keeps its Bash runtime, so this module is not a supported runtime. It
reuses the POSIX parts of the Linux module and swaps what macOS does
differently: no /proc, ``~/.Trash``, osascript, ``open`` and ``pbcopy``.
"""

from __future__ import annotations

import functools
import os
import platform as _stdlib_platform
import time
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, Tuple

from aiup.platform import proc
from aiup.platform.base import DistroInfo, TrashError, url_is_web
from aiup.platform.linux import LinuxPlatform, spawn_detached

# Text arrives as argv, so nothing the caller passes is parsed as AppleScript.
_NOTIFY_SCRIPT = (
    "on run argv\n"
    "display notification (item 2 of argv) with title (item 1 of argv)\n"
    "end run"
)


class DarwinPlatform(LinuxPlatform):
    """macOS implementation of ``Platform`` (POSIX parts shared with Linux)."""

    name = "darwin"

    def desktop_session(self) -> bool:
        """True unless aiup runs over SSH."""
        return not any(os.environ.get(name) for name in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"))

    def pid_alive(self, pid: int) -> bool:
        """Signal-0 probe (sends nothing on POSIX). A zombie still counts as alive."""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def process_table(self) -> Dict[int, Tuple[int, str]]:
        """pid -> (parent pid, command base name) from ``ps``."""
        result = proc.run_read(["/bin/ps", "-axo", "pid=,ppid=,comm="], timeout=10.0)
        table: Dict[int, Tuple[int, str]] = {}
        if not result.ok:
            return table
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
                continue
            table[int(parts[0])] = (int(parts[1]), os.path.basename(parts[2]))
        return table

    def _normalize_names(self, names: Iterable[str]) -> FrozenSet[str]:
        return frozenset(os.path.basename(name) for name in names if name)

    def notify(self, title: str, body: str) -> bool:
        """``display notification`` through osascript."""
        argv = ["/usr/bin/osascript", "-e", _NOTIFY_SCRIPT, title, body or title]
        return proc.run_read(argv, timeout=10.0).ok

    def trash(self, path: str) -> Path:
        """Rename into ``~/.Trash`` on the same volume; refuse anything else.

        Like the Bash runtime, the item keeps its name with an aiup time
        stamp in front, so two removals never collide.
        """
        target = os.path.abspath(path)
        if not os.path.lexists(target):
            raise TrashError(path + " does not exist")
        trash_dir = os.path.join(os.path.expanduser("~"), ".Trash")
        _refuse_protected(target, trash_dir)
        try:
            same_volume = os.lstat(target).st_dev == os.stat(trash_dir).st_dev
        except OSError as exc:
            raise TrashError("cannot use " + trash_dir + ": " + str(exc)) from exc
        if not same_volume:
            raise TrashError(target + " is on a different volume than your Trash. Nothing was moved.")
        return _rename_into(trash_dir, target)

    def open_url(self, url: str) -> bool:
        """``open`` with the URL."""
        return url_is_web(url) and spawn_detached(["/usr/bin/open", url])

    def copy_text(self, text: str) -> bool:
        """``pbcopy`` with the text on stdin."""
        return proc.run_feed(["/usr/bin/pbcopy"], text.encode("utf-8"), timeout=10.0) == 0

    def distro(self) -> DistroInfo:
        """macOS product version from ``platform.mac_ver``."""
        return _darwin_distro()


def _refuse_protected(target: str, trash_dir: str) -> None:
    """Never move /, the home folder, the Trash or anything holding them."""
    home = os.path.expanduser("~")
    for item in ("/", home, trash_dir):
        if target == item or item.startswith(target.rstrip("/") + "/"):
            raise TrashError("refusing to move " + target + " to the Trash")
    if target.startswith(trash_dir.rstrip("/") + "/"):
        raise TrashError(target + " is already in the Trash")


def _rename_into(trash_dir: str, target: str) -> Path:
    """Rename ``target`` to ``aiup-<stamp>-<leaf>`` inside the Trash, never replacing."""
    stamp = time.strftime("%Y%m%d%H%M%S")
    leaf = os.path.basename(target.rstrip("/")) or "item"
    for attempt in range(1000):
        suffix = "" if attempt == 0 else "." + str(attempt)
        destination = os.path.join(trash_dir, "aiup-" + stamp + "-" + leaf + suffix)
        if os.path.lexists(destination):
            continue
        try:
            os.rename(target, destination)
        except OSError as exc:
            raise TrashError("could not move " + target + " to the Trash: " + str(exc)) from exc
        return Path(destination)
    raise TrashError("could not find a free name in " + trash_dir + " for " + target)


@functools.lru_cache(maxsize=1)
def _darwin_distro() -> DistroInfo:
    release, _info, _machine = _stdlib_platform.mac_ver()
    build = ""
    result = proc.run_read(["/usr/bin/sw_vers", "-buildVersion"], timeout=5.0)
    if result.ok:
        build = result.stdout.strip()
    return DistroInfo(
        system="darwin",
        id="macos",
        id_like=(),
        version_id=release,
        name=("macOS " + release).strip(),
        build=build,
    )
