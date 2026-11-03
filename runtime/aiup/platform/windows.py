"""Windows platform: ctypes process and token queries, Recycle Bin, toasts.

Everything that talks to Win32 goes through ``_win32()``, which loads the
DLLs once and sets argument and return types. Nothing here sends a signal to
test a process: ``os.kill(pid, 0)`` ends the process on Windows.
"""

from __future__ import annotations

import base64
import functools
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

from aiup.platform import proc
from aiup.platform.base import (
    DistroInfo,
    Platform,
    ProcessTable,
    TrashError,
    executable_candidates,
    split_path,
    url_is_web,
)

_DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD"

_PROCESS_TERMINATE = 0x0001
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5
_TOKEN_QUERY = 0x0008
_TOKEN_ELEVATION = 20
_TH32CS_SNAPPROCESS = 0x00000002
_DRIVE_FIXED = 3
_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
_MAX_PATH = 260
_CREATE_NO_WINDOW = 0x08000000

_FO_DELETE = 0x0003
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040
_FOF_NOERRORUI = 0x0400

_BITBUCKET = r"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket"
_EXPLORER_POLICY = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
_CURRENT_VERSION = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"

# PowerShell's registered app id, so a toast needs no app of aiup's own.
_TOAST_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$title = [string]$env:AIUP_NOTIFY_TITLE
$body = [string]$env:AIUP_NOTIFY_BODY
try {
    $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
    $null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
    $t = [Security.SecurityElement]::Escape($title)
    $b = [Security.SecurityElement]::Escape($body)
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text>' + $t + '</text><text>' + $b + '</text></binding></visual></toast>')
    $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
    exit 0
} catch {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $icon = New-Object System.Windows.Forms.NotifyIcon
        $icon.Icon = [System.Drawing.SystemIcons]::Information
        $icon.BalloonTipTitle = $title
        $icon.BalloonTipText = $body
        $icon.Visible = $true
        $icon.ShowBalloonTip(5000)
        Start-Sleep -Seconds 6
        $icon.Dispose()
        exit 0
    } catch {
        exit 1
    }
}
"""

# Reads raw bytes from stdin so no console encoding is involved.
_CLIPBOARD_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$stdin = [Console]::OpenStandardInput()
$buffer = New-Object System.IO.MemoryStream
$stdin.CopyTo($buffer)
$text = [System.Text.Encoding]::UTF8.GetString($buffer.ToArray())
Set-Clipboard -Value $text
exit 0
"""

_RECYCLE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName Microsoft.VisualBasic
$p = [string]$env:AIUP_TRASH_PATH
$ui = [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs
$bin = [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
if ([System.IO.Directory]::Exists($p)) {
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p, $ui, $bin)
} else {
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p, $ui, $bin)
}
exit 0
"""


class WindowsPlatform(Platform):
    """Windows implementation of ``Platform``."""

    name = "windows"

    # ----- commands --------------------------------------------------------

    def which_all(self, command: str, path: Optional[str] = None) -> Tuple[str, ...]:
        """Matches in PATH order, trying each PATHEXT suffix; one per folder.

        The current folder is not searched (cmd.exe would search it first,
        which lets a file in any folder shadow a real command).
        """
        if not command or "\0" in command:
            return ()
        pathext = _pathext()
        if any(sep in command for sep in ("\\", "/", ":")):
            for name in executable_candidates(os.path.abspath(command), pathext):
                if _is_file(name):
                    return (name,)
            return ()
        found: List[str] = []
        names = executable_candidates(command, pathext)
        for entry in split_path(path):
            for name in names:
                candidate = os.path.join(entry, name)
                if _is_file(candidate):
                    found.append(candidate)
                    break
        return tuple(found)

    # ----- privileges and sessions ------------------------------------------

    def is_elevated(self) -> bool:
        """Token elevation of this process (TokenElevation), else IsUserAnAdmin."""
        api = _win32()
        if api is None:
            return False
        elevated = _token_elevated(api)
        if elevated is not None:
            return elevated
        try:
            return bool(api.shell32.IsUserAnAdmin())
        except (OSError, AttributeError):
            return False

    def desktop_session(self) -> bool:
        """False over SSH and in session 0 (services, some scheduled tasks)."""
        if any(os.environ.get(name) for name in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")):
            return False
        api = _win32()
        if api is None:
            return False
        import ctypes
        from ctypes import wintypes

        session = wintypes.DWORD(0)
        if not api.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
            return False
        return session.value != 0

    # ----- processes ---------------------------------------------------------

    def pid_alive(self, pid: int) -> bool:
        """OpenProcess and GetExitCodeProcess; a protected process counts as alive."""
        if pid <= 0:
            return False
        api = _win32()
        if api is None:
            return False
        import ctypes
        from ctypes import wintypes

        handle = api.kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ctypes.get_last_error() == _ERROR_ACCESS_DENIED  # type: ignore[attr-defined]
        try:
            code = wintypes.DWORD(0)
            if not api.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == _STILL_ACTIVE
        finally:
            api.kernel32.CloseHandle(handle)

    def process_table(self) -> Dict[int, Tuple[int, str]]:
        """CreateToolhelp32Snapshot: pid -> (parent pid, lower-case name without .exe)."""
        api = _win32()
        if api is None:
            return {}
        import ctypes

        table: Dict[int, Tuple[int, str]] = {}
        snapshot = api.kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == api.invalid_handle:
            return table
        try:
            entry = api.PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(api.PROCESSENTRY32W)
            ok = api.kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                table[int(entry.th32ProcessID)] = (int(entry.th32ParentProcessID), _process_name(entry.szExeFile))
                ok = api.kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            api.kernel32.CloseHandle(snapshot)
        return table

    def _normalize_names(self, names: Iterable[str]) -> FrozenSet[str]:
        return frozenset(_process_name(name) for name in names if name)

    def _descendants_in(self, pid: int, table: ProcessTable) -> Tuple[int, ...]:
        """Descendants, skipping children older than their recorded parent.

        Windows keeps a dead parent's pid in its children's records, and the
        pid can be reused by an unrelated process, so a child created before
        its "parent" is not really below it.
        """
        children: Dict[int, List[int]] = {}
        for child, row in table.items():
            if child != row[0]:
                children.setdefault(row[0], []).append(child)
        times: Dict[int, Optional[int]] = {}
        found: List[int] = []
        seen = {pid}
        queue = [pid]
        while queue:
            parent = queue.pop(0)
            for child in children.get(parent, ()):
                if child in seen or not _created_after(child, parent, times):
                    continue
                seen.add(child)
                found.append(child)
                queue.append(child)
        return tuple(found)

    def kill_tree(self, pid: int, grace: float = 2.0) -> None:
        """taskkill /T /F, then TerminateProcess on anything left. ``grace`` is unused.

        Creation times are recorded before taskkill runs. A pid whose process
        has since exited can be reused at once, so a leftover pid is ended
        only when its process still has the recorded creation time.
        """
        me = os.getpid()
        if pid <= 4 or pid == me:
            return
        tree = [p for p in (pid,) + self.descendants(pid) if p != me]
        born = {target: _creation_time(target) for target in tree}
        _taskkill(pid)
        api = _win32()
        if api is None:
            return
        for target in reversed(tree):
            created = born.get(target)
            if created is not None:
                _terminate(api, target, created)

    # ----- desktop ---------------------------------------------------------

    def notify(self, title: str, body: str) -> bool:
        """Toast through Windows PowerShell, then a tray balloon, then msg.exe."""
        body = body or title
        argv = _powershell_argv(_TOAST_SCRIPT)
        env = dict(windows_powershell_env(argv[0]))
        env.update({"AIUP_NOTIFY_TITLE": title, "AIUP_NOTIFY_BODY": body})
        result = proc.run_read(argv, timeout=30.0, env=env)
        if result.ok:
            return True
        msg = os.path.join(_system32(), "msg.exe")
        user = os.environ.get("USERNAME", "")
        if user and os.path.isfile(msg):
            return proc.run_read([msg, user, "/TIME:30", title + ": " + body], timeout=10.0).ok
        return False

    def trash(self, path: str) -> Path:
        """Recycle Bin through SHFileOperationW with FOF_ALLOWUNDO.

        Before anything moves, aiup checks that the drive is a fixed drive
        with a Recycle Bin, that neither the bin's settings nor Group Policy
        make it delete right away, and that the item fits the smallest size
        limit set. Windows deletes permanently when one of those fails, so
        each one is refused here instead. Folder junctions are resolved first
        so the checks look at the drive that really holds the item.
        Returns the drive's ``$Recycle.Bin`` folder.
        """
        target = _resolve_parent(os.path.abspath(path))
        root = _check_trash_target(target)
        api = _win32()
        if api is None:
            raise TrashError("cannot reach the Windows shell to use the Recycle Bin; nothing was moved")
        _check_recycle_bin(api, root, target)
        try:
            _shell_recycle(api, target)
        except TrashError:
            raise
        except (OSError, AttributeError, TypeError, ValueError):
            _powershell_recycle(target)
        if os.path.lexists(target):
            raise TrashError("Windows did not move " + target + " to the Recycle Bin")
        return Path(root) / "$Recycle.Bin"

    def open_url(self, url: str) -> bool:
        """os.startfile with the URL (the default browser)."""
        if not url_is_web(url):
            return False
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            return False
        try:
            startfile(url)
        except OSError:
            return False
        return True

    def copy_text(self, text: str) -> bool:
        """Set-Clipboard through Windows PowerShell, then clip.exe; text on stdin."""
        argv = _powershell_argv(_CLIPBOARD_SCRIPT)
        result = proc.run_read(argv, timeout=15.0, env=windows_powershell_env(argv[0]),
                               input_bytes=text.encode("utf-8"))
        if result.ok:
            return True
        clip = os.path.join(_system32(), "clip.exe")
        if os.path.isfile(clip):
            data = b"\xff\xfe" + text.encode("utf-16-le")
            return proc.run_feed([clip], data, timeout=10.0) == 0
        return False

    def distro(self) -> DistroInfo:
        """Windows version, build with update revision, edition and product name."""
        return _windows_distro()


# ----- Win32 bindings ------------------------------------------------------


class _Win32:
    """Loaded DLLs, structures and the INVALID_HANDLE_VALUE constant."""

    def __init__(self, kernel32: Any, advapi32: Any, shell32: Any, structs: Dict[str, Any], invalid: Any) -> None:
        self.kernel32 = kernel32
        self.advapi32 = advapi32
        self.shell32 = shell32
        self.PROCESSENTRY32W = structs["PROCESSENTRY32W"]
        self.SHFILEOPSTRUCTW = structs["SHFILEOPSTRUCTW"]
        self.SHQUERYRBINFO = structs["SHQUERYRBINFO"]
        self.FILETIME = structs["FILETIME"]
        self.invalid_handle = invalid


@functools.lru_cache(maxsize=1)
def _win32() -> Optional[_Win32]:
    """Win32 functions with types set, or None when ctypes cannot load them."""
    if sys.platform != "win32":
        return None
    try:
        return _load_win32()
    except (ImportError, OSError, AttributeError):
        return None


def _load_win32() -> _Win32:
    import ctypes
    from ctypes import wintypes

    structs = _structs()
    k = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    a = ctypes.WinDLL("advapi32", use_last_error=True)  # type: ignore[attr-defined]
    s = ctypes.WinDLL("shell32", use_last_error=True)  # type: ignore[attr-defined]
    handle, dword, boolean = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL
    pdword = ctypes.POINTER(dword)
    pft = ctypes.POINTER(structs["FILETIME"])
    _sig(k.OpenProcess, [dword, boolean, dword], handle)
    _sig(k.CloseHandle, [handle], boolean)
    _sig(k.GetExitCodeProcess, [handle, pdword], boolean)
    _sig(k.GetProcessTimes, [handle, pft, pft, pft, pft], boolean)
    _sig(k.TerminateProcess, [handle, wintypes.UINT], boolean)
    _sig(k.GetCurrentProcess, [], handle)
    _sig(k.CreateToolhelp32Snapshot, [dword, dword], handle)
    _sig(k.Process32FirstW, [handle, ctypes.POINTER(structs["PROCESSENTRY32W"])], boolean)
    _sig(k.Process32NextW, [handle, ctypes.POINTER(structs["PROCESSENTRY32W"])], boolean)
    _sig(k.ProcessIdToSessionId, [dword, pdword], boolean)
    _sig(k.GetDriveTypeW, [wintypes.LPCWSTR], wintypes.UINT)
    _sig(k.GetVolumeNameForVolumeMountPointW, [wintypes.LPCWSTR, wintypes.LPWSTR, dword], boolean)
    pull = ctypes.POINTER(ctypes.c_ulonglong)
    _sig(k.GetDiskFreeSpaceExW, [wintypes.LPCWSTR, pull, pull, pull], boolean)
    _sig(a.OpenProcessToken, [handle, dword, ctypes.POINTER(handle)], boolean)
    _sig(a.GetTokenInformation, [handle, ctypes.c_int, ctypes.c_void_p, dword, pdword], boolean)
    _sig(s.SHFileOperationW, [ctypes.POINTER(structs["SHFILEOPSTRUCTW"])], ctypes.c_int)
    _sig(s.SHQueryRecycleBinW, [wintypes.LPCWSTR, ctypes.POINTER(structs["SHQUERYRBINFO"])], ctypes.c_long)
    _sig(s.IsUserAnAdmin, [], boolean)
    invalid = ctypes.c_void_p(-1).value
    return _Win32(k, a, s, structs, invalid)


def _sig(function: Any, argtypes: List[Any], restype: Any) -> None:
    function.argtypes = argtypes
    function.restype = restype


def _structs() -> Dict[str, Any]:
    """ctypes structures, built only on Windows. shellapi.h packs to 1 byte on 32-bit."""
    import ctypes
    from ctypes import wintypes

    shell_pack = 1 if ctypes.sizeof(ctypes.c_void_p) == 4 else 8

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * _MAX_PATH),
        ]

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _pack_ = shell_pack
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    class SHQUERYRBINFO(ctypes.Structure):
        _pack_ = shell_pack
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("i64Size", ctypes.c_longlong),
            ("i64NumItems", ctypes.c_longlong),
        ]

    return {
        "PROCESSENTRY32W": PROCESSENTRY32W,
        "SHFILEOPSTRUCTW": SHFILEOPSTRUCTW,
        "SHQUERYRBINFO": SHQUERYRBINFO,
        "FILETIME": wintypes.FILETIME,
    }


# ----- commands and processes ------------------------------------------------


def _pathext() -> Tuple[str, ...]:
    raw = os.environ.get("PATHEXT", "") or _DEFAULT_PATHEXT
    return tuple(ext.strip() for ext in raw.split(";") if ext.strip().startswith("."))


def _is_file(candidate: str) -> bool:
    """A file, or an app execution alias (a reparse point that stat may refuse)."""
    if os.path.isfile(candidate):
        return True
    return os.path.lexists(candidate) and not os.path.isdir(candidate)


def _process_name(name: str) -> str:
    base = os.path.basename(str(name)).lower()
    return base[:-4] if base.endswith(".exe") else base


def _token_elevated(api: _Win32) -> Optional[bool]:
    import ctypes
    from ctypes import wintypes

    token = wintypes.HANDLE()
    if not api.advapi32.OpenProcessToken(api.kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)):
        return None
    try:
        value = wintypes.DWORD(0)
        size = wintypes.DWORD(0)
        if not api.advapi32.GetTokenInformation(
            token, _TOKEN_ELEVATION, ctypes.byref(value), ctypes.sizeof(value), ctypes.byref(size)
        ):
            return None
        return value.value != 0
    finally:
        api.kernel32.CloseHandle(token)


def _creation_time(pid: int) -> Optional[int]:
    """Process creation time as a FILETIME integer, or None when unreadable."""
    api = _win32()
    if api is None:
        return None
    handle = api.kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        return _handle_creation_time(api, handle)
    finally:
        api.kernel32.CloseHandle(handle)


def _handle_creation_time(api: _Win32, handle: Any) -> Optional[int]:
    import ctypes

    created, exited, kernel, user = api.FILETIME(), api.FILETIME(), api.FILETIME(), api.FILETIME()
    if not api.kernel32.GetProcessTimes(
        handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)
    ):
        return None
    return (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)


def _created_after(child: int, parent: int, cache: Dict[int, Optional[int]]) -> bool:
    """False only when both times are known and the child is older."""
    for pid in (child, parent):
        if pid not in cache:
            cache[pid] = _creation_time(pid)
    child_time, parent_time = cache[child], cache[parent]
    if child_time is None or parent_time is None:
        return True
    return child_time >= parent_time


def _system32() -> str:
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    return os.path.join(root, "System32")


def _taskkill(pid: int) -> None:
    taskkill = os.path.join(_system32(), "taskkill.exe")
    if not os.path.isfile(taskkill):
        return
    try:
        subprocess.run(
            [taskkill, "/T", "/F", "/PID", str(pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return


def _terminate(api: _Win32, pid: int, created: int) -> None:
    """End ``pid`` only if it is still the process created at ``created``.

    The open handle pins the process, so the check and the kill see the same
    one. An exited process keeps its times while a handle is open, and
    TerminateProcess on it just fails.
    """
    handle = api.kernel32.OpenProcess(_PROCESS_TERMINATE | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return
    try:
        if _handle_creation_time(api, handle) == created:
            api.kernel32.TerminateProcess(handle, 1)
    finally:
        api.kernel32.CloseHandle(handle)


def _powershell_argv(script: str) -> List[str]:
    """Windows PowerShell 5.1 running a fixed script. Data goes in env or stdin only."""
    exe = os.path.join(_system32(), "WindowsPowerShell", "v1.0", "powershell.exe")
    if not os.path.isfile(exe):
        exe = "powershell"
    encoded = base64.b64encode(script.strip().encode("utf-16-le")).decode("ascii")
    return [exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]


def windows_powershell_env(exe: str) -> Dict[str, str]:
    """Environment changes that let Windows PowerShell 5.1 load its own modules.

    PowerShell 7 puts its module folders first in PSModulePath, and a child
    started from it (aiup, then powershell.exe) inherits them, so 5.1 can try
    to load modules built for 7 and fail. For 5.1 this drops every
    ``PowerShell`` folder (``WindowsPowerShell`` folders stay). Empty for
    any other executable, or when nothing needs to change.
    """
    parts = [part.lower() for part in os.path.normpath(exe).replace("/", "\\").split("\\")]
    if "windowspowershell" not in parts:
        return {}
    current = os.environ.get("PSModulePath", "")
    entries = [entry for entry in current.split(os.pathsep) if entry.strip()]
    kept = [entry for entry in entries if not _is_powershell7_folder(entry)]
    if len(kept) == len(entries):
        return {}
    if not kept:
        kept = [os.path.join(_system32(), "WindowsPowerShell", "v1.0", "Modules")]
    return {"PSModulePath": os.pathsep.join(kept)}


def _is_powershell7_folder(entry: str) -> bool:
    parts = [part.lower() for part in os.path.normpath(entry.strip()).replace("/", "\\").split("\\")]
    return "powershell" in parts


# ----- Recycle Bin -----------------------------------------------------------


def _resolve_parent(target: str) -> str:
    """``target`` with its folder's links and junctions resolved.

    A junction in the folder path can put the item on another drive, and the
    checks below must look at the drive that really holds it. The item itself
    is not resolved: a link is refused, never followed.
    """
    folder, name = os.path.split(target)
    if not name:
        return target
    try:
        return os.path.join(os.path.realpath(folder), name)
    except (OSError, ValueError):
        return target


def _check_trash_target(target: str) -> str:
    """Refuse targets the Recycle Bin cannot take safely; return the drive root."""
    if not os.path.lexists(target):
        raise TrashError(target + " does not exist")
    if target.startswith("\\\\"):
        raise TrashError(target + " is on a network or device path, which has no Recycle Bin. Nothing was moved.")
    if len(target) >= _MAX_PATH:
        raise TrashError(target + " is too long a path for the Recycle Bin. Nothing was moved.")
    drive, _rest = os.path.splitdrive(target)
    if len(drive) != 2 or drive[1] != ":":
        raise TrashError(target + " is not on a lettered drive. Nothing was moved.")
    try:
        attributes = int(getattr(os.lstat(target), "st_file_attributes", 0))
    except OSError as exc:
        raise TrashError("cannot read " + target + ": " + str(exc)) from exc
    if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
        raise TrashError(target + " is a link or junction. Remove it by hand; aiup will not risk its target.")
    _refuse_protected(target, drive + "\\")
    return drive + "\\"


def _refuse_protected(target: str, root: str) -> None:
    """Never recycle a drive root, the profile, Windows, or a folder holding them."""
    protected = [root]
    for name in ("USERPROFILE", "SystemRoot", "LOCALAPPDATA", "APPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(name, "")
        if value:
            protected.append(value)
    norm_target = os.path.normcase(os.path.normpath(target))
    for item in protected:
        norm_item = os.path.normcase(os.path.normpath(item))
        if norm_target == norm_item or norm_item.startswith(norm_target.rstrip("\\") + "\\"):
            raise TrashError("refusing to move " + target + " to the Recycle Bin")


def _check_recycle_bin(api: _Win32, root: str, target: str) -> None:
    """Raise unless ``target`` will land in the Recycle Bin, not be deleted."""
    import ctypes

    if api.kernel32.GetDriveTypeW(root) != _DRIVE_FIXED:
        raise TrashError(root + " is not a fixed drive, so it has no Recycle Bin. Nothing was moved.")
    info = api.SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(api.SHQUERYRBINFO)
    if api.shell32.SHQueryRecycleBinW(root, ctypes.byref(info)) != 0:
        raise TrashError(root + " has no Recycle Bin. Nothing was moved.")
    nuke, max_mb = _bitbucket_policy(api, root)
    percent = _policy_bin_percent()
    if nuke or _policy_no_recycle() or percent == 0:
        raise TrashError(
            "The Recycle Bin on " + root + " is set to delete files right away. Nothing was moved."
        )
    limits: List[int] = []
    if max_mb is not None:
        limits.append(max_mb * 1024 * 1024)
    total = _drive_total(api, root)
    if percent is not None:
        if total is None:
            raise TrashError("cannot read the size of " + root + ". Nothing was moved.")
        limits.append(total * percent // 100)
    if not limits and total is not None:
        limits.append(total // 20)  # assume 5 percent when nothing is stored (conservative)
    if not limits:
        raise TrashError("cannot read the Recycle Bin size limit on " + root + ". Nothing was moved.")
    # Keep a margin: Windows may count a little more than the file sizes.
    limit = min(limits)
    limit -= limit // 20
    if _tree_size(target, limit) > limit:
        raise TrashError(
            target + " is larger than the Recycle Bin on " + root + " can hold, and Windows would delete it "
            "for good. Nothing was moved."
        )


def _policy_values(name: str) -> List[Any]:
    """One Explorer policy value as set for the machine and for the user."""
    try:
        import winreg
    except ImportError:
        return []
    found: List[Any] = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        values = _read_registry(hive, _EXPLORER_POLICY, (name,))
        if name in values:
            found.append(values[name])
    return found


def _policy_no_recycle() -> bool:
    """Group Policy "Do not move deleted files to the Recycle Bin" (NoRecycleFiles)."""
    return any(isinstance(value, int) and value != 0 for value in _policy_values("NoRecycleFiles"))


def _policy_bin_percent() -> Optional[int]:
    """Group Policy "Maximum allowed Recycle Bin size" in percent, smallest set value."""
    percents = [value for value in _policy_values("RecycleBinSize") if isinstance(value, int) and 0 <= value <= 100]
    return min(percents) if percents else None


def _bitbucket_policy(api: _Win32, root: str) -> Tuple[bool, Optional[int]]:
    """(delete right away, size limit in MB) from the per-drive Recycle Bin settings."""
    try:
        import winreg
    except ImportError:
        return False, None
    guid = _volume_guid(api, root)
    keys = [_BITBUCKET + "\\Volume\\" + guid] if guid else []
    keys.append(_BITBUCKET)
    for key_path in keys:
        values = _read_registry(winreg.HKEY_CURRENT_USER, key_path, ("NukeOnDelete", "MaxCapacity"))
        if values:
            nuke = values.get("NukeOnDelete") == 1
            capacity = values.get("MaxCapacity")
            return nuke, capacity if isinstance(capacity, int) and capacity > 0 else None
    return False, None


def _volume_guid(api: _Win32, root: str) -> str:
    import ctypes

    buffer = ctypes.create_unicode_buffer(64)
    if not api.kernel32.GetVolumeNameForVolumeMountPointW(root, buffer, 64):
        return ""
    name = buffer.value
    start = name.find("{")
    end = name.find("}", start)
    return name[start:end + 1] if start >= 0 and end > start else ""


def _drive_total(api: _Win32, root: str) -> Optional[int]:
    """Size of the drive in bytes, or None when unreadable."""
    import ctypes

    free, total, total_free = ctypes.c_ulonglong(0), ctypes.c_ulonglong(0), ctypes.c_ulonglong(0)
    if not api.kernel32.GetDiskFreeSpaceExW(root, ctypes.byref(free), ctypes.byref(total), ctypes.byref(total_free)):
        return None
    return int(total.value) or None


def _tree_size(target: str, stop_after: int) -> int:
    """Bytes under ``target`` without following links; stops counting past ``stop_after``."""
    try:
        info = os.lstat(target)
    except OSError:
        return 0
    if not os.path.isdir(target):
        return int(info.st_size)
    total = 0
    pending = [target]
    while pending:
        folder = pending.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            reparse = int(getattr(stat, "st_file_attributes", 0)) & _FILE_ATTRIBUTE_REPARSE_POINT
            if entry.is_dir(follow_symlinks=False) and not reparse:
                pending.append(entry.path)
            else:
                total += int(stat.st_size)
            if total > stop_after:
                return total
    return total


def _shell_recycle(api: _Win32, target: str) -> None:
    """SHFileOperationW FO_DELETE with FOF_ALLOWUNDO and no UI."""
    import ctypes
    from ctypes import wintypes

    source = ctypes.create_unicode_buffer(target + "\0")  # double NUL ends the list
    operation = api.SHFILEOPSTRUCTW()
    operation.hwnd = None
    operation.wFunc = _FO_DELETE
    operation.pFrom = ctypes.cast(source, wintypes.LPCWSTR)
    operation.pTo = None
    operation.fFlags = _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT | _FOF_NOERRORUI
    code = api.shell32.SHFileOperationW(ctypes.byref(operation))
    if code != 0:
        raise TrashError("Windows could not move %s to the Recycle Bin (error 0x%x)" % (target, code & 0xFFFFFFFF))
    if operation.fAnyOperationsAborted:
        raise TrashError("moving " + target + " to the Recycle Bin was cancelled")


def _powershell_recycle(target: str) -> None:
    """Fallback through Microsoft.VisualBasic.FileIO, path passed in the environment."""
    argv = _powershell_argv(_RECYCLE_SCRIPT)
    env = dict(windows_powershell_env(argv[0]))
    env["AIUP_TRASH_PATH"] = target
    result = proc.run_read(argv, timeout=120.0, env=env)
    if not result.ok:
        raise TrashError("Windows PowerShell could not move " + target + " to the Recycle Bin")


# ----- version ---------------------------------------------------------------


def _read_registry(hive: Any, key_path: str, names: Tuple[str, ...]) -> Dict[str, Any]:
    """The named values that exist under one key (64-bit view), or {}."""
    try:
        import winreg
    except ImportError:
        return {}
    values: Dict[str, Any] = {}
    try:
        with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            for name in names:
                try:
                    values[name] = winreg.QueryValueEx(key, name)[0]
                except OSError:
                    continue
    except OSError:
        return {}
    return values


@functools.lru_cache(maxsize=1)
def _windows_distro() -> DistroInfo:
    version = sys.getwindowsversion()  # type: ignore[attr-defined]
    major, minor, build = int(version.major), int(version.minor), int(version.build)
    try:
        import winreg

        values = _read_registry(
            winreg.HKEY_LOCAL_MACHINE,
            _CURRENT_VERSION,
            ("ProductName", "EditionID", "DisplayVersion", "ReleaseId", "UBR", "InstallationType"),
        )
    except ImportError:
        values = {}
    product = str(values.get("ProductName", "") or "Windows")
    installation = str(values.get("InstallationType", ""))
    # ProductName still says "Windows 10" on Windows 11 client builds.
    if installation == "Client" and build >= 22000 and product.startswith("Windows 10"):
        product = "Windows 11" + product[len("Windows 10"):]
    release = str(values.get("DisplayVersion", "") or values.get("ReleaseId", ""))
    ubr = values.get("UBR")
    return DistroInfo(
        system="windows",
        id="windows",
        id_like=(),
        version_id="%d.%d.%d" % (major, minor, build),
        name=(product + " " + release).strip(),
        build="%d.%d" % (build, ubr) if isinstance(ubr, int) else str(build),
        edition=str(values.get("EditionID", "")),
        variant=installation,
    )
