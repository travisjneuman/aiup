"""Linux desktop entries and Flatpak and Snap exports (research 4.10, 4.11).

Folders are read in XDG order: ``$XDG_DATA_HOME/applications`` first, then
each ``$XDG_DATA_DIRS`` entry, then the Flatpak and Snap export folders when
the data dirs leave them out. The first folder that has a desktop-file ID
wins, so a user entry with ``Hidden=true`` masks the system one. Entries that
are hidden, not applications, or whose ``TryExec`` program is missing are left
out. Nothing named in ``Exec`` is ever run.

Owners: ``X-Flatpak`` and ``X-SnapInstanceName`` name their package; entries in
system folders are looked up in the system package database in one batch
(package-owned entries become "package" rows, which listings leave to the
package view); the launched file gets the same layout rules as PATH commands.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Set, Tuple

from aiup.detect import files, owners
from aiup.detect.items import InventoryItem, Owner, det_id
from aiup.detect.sources import DetectionSource, register
from aiup.platform.base import split_path

if TYPE_CHECKING:
    from aiup.engine.context import Context

DESKTOP_MAX = 256 * 1024
MAX_DEPTH = 3
# Programs that start something else; their entries name no file of their own.
_LAUNCHERS = frozenset((
    "env", "sh", "bash", "dash", "zsh", "flatpak", "snap", "gtk-launch", "xdg-open", "wine", "wine64",
    "wine-stable", "steam", "kioclient", "kioclient5", "kde-open", "gio", "systemd-run", "pkexec",
    "distrobox", "distrobox-enter", "toolbox", "python", "python3", "java", "mono", "dotnet",
))
_FIELD_CODES = frozenset("fFuUdDnNickvm")


def app_folders(ctx: "Context") -> List[Tuple[Path, str]]:
    """``(applications folder, scope)`` in lookup order."""
    data_home = files.xdg_data_home(ctx)
    out: List[Tuple[Path, str]] = [(data_home / "applications", "user")]
    for folder in files.xdg_data_dirs(ctx):
        out.append((folder / "applications", "system"))
    out.append((data_home / "flatpak" / "exports" / "share" / "applications", "user"))
    out.append((Path("/var/lib/flatpak/exports/share/applications"), "system"))
    out.append((Path("/var/lib/snapd/desktop/applications"), "system"))
    seen: Set[str] = set()
    unique: List[Tuple[Path, str]] = []
    home = str(files.home(ctx))
    for folder, scope in out:
        key = files.norm(str(folder))
        if key in seen:
            continue
        seen.add(key)
        unique.append((folder, "user" if files.inside(str(folder), home) else scope))
    return unique


def _walk(folder: Path, depth: int = 0) -> List[Tuple[str, Path]]:
    """``(desktop-file ID, file)`` below one folder."""
    out: List[Tuple[str, Path]] = []
    for entry in files.scandir(folder):
        try:
            if entry.is_dir():
                if depth < MAX_DEPTH and not entry.name.startswith("."):
                    for sub_id, path in _walk(Path(entry.path), depth + 1):
                        out.append((entry.name + "-" + sub_id, path))
                continue
            if entry.name.endswith(".desktop") and entry.is_file():
                out.append((entry.name, Path(entry.path)))
        except OSError:
            continue
    return out


def _unescape(value: str) -> str:
    out: List[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            following = value[index + 1]
            out.append({"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}.get(following, "\\" + following))
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def parse_entry(text: str) -> Dict[str, str]:
    """The unlocalized keys of the ``[Desktop Entry]`` group."""
    out: Dict[str, str] = {}
    group = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            if group == "Desktop Entry":
                break
            group = line[1:-1]
            continue
        if group != "Desktop Entry" or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if "[" in key or key in out:
            continue
        out[key] = _unescape(value.strip())
    return out


def exec_argv(value: str) -> List[str]:
    """``Exec`` split per the Desktop Entry spec, field codes removed."""
    args: List[str] = []
    current: List[str] = []
    quoted = False
    started = False
    index = 0
    while index < len(value):
        char = value[index]
        if quoted:
            if char == "\\" and index + 1 < len(value) and value[index + 1] in "\"`$\\":
                current.append(value[index + 1])
                index += 2
                continue
            if char == '"':
                quoted = False
            else:
                current.append(char)
        elif char == '"':
            quoted, started = True, True
        elif char.isspace():
            if started:
                args.append("".join(current))
                current, started = [], False
        elif char == "%" and index + 1 < len(value):
            following = value[index + 1]
            if following == "%":
                current.append("%")
                started = True
            elif following not in _FIELD_CODES:
                current.append(char + following)
                started = True
            index += 2
            continue
        else:
            current.append(char)
            started = True
        index += 1
    if started:
        args.append("".join(current))
    return [a for a in args if a]


def program_of(argv: Sequence[str]) -> str:
    """The program an ``Exec`` line starts, skipping an ``env VAR=value`` prefix."""
    index = 0
    if argv and os.path.basename(argv[0]) == "env":
        index = 1
        while index < len(argv) and ("=" in argv[index] or argv[index].startswith("-")):
            index += 1
    return argv[index] if index < len(argv) else ""


def locate(ctx: "Context", program: str) -> Tuple[str, bool]:
    """``(file, found by PATH lookup)``; ("", False) when it cannot be found."""
    if not program:
        return "", False
    if os.path.isabs(program):
        return (program, False) if os.path.isfile(program) else ("", False)
    if "/" in program:
        return "", False
    found = shutil.which(program, path=os.pathsep.join(split_path(files.env_get(ctx, "PATH"))))
    return (found, True) if found else ("", False)


class _Entry:
    def __init__(self, desktop_id: str, path: Path, scope: str, keys: Dict[str, str]) -> None:
        self.desktop_id = desktop_id
        self.path = path
        self.scope = scope
        self.keys = keys
        self.program = ""
        self.target = ""
        self.command = ""
        self.needs_owner = False    # kept only when a package database claims it


def _system_tool_available(ctx: "Context") -> bool:
    return any(ctx.provider_available(name) for name in owners.SYSTEM_MANAGERS if name != "aur")


def read_entries(ctx: "Context") -> List[_Entry]:
    """Winning, visible application entries."""
    seen: Set[str] = set()
    out: List[_Entry] = []
    system_db = _system_tool_available(ctx)
    for folder, scope in app_folders(ctx):
        if not files.exists_dir(folder):
            continue
        # Without a package database, entries under /usr/share cannot be told
        # apart from the distribution's own and are left out.
        skip_unowned = scope == "system" and not system_db and str(folder).startswith("/usr/share/")
        for desktop_id, path in _walk(folder):
            if desktop_id in seen:
                continue
            seen.add(desktop_id)
            text = files.read_text(path, DESKTOP_MAX)
            if text is None:
                continue
            keys = parse_entry(text)
            if keys.get("Type", "Application") != "Application" or not keys.get("Name"):
                continue
            if keys.get("Hidden", "").lower() == "true" or keys.get("NoDisplay", "").lower() == "true":
                continue
            try_exec = keys.get("TryExec", "")
            if try_exec and not locate(ctx, try_exec)[0]:
                continue
            entry = _Entry(desktop_id, path, scope, keys)
            entry.needs_owner = skip_unowned and _package_owner(keys) is None
            out.append(entry)
    for entry in out:
        program = program_of(exec_argv(entry.keys.get("Exec", "")))
        entry.program = program
        if os.path.basename(program) in _LAUNCHERS:
            continue
        found, by_path = locate(ctx, program)
        if found:
            entry.target = files.real(found)
            if by_path or os.path.dirname(found) in split_path(files.env_get(ctx, "PATH")):
                entry.command = os.path.basename(found)
    return out


def _package_owner(keys: Dict[str, str]) -> Optional[Owner]:
    flatpak = keys.get("X-Flatpak", "")
    if flatpak:
        return Owner(manager="flatpak", package=flatpak, confidence="exact", evidence="X-Flatpak key")
    snap = keys.get("X-SnapInstanceName", "")
    if snap:
        return Owner(manager="snap", package=snap, confidence="exact", evidence="X-SnapInstanceName key")
    return None


def read_items(ctx: "Context") -> List[InventoryItem]:
    entries = read_entries(ctx)
    home = str(files.home(ctx))
    system_files = [str(e.path) for e in entries if e.scope == "system" and _package_owner(e.keys) is None]
    outside = [e.target for e in entries if e.target and not files.inside(e.target, home)]
    by_system = owners.system_owners(ctx, list(dict.fromkeys(system_files + outside)))
    targets = list(dict.fromkeys(e.target for e in entries if e.target))
    by_layout = owners.attribute(ctx, targets, system=False)
    items: List[InventoryItem] = []
    for entry in entries:
        owner = _package_owner(entry.keys) or by_system.get(str(entry.path))
        found = by_layout.get(entry.target) if entry.target else None
        if owner is None and entry.target:
            owner = by_system.get(entry.target) or (found.owner if found is not None else None)
        if owner is None and entry.needs_owner:
            continue
        items.append(_item(entry, owner, found.version if found is not None else "",
                           found.guidance if found is not None else ""))
    return items


def _item(entry: _Entry, owner: Optional[Owner], version: str, guidance: str) -> InventoryItem:
    keys = entry.keys
    facts: List[Tuple[str, str]] = [("desktop_id", entry.desktop_id), ("desktop_file", str(entry.path))]
    if entry.target:
        facts.append(("target", entry.target))
        head = files.read_head(entry.target, 16)
        if files.appimage_type(head):
            facts.append(("appimage", "1"))
            if not version:
                version = keys.get("X-AppImage-Version", "") or \
                    files.split_name_version(os.path.basename(entry.target).rsplit(".", 1)[0])[1]
    if entry.command:
        facts.append(("command", entry.command))
    if os.path.basename(entry.program) in ("wine", "wine64", "wine-stable"):
        facts.append(("runner", "wine"))
    paths = tuple(p for p in (entry.target, str(entry.path)) if p)
    confidence = "exact" if owner is not None and owner.confidence == "exact" else "heuristic"
    return InventoryItem(
        id=det_id("desktop", entry.desktop_id[:-len(".desktop")]), name=keys.get("Name", entry.desktop_id),
        version=version, population="detected", source="desktop", paths=paths, owner=owner,
        kind="app", scope=entry.scope, confidence=confidence,
        evidence=owner.evidence if owner is not None else "desktop entry",
        needs_admin=entry.scope == "system", guidance=guidance,
        description=keys.get("Comment", "") or keys.get("GenericName", ""), facts=tuple(facts),
    )


class DesktopSource(DetectionSource):
    name = "desktop"
    oses = frozenset(("linux",))
    cost = "cheap"

    def fingerprint(self, ctx: "Context") -> str:
        parts = [files.env_get(ctx, "XDG_DATA_DIRS"), files.env_get(ctx, "PATH")]
        for folder, _scope in app_folders(ctx):
            parts.append(str(folder) + "=" + files.stat_stamp(folder))
        return files.stamp(parts)

    def read(self, ctx: "Context") -> List[InventoryItem]:
        return read_items(ctx)


register(DesktopSource())
