"""Windows Uninstall keys (Programs and Features), read in-process with winreg.

Research section 5.1. Three views: HKLM 64-bit, HKLM 32-bit (WOW6432Node,
opened with ``KEY_WOW64_32KEY``) and HKCU. System components, updates and
hotfixes, and entries without a name are left out. The uninstall command is
untrusted text: it is parsed into argv here and never passed to a shell, and
an uninstaller that is not an existing absolute file is not offered.
"""

from __future__ import annotations

import ntpath
import os
import re
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, Tuple

from aiup.detect import files
from aiup.detect.items import InventoryItem, Owner, det_id
from aiup.detect.sources import DetectionSource, register

if TYPE_CHECKING:
    from aiup.engine.context import Context

UNINSTALL = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
_GUID = re.compile(r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}")
_SYSTEM_TOOLS = ("msiexec.exe", "rundll32.exe")
_MAX_SUBKEYS = 5000


@dataclass(frozen=True)
class ArpEntry:
    """One Uninstall entry, after filtering."""

    view: str              # "HKLM64" | "HKLM32" | "HKCU"
    key: str
    name: str
    version: str
    publisher: str
    install_location: str
    display_icon: str
    uninstall: str
    quiet_uninstall: str
    windows_installer: bool
    no_remove: bool
    url: str

    @property
    def id(self) -> str:
        return det_id("arp", self.view + ":" + self.key)

    @property
    def scope(self) -> str:
        return "user" if self.view == "HKCU" else "system"


# ----- reading the registry ------------------------------------------------------------------------


def _views() -> List[Tuple[str, object, int]]:
    import winreg  # Windows only

    return [
        ("HKLM64", winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
        ("HKLM32", winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
        ("HKCU", winreg.HKEY_CURRENT_USER, 0),
    ]


def _values(key: object) -> Dict[str, object]:
    import winreg

    out: Dict[str, object] = {}
    try:
        count = winreg.QueryInfoKey(key)[1]
    except OSError:
        return out
    for index in range(min(count, 512)):
        try:
            name, data, kind = winreg.EnumValue(key, index)
        except OSError:
            break
        if kind == winreg.REG_EXPAND_SZ and isinstance(data, str):
            try:
                data = winreg.ExpandEnvironmentStrings(data)
            except OSError:
                pass
        out[name] = data
    return out


def _text(values: Mapping[str, object], name: str) -> str:
    value = values.get(name)
    return value.strip() if isinstance(value, str) else ""


def _flag(values: Mapping[str, object], name: str) -> bool:
    value = values.get(name)
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip() not in ("", "0")
    return False


def read_entries(ctx: "Context") -> List[ArpEntry]:
    """Every listed Uninstall entry, the 64-bit and 32-bit copies of one product once."""
    if not files.is_windows(ctx):
        return []
    try:
        import winreg
    except ImportError:
        return []
    out: List[ArpEntry] = []
    seen: Dict[Tuple[str, str], str] = {}
    for view, root, flag in _views():
        try:
            parent = winreg.OpenKey(root, UNINSTALL, 0, winreg.KEY_READ | flag)
        except OSError:
            continue
        with parent:
            try:
                count = winreg.QueryInfoKey(parent)[0]
            except OSError:
                continue
            for index in range(min(count, _MAX_SUBKEYS)):
                try:
                    sub = winreg.EnumKey(parent, index)
                    handle = winreg.OpenKey(parent, sub, 0, winreg.KEY_READ | flag)
                except OSError:
                    continue
                with handle:
                    values = _values(handle)
                entry = _entry(view, sub, values)
                if entry is None:
                    continue
                twin = (entry.key.lower(), entry.name.lower())
                location = files.norm(entry.install_location) if entry.install_location else ""
                if twin in seen and seen[twin] == location:
                    continue
                seen[twin] = location
                out.append(entry)
    return out


def _entry(view: str, key: str, values: Mapping[str, object]) -> Optional[ArpEntry]:
    name = _text(values, "DisplayName")
    if not name or _flag(values, "SystemComponent"):
        return None
    if _text(values, "ParentKeyName") or _text(values, "ReleaseType"):
        return None
    return ArpEntry(
        view=view, key=key, name=name, version=_text(values, "DisplayVersion"),
        publisher=_text(values, "Publisher"),
        install_location=_clean_folder(_text(values, "InstallLocation")),
        display_icon=_text(values, "DisplayIcon"), uninstall=_text(values, "UninstallString"),
        quiet_uninstall=_text(values, "QuietUninstallString"),
        windows_installer=_flag(values, "WindowsInstaller"), no_remove=_flag(values, "NoRemove"),
        url=_text(values, "URLInfoAbout") or _text(values, "HelpLink"),
    )


def _clean_folder(text: str) -> str:
    folder = text.strip().strip('"').strip()
    while len(folder) > 3 and folder.endswith(("\\", "/")):
        folder = folder[:-1]
    return folder


_ENTRIES_LOCK = threading.Lock()


def entries(ctx: "Context") -> List[ArpEntry]:
    """:func:`read_entries`, once per process (owner lookups share it with the source)."""
    key = "aiup.detect.arp-entries"
    with _ENTRIES_LOCK:
        done = ctx.cache.recall(key)
        if isinstance(done, list):
            return done
        found = read_entries(ctx)
        ctx.cache.remember(key, found)
        return found


# ----- install folders ---------------------------------------------------------------------------------


def _generic_folders(ctx: "Context") -> List[str]:
    names = ("SystemRoot", "ProgramData", "ProgramFiles", "ProgramFiles(x86)", "CommonProgramFiles",
             "CommonProgramFiles(x86)", "LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP")
    out = [files.norm(files.env_get(ctx, n)) for n in names if files.env_get(ctx, n)]
    data = files.env_get(ctx, "ProgramData")
    if data:
        out.append(files.norm(ntpath.join(data, "Package Cache")))
    local = files.env_get(ctx, "LOCALAPPDATA")
    if local:
        out.append(files.norm(ntpath.join(local, "Programs")))
        out.append(files.norm(ntpath.join(local, "Package Cache")))
    return out


def _usable(ctx: "Context", folder: str, generic: Sequence[str]) -> bool:
    if not folder or not ntpath.isabs(folder):
        return False
    key = files.norm(folder)
    if key in generic:
        return False
    windows_dir = files.env_get(ctx, "SystemRoot")
    if windows_dir and files.inside(folder, windows_dir):
        return False
    drive, rest = ntpath.splitdrive(folder)
    return bool(drive) and rest.strip("\\/") != ""


def _icon_folder(icon: str) -> str:
    text = icon.strip().strip('"')
    text = re.sub(r",\s*-?\d+$", "", text).strip().strip('"')
    return ntpath.dirname(text) if text.lower().endswith((".exe", ".ico", ".dll")) else ""


def folders_of(ctx: "Context", entry: ArpEntry, generic: Sequence[str]) -> Tuple[str, ...]:
    """Install folders: InstallLocation, then the icon's and uninstaller's folders."""
    out: List[str] = []
    candidates = [entry.install_location, _icon_folder(entry.display_icon)]
    argv = parse_command(entry.uninstall)
    if argv and ntpath.basename(argv[0]).lower() not in _SYSTEM_TOOLS:
        candidates.append(ntpath.dirname(argv[0]))
    for folder in candidates:
        if _usable(ctx, folder, generic) and folder not in out:
            out.append(folder)
    return tuple(out)


def entry_for_path(ctx: "Context", path: str) -> Optional[ArpEntry]:
    """The entry whose install folder is the nearest parent of ``path``."""
    index_key = "aiup.detect.arp-folders"
    index = ctx.cache.recall(index_key)
    if not isinstance(index, dict):
        generic = _generic_folders(ctx)
        index = {}
        for entry in entries(ctx):
            for folder in folders_of(ctx, entry, generic):
                index.setdefault(files.norm(folder), entry)
        ctx.cache.remember(index_key, index)
    current = files.norm(path)
    for _ in range(16):
        parent = ntpath.dirname(current)
        if parent == current:
            return None
        current = parent
        found = index.get(current)
        if isinstance(found, ArpEntry):
            return found
    return None


# ----- uninstall commands --------------------------------------------------------------------------------


def _split_args(text: str) -> List[str]:
    """Arguments split on spaces outside double quotes (the quotes removed)."""
    out: List[str] = []
    current: List[str] = []
    quoted = False
    started = False
    for char in text:
        if char == '"':
            quoted = not quoted
            started = True
        elif char.isspace() and not quoted:
            if started:
                out.append("".join(current))
                current, started = [], False
        else:
            current.append(char)
            started = True
    if started:
        out.append("".join(current))
    return out


def _system_root() -> str:
    return os.environ.get("SystemRoot") or os.environ.get("windir") or "C:\\Windows"


def parse_command(text: str) -> Tuple[str, ...]:
    """An uninstall command line as argv; () when the program cannot be found safely."""
    line = text.strip()
    if not line:
        return ()
    if line.startswith('"'):
        end = line.find('"', 1)
        if end < 0:
            return ()
        program, rest = line[1:end], line[end + 1:]
    else:
        lowered = line.lower()
        cut = lowered.find(".exe")
        if cut < 0:
            parts = line.split(None, 1)
            program, rest = parts[0], parts[1] if len(parts) > 1 else ""
        else:
            program, rest = line[:cut + 4], line[cut + 4:]
    program = program.strip()
    base = ntpath.basename(program).lower()
    if not ntpath.isabs(program):
        if base in _SYSTEM_TOOLS or base + ".exe" in _SYSTEM_TOOLS:
            program = ntpath.join(_system_root(), "System32", base if base.endswith(".exe") else base + ".exe")
        else:
            return ()
    return (program,) + tuple(_split_args(rest))


def installer_kind(entry: ArpEntry, argv: Sequence[str]) -> str:
    base = ntpath.basename(argv[0]).lower() if argv else ""
    if base == "msiexec.exe" or (entry.windows_installer and _GUID.fullmatch(entry.key)):
        return "msi"
    if entry.key.lower().endswith("_is1"):
        return "inno"
    if base == "update.exe" and any(a.lower() == "--uninstall" for a in argv[1:]):
        return "squirrel"
    if base.startswith("uninst"):
        return "nsis"
    return "exe"


def _runnable(program: str) -> bool:
    """An existing ``.exe``. Windows runs ``.bat`` and ``.cmd`` files through cmd.exe,
    which reparses the arguments, so those stay a manual step."""
    return program.lower().endswith(".exe") and os.path.isfile(program)


def remove_commands(entry: ArpEntry) -> Tuple[Tuple[str, ...], Tuple[str, ...], str]:
    """``(interactive argv, quiet argv, installer kind)``; empty argv when not offered."""
    if entry.no_remove:
        return (), (), ""
    argv = parse_command(entry.uninstall)
    kind = installer_kind(entry, argv)
    if kind == "msi":
        guid = _GUID.search(entry.uninstall or "") or _GUID.fullmatch(entry.key)
        if guid is None:
            return (), (), kind
        msiexec = argv[0] if argv and ntpath.basename(argv[0]).lower() == "msiexec.exe" else \
            ntpath.join(_system_root(), "System32", "msiexec.exe")
        return (msiexec, "/x", guid.group(0)), (msiexec, "/x", guid.group(0), "/qn", "/norestart"), kind
    if argv and not _runnable(argv[0]):
        argv = ()
    quiet = parse_command(entry.quiet_uninstall)
    if quiet and not _runnable(quiet[0]):
        quiet = ()
    if not quiet and argv:
        lowered = [a.lower() for a in argv[1:]]
        if kind == "inno":
            quiet = argv + tuple(f for f in ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
                                 if f.lower() not in lowered)
        elif kind == "nsis" and "/s" not in lowered:
            quiet = argv + ("/S",)
        elif kind == "squirrel" and "-s" not in lowered:
            quiet = argv + ("-s",)
    return argv, quiet, kind


def to_item(ctx: "Context", entry: ArpEntry, generic: Sequence[str]) -> InventoryItem:
    argv, quiet, kind = remove_commands(entry)
    folders = folders_of(ctx, entry, generic)
    guidance = "Update it with the app's own updater or from the vendor's site."
    if entry.no_remove:
        guidance += " Its entry says it cannot be removed here."
    elif not argv and not quiet:
        guidance += " Its uninstaller was not found."
    facts: List[Tuple[str, str]] = [("view", entry.view), ("key", entry.key), ("installer", kind)]
    if entry.publisher:
        facts.append(("publisher", entry.publisher))
    if entry.install_location:
        facts.append(("install_location", entry.install_location))
    if argv and ntpath.basename(argv[0]).lower() not in _SYSTEM_TOOLS:
        facts.append(("uninstaller", ntpath.basename(argv[0])))
    return InventoryItem(
        id=entry.id, name=entry.name, version=entry.version, population="detected", source="arp",
        paths=folders, owner=Owner(manager="arp", package=entry.view + ":" + entry.key, confidence="exact",
                                   label="Programs and Features", evidence="Uninstall key"),
        kind="uninstall-entry", scope=entry.scope, confidence="exact", evidence="Uninstall key",
        manual=True, self_updates=kind == "squirrel", needs_admin=entry.scope == "system",
        docs=entry.url if entry.url.lower().startswith("https://") else "", guidance=guidance,
        description=entry.publisher, remove_argv=argv, quiet_remove_argv=quiet, facts=tuple(facts),
    )


class ArpSource(DetectionSource):
    name = "arp"
    oses = frozenset(("windows",))
    cost = "cheap"

    def fingerprint(self, ctx: "Context") -> str:
        try:
            import winreg
        except ImportError:
            return ""
        parts: List[str] = []
        for view, root, flag in _views():
            try:
                with winreg.OpenKey(root, UNINSTALL, 0, winreg.KEY_READ | flag) as key:
                    subkeys, values, written = winreg.QueryInfoKey(key)
                    parts.append("{}={}:{}:{}".format(view, subkeys, values, written))
            except OSError:
                parts.append(view + "=-")
        return files.stamp(parts)

    def read(self, ctx: "Context") -> Sequence[InventoryItem]:
        generic = _generic_folders(ctx)
        return [to_item(ctx, entry, generic) for entry in entries(ctx)]


register(ArpSource())
