"""Linux platform: /proc processes, freedesktop Trash and notifications, xdg-open."""

from __future__ import annotations

import functools
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote

from aiup.platform import proc
from aiup.platform.base import DistroInfo, Platform, TrashError, split_path, url_is_web

_COMM_LIMIT = 15  # the kernel truncates comm to 15 characters
_OS_RELEASE_FILES = ("/etc/os-release", "/usr/lib/os-release")


class LinuxPlatform(Platform):
    """Linux implementation of ``Platform``."""

    name = "linux"

    # ----- commands --------------------------------------------------------

    def which_all(self, command: str, path: Optional[str] = None) -> Tuple[str, ...]:
        """Executable files named ``command`` in each PATH folder, in order."""
        if not command or "\0" in command:
            return ()
        if "/" in command:
            candidate = os.path.abspath(command)
            return (candidate,) if _is_executable(candidate) else ()
        found: List[str] = []
        for entry in split_path(path):
            candidate = os.path.join(entry, command)
            if _is_executable(candidate):
                found.append(candidate)
        return tuple(found)

    # ----- privileges and sessions ------------------------------------------

    def is_elevated(self) -> bool:
        """True when the effective user is root."""
        return os.geteuid() == 0

    def desktop_session(self) -> bool:
        """True when a Wayland or X11 display is set for this session."""
        return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))

    # ----- processes ---------------------------------------------------------

    def pid_alive(self, pid: int) -> bool:
        """True when ``pid`` runs and is not a zombie. Sends no signal."""
        if pid <= 0:
            return False
        state = _proc_state(pid)
        if state is not None:
            return state not in ("Z", "X", "x")
        if os.path.isdir("/proc/self"):
            return False  # /proc works and has no entry for pid
        return _posix_pid_exists(pid)

    def process_table(self) -> Dict[int, Tuple[int, str]]:
        """pid -> (parent pid, comm) for every process in /proc."""
        table: Dict[int, Tuple[int, str]] = {}
        try:
            entries = os.listdir("/proc")
        except OSError:
            return table
        for entry in entries:
            if not entry.isdigit():
                continue
            row = _read_stat(int(entry))
            if row is not None:
                table[int(entry)] = (row[1], row[2])
        return table

    def _normalize_names(self, names: Iterable[str]) -> FrozenSet[str]:
        return frozenset(name[:_COMM_LIMIT] for name in names if name)

    def kill_tree(self, pid: int, grace: float = 2.0) -> None:
        """SIGTERM ``pid``, its descendants and its own process group; SIGKILL what is left."""
        if pid <= 1 or pid == os.getpid():
            return
        targets = _safe_targets((pid,) + self.descendants(pid))
        group = _own_group(pid)
        _signal_all(targets, group, signal.SIGTERM)
        deadline = time.monotonic() + max(0.0, grace)
        while time.monotonic() < deadline and any(self.pid_alive(p) for p in targets):
            time.sleep(0.05)
        late = _safe_targets(targets + self.descendants(pid))
        survivors = tuple(p for p in late if self.pid_alive(p))
        if survivors or group:
            _signal_all(survivors, group, signal.SIGKILL)

    # ----- desktop ---------------------------------------------------------

    def notify(self, title: str, body: str) -> bool:
        """notify-send, then gdbus to org.freedesktop.Notifications (section 9.6)."""
        env = _session_bus_env()
        if self.which("notify-send"):
            result = proc.run_read(
                ["notify-send", "--app-name=aiup", "--", title, body], timeout=10.0, env=env
            )
            if result.ok:
                return True
        if self.which("gdbus"):
            result = proc.run_read(_gdbus_notify_argv(title, body), timeout=10.0, env=env)
            if result.ok:
                return True
        return False

    def trash(self, path: str) -> Path:
        """Freedesktop Trash: home trash on the same filesystem, else ``gio trash``."""
        target = _absolute_no_follow(path)
        if not os.path.lexists(target):
            raise TrashError(path + " does not exist")
        home_trash = _home_trash_dir()
        _refuse_protected(target, home_trash)
        if os.lstat(target).st_dev == _device_of(home_trash):
            return _move_to_trash_dir(home_trash, target)
        if self.which("gio"):
            result = proc.run_read(["gio", "trash", "--", target], timeout=120.0)
            if result.ok and not os.path.lexists(target):
                return _mount_trash_dir(target)
            raise TrashError("gio could not move " + target + " to the Trash; nothing was deleted")
        raise TrashError(
            target + " is on a different drive than your Trash, and gio is not installed to use "
            "that drive's Trash. Nothing was moved or deleted."
        )

    def open_url(self, url: str) -> bool:
        """xdg-open, then gio open, then wslview."""
        if not url_is_web(url):
            return False
        for argv in (["xdg-open", url], ["gio", "open", url], ["wslview", url]):
            if self.which(argv[0]) and spawn_detached(argv, settle=1.0):
                return True
        return False

    def copy_text(self, text: str) -> bool:
        """wl-copy, then xclip, then xsel; the text goes on stdin."""
        data = text.encode("utf-8")
        for argv in (["wl-copy"], ["xclip", "-selection", "clipboard", "-in"], ["xsel", "--clipboard", "--input"]):
            if self.which(argv[0]) and proc.run_feed(argv, data, timeout=10.0) == 0:
                return True
        return False

    def distro(self) -> DistroInfo:
        """ID, ID_LIKE, VERSION_ID and names from os-release."""
        return _linux_distro()


# ----- helpers shared with darwin.py ---------------------------------------


def spawn_detached(argv: Sequence[str], settle: float = 3.0) -> bool:
    """Start an opener in its own session with no stdio; True unless it fails fast.

    Openers such as xdg-open may wait for the browser, so a process still
    running after ``settle`` seconds counts as success.
    """
    try:
        args = proc.resolve_argv(argv)
        child = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (proc.ProcError, OSError):
        return False
    try:
        return child.wait(timeout=settle) == 0
    except subprocess.TimeoutExpired:
        return True


def _is_executable(candidate: str) -> bool:
    return os.path.isfile(candidate) and os.access(candidate, os.X_OK)


def _posix_pid_exists(pid: int) -> bool:
    """Signal-0 probe; only used on POSIX, where signal 0 sends nothing."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _safe_targets(pids: Iterable[int]) -> Tuple[int, ...]:
    """Unique pids, never init or aiup itself."""
    me = os.getpid()
    seen: List[int] = []
    for pid in pids:
        if pid > 1 and pid != me and pid not in seen:
            seen.append(pid)
    return tuple(seen)


def _own_group(pid: int) -> int:
    """``pid``'s process group when it leads one that is not aiup's, else 0."""
    try:
        group = os.getpgid(pid)
    except OSError:
        return 0
    if group == pid and group != os.getpgrp() and group > 1:
        return group
    return 0


def _signal_all(pids: Iterable[int], group: int, sig: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            continue
    if group:
        try:
            os.killpg(group, sig)
        except OSError:
            pass


# ----- /proc ---------------------------------------------------------------


def _read_stat(pid: int) -> Optional[Tuple[str, int, str]]:
    """(state, parent pid, comm) from /proc/<pid>/stat, or None."""
    try:
        with open("/proc/%d/stat" % pid, "rb") as handle:
            raw = handle.read(4096)
    except OSError:
        return None
    text = raw.decode("utf-8", errors="replace")
    open_paren = text.find("(")
    close_paren = text.rfind(")")
    if open_paren < 0 or close_paren < open_paren:
        return None
    comm = text[open_paren + 1:close_paren]
    fields = text[close_paren + 1:].split()
    if len(fields) < 2:
        return None
    try:
        return fields[0], int(fields[1]), comm
    except ValueError:
        return None


def _proc_state(pid: int) -> Optional[str]:
    row = _read_stat(pid)
    return row[0] if row is not None else None


# ----- notifications ---------------------------------------------------------


def _session_bus_env() -> Dict[str, str]:
    """Point cron and timer jobs at the user's session bus when it is unset."""
    if os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return {}
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "")
    bus = os.path.join(runtime_dir, "bus") if os.path.isabs(runtime_dir) else ""
    if bus and os.path.exists(bus):
        return {"DBUS_SESSION_BUS_ADDRESS": "unix:path=" + bus}
    return {}


def _gvariant_string(text: str) -> str:
    """A GVariant text-format string literal, so gdbus reads the text exactly."""
    escaped: List[str] = []
    for ch in text:
        if ch in ("\\", "'"):
            escaped.append("\\" + ch)
        elif ch == "\n":
            escaped.append("\\n")
        elif ch == "\t":
            escaped.append("\\t")
        elif ord(ch) < 32 or ord(ch) == 127:
            escaped.append("\\u%04x" % ord(ch))
        else:
            escaped.append(ch)
    return "'" + "".join(escaped) + "'"


def _gdbus_notify_argv(title: str, body: str) -> List[str]:
    """org.freedesktop.Notifications.Notify with explicitly typed arguments."""
    return [
        "gdbus", "call", "--session",
        "--dest", "org.freedesktop.Notifications",
        "--object-path", "/org/freedesktop/Notifications",
        "--method", "org.freedesktop.Notifications.Notify",
        "'aiup'", "uint32 0", "''",
        _gvariant_string(title), _gvariant_string(body),
        "@as []", "@a{sv} {}", "int32 5000",
    ]


# ----- Trash -----------------------------------------------------------------


def _absolute_no_follow(path: str) -> str:
    """Absolute path with the parent resolved and the last part kept as is."""
    absolute = os.path.abspath(os.path.expanduser(path))
    parent, leaf = os.path.split(absolute.rstrip("/") or "/")
    if not leaf:
        return "/"
    return os.path.join(os.path.realpath(parent), leaf)


def _home_trash_dir() -> str:
    data_home = os.environ.get("XDG_DATA_HOME", "")
    if not os.path.isabs(data_home):
        data_home = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(data_home, "Trash")


def _is_within(child: str, parent: str) -> bool:
    child_norm = os.path.normpath(child)
    parent_norm = os.path.normpath(parent)
    return child_norm == parent_norm or child_norm.startswith(parent_norm.rstrip("/") + "/")


def _refuse_protected(target: str, home_trash: str) -> None:
    """Never trash /, the home folder, the Trash, or anything holding them."""
    home = os.path.realpath(os.path.expanduser("~"))
    trash_real = os.path.realpath(home_trash)
    if target == "/" or os.path.normpath(target) == home:
        raise TrashError("refusing to move " + target + " to the Trash")
    if _is_within(trash_real, target) or _is_within(target, trash_real):
        raise TrashError("refusing to move " + target + " to the Trash: it holds or is inside the Trash")


def _device_of(path: str) -> int:
    """st_dev of ``path``, or of its nearest existing parent folder."""
    current = path
    while True:
        try:
            return os.stat(current).st_dev
        except OSError:
            parent = os.path.dirname(current)
            if parent == current:
                return -1
            current = parent


def _ensure_private_dir(path: str) -> None:
    if os.path.islink(path):
        raise TrashError("refusing a symbolic-link Trash folder: " + path)
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
    except OSError as exc:
        raise TrashError("cannot create the Trash folder " + path + ": " + str(exc)) from exc
    if not os.path.isdir(path) or os.path.islink(path):
        raise TrashError("the Trash folder is not a folder: " + path)


def _trash_name(leaf: str, attempt: int) -> str:
    """``leaf``, then ``stem.2.ext``, ``stem.3.ext`` and so on."""
    if attempt == 1:
        return leaf
    stem, suffix = os.path.splitext(leaf)
    return "%s.%d%s" % (stem, attempt, suffix)


def _trashinfo(target: str) -> bytes:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    encoded = quote(os.fsencode(target), safe="/")
    return ("[Trash Info]\nPath=%s\nDeletionDate=%s\n" % (encoded, stamp)).encode("utf-8")


def _move_to_trash_dir(trash: str, target: str) -> Path:
    """Write ``info/<name>.trashinfo`` with O_EXCL, then rename into ``files/<name>``."""
    files_dir = os.path.join(trash, "files")
    info_dir = os.path.join(trash, "info")
    for folder in (trash, files_dir, info_dir):
        _ensure_private_dir(folder)
    leaf = os.path.basename(target)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    for attempt in range(1, 10000):
        name = _trash_name(leaf, attempt)
        info_path = os.path.join(info_dir, name + ".trashinfo")
        destination = os.path.join(files_dir, name)
        try:
            fd = os.open(info_path, flags, 0o600)
        except FileExistsError:
            continue
        except OSError as exc:
            raise TrashError("cannot write " + info_path + ": " + str(exc)) from exc
        try:
            if os.path.lexists(destination):
                os.close(fd)
                os.unlink(info_path)
                continue
            os.write(fd, _trashinfo(target))
            os.fsync(fd)
            os.close(fd)
            os.rename(target, destination)
        except OSError as exc:
            _unlink_quietly(info_path)
            raise TrashError("could not move " + target + " to the Trash: " + str(exc)) from exc
        return Path(destination)
    raise TrashError("could not find a free name in the Trash for " + target)


def _unlink_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _mount_trash_dir(target: str) -> Path:
    """Best guess of the per-drive Trash gio used for ``target``."""
    top = os.path.dirname(target)
    device = _device_of(top)
    while True:
        parent = os.path.dirname(top)
        if parent == top or _device_of(parent) != device:
            break
        top = parent
    uid = str(os.getuid())
    for candidate in (os.path.join(top, ".Trash", uid, "files"), os.path.join(top, ".Trash-" + uid, "files")):
        if os.path.isdir(candidate):
            return Path(candidate)
    return Path(os.path.join(top, ".Trash-" + uid, "files"))


# ----- os-release ------------------------------------------------------------


def parse_os_release(text: str) -> Dict[str, str]:
    """KEY=value pairs from os-release text, quotes and escapes removed."""
    values: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key.replace("_", "").isalnum():
            continue
        values[key] = _unquote(value.strip())
    return values


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        quote_char = value[0]
        inner = value[1:-1]
        if quote_char == "'":
            return inner
        out: List[str] = []
        index = 0
        while index < len(inner):
            ch = inner[index]
            if ch == "\\" and index + 1 < len(inner) and inner[index + 1] in '\\"$`':
                out.append(inner[index + 1])
                index += 2
                continue
            out.append(ch)
            index += 1
        return "".join(out)
    return value


@functools.lru_cache(maxsize=1)
def _linux_distro() -> DistroInfo:
    values: Dict[str, str] = {}
    for candidate in _OS_RELEASE_FILES:
        try:
            with open(candidate, "r", encoding="utf-8", errors="replace") as handle:
                values = parse_os_release(handle.read(65536))
            break
        except OSError:
            continue
    return DistroInfo(
        system="linux",
        id=values.get("ID", "").lower() or "linux",
        id_like=tuple(word.lower() for word in values.get("ID_LIKE", "").split()),
        version_id=values.get("VERSION_ID", ""),
        name=values.get("PRETTY_NAME", "") or values.get("NAME", "") or "Linux",
        build=values.get("BUILD_ID", ""),
        edition=values.get("VARIANT", ""),
        variant=values.get("VARIANT_ID", ""),
    )
