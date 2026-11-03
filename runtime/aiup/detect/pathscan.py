"""PATH commands with owner attribution (research 4.12, 5.7, 7, 9, 10).

Walks every PATH folder plus the folders installers commonly use even when
they are not on PATH (as ``inventory_scan_path_bins`` does on macOS). System
folders and version manager shim folders are skipped: their commands belong
to the system package database or forward to one install. Each command name
becomes one item; every distinct real file that answers to the name is kept
in PATH order as a :class:`Copy`, so the merge can flag duplicates and
shadowed copies.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Set, Tuple

from aiup import paths as aiup_paths
from aiup.detect import files, owners
from aiup.detect.items import Copy, InventoryItem, Owner, det_id
from aiup.detect.sources import DetectionSource, register
from aiup.platform.base import split_path

if TYPE_CHECKING:
    from aiup.engine.context import Context

_LINUX_SYSTEM_DIRS = (
    "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/usr/games", "/usr/lib", "/usr/lib64", "/usr/libexec",
    "/snap/bin", "/var/lib/snapd/snap/bin", "/var/lib/flatpak/exports/bin",
    "/run/current-system/sw/bin", "/nix/var/nix/profiles/default/bin", "/run/wrappers/bin",
    "/home/linuxbrew/.linuxbrew/bin", "/home/linuxbrew/.linuxbrew/sbin",
)
_BACKUP = re.compile(r"(?:\.\d+)?\.(?:old|bak|orig)$|~$", re.IGNORECASE)
_PS1_RANK = 99


def _pathext(ctx: "Context") -> Tuple[str, ...]:
    raw = files.env_get(ctx, "PATHEXT") or ".COM;.EXE;.BAT;.CMD"
    return tuple(e.strip().lower() for e in raw.split(";") if e.strip().startswith("."))


def skipped_dirs(ctx: "Context") -> Set[str]:
    """Folders the walk never reads (normalized)."""
    home = files.home(ctx)
    data = files.xdg_data_home(ctx)
    out: List[str] = []
    if files.is_windows(ctx):
        out.append(files.env_get(ctx, "SystemRoot") or files.env_get(ctx, "windir") or "C:\\Windows")
        out.append(str(files.local_appdata(ctx) / "Microsoft" / "WindowsApps"))
        program_files = files.env_get(ctx, "ProgramFiles")
        if program_files:
            out.append(str(Path(program_files) / "WindowsApps"))
    else:
        out.extend(_LINUX_SYSTEM_DIRS)
        out.extend(str(p) for p in (
            data / "flatpak" / "exports" / "bin", home / ".nix-profile" / "bin", home / ".linuxbrew" / "bin",
            home / ".pyenv" / "shims", home / ".rbenv" / "shims", home / ".nodenv" / "shims",
            home / ".goenv" / "shims", home / ".jenv" / "shims",
        ))
    mise = files.env_dir(ctx, "MISE_DATA_DIR") or data / "mise"
    asdf = files.env_dir(ctx, "ASDF_DATA_DIR") or home / ".asdf"
    volta = files.env_dir(ctx, "VOLTA_HOME") or home / ".volta"
    proto = files.env_dir(ctx, "PROTO_HOME") or home / ".proto"
    out.extend(str(p) for p in (mise / "shims", asdf / "shims", volta / "bin", proto / "shims"))
    return {files.norm(p) for p in out if p}


def _is_system(ctx: "Context", folder: str, skip: Set[str]) -> bool:
    key = files.norm(folder)
    if key in skip:
        return True
    if files.is_windows(ctx):
        root = files.env_get(ctx, "SystemRoot") or "C:\\Windows"
        return files.inside(folder, root)
    return False


def extra_dirs(ctx: "Context") -> Tuple[Path, ...]:
    """Installer folders read even when PATH leaves them out."""
    home = files.home(ctx)
    env = files.env_of(ctx)
    out: List[Path] = [
        aiup_paths.local_bin(ctx.os_name, env),
        aiup_paths.npm_bin(ctx.os_name, env),
        owners.cargo_home(ctx) / "bin",
        home / ".grok" / "bin",
        home / ".deno" / "bin",
        home / ".bun" / "bin",
        home / ".opencode" / "bin",
        home / ".dotnet" / "tools",
    ]
    out.extend(owners.go_bin_dirs(ctx))
    if files.is_windows(ctx):
        out.append(files.local_appdata(ctx) / "Microsoft" / "WinGet" / "Links")
    else:
        out.extend((home / "bin", Path("/usr/local/bin")))
    return tuple(out)


def scan_dirs(ctx: "Context") -> List[Tuple[str, bool]]:
    """``(folder, on PATH)`` in lookup order, system and shim folders left out."""
    skip = skipped_dirs(ctx)
    out: List[Tuple[str, bool]] = []
    seen: Set[str] = set()
    for folder in split_path(files.env_get(ctx, "PATH")):
        key = files.norm(folder)
        if key in seen:
            continue
        seen.add(key)
        if not _is_system(ctx, folder, skip):
            out.append((folder, True))
    for extra in extra_dirs(ctx):
        key = files.norm(str(extra))
        if key in seen or not files.exists_dir(extra):
            continue
        seen.add(key)
        if not _is_system(ctx, str(extra), skip):
            out.append((str(extra), False))
    return out


class _Seen:
    """One command name's copies while walking."""

    def __init__(self) -> None:
        self.copies: List[Copy] = []
        self.resolved: Set[str] = set()


def walk(ctx: "Context") -> Dict[str, _Seen]:
    """Command key -> its distinct copies in lookup order."""
    windows = files.is_windows(ctx)
    pathext = _pathext(ctx)
    found: Dict[str, _Seen] = {}
    for folder, on_path in scan_dirs(ctx):
        best: Dict[str, Tuple[int, os.DirEntry]] = {}
        for entry in files.scandir(folder):
            name = entry.name
            if name.startswith(".") or _BACKUP.search(name):
                continue
            if not files.is_executable_entry(entry, windows, pathext):
                continue
            key = owners.command_key(ctx, name)
            if not key:
                continue
            rank = 0
            if windows:
                lowered = name.lower()
                rank = next((i for i, ext in enumerate(pathext) if lowered.endswith(ext)), _PS1_RANK)
            current = best.get(key)
            if current is None or rank < current[0]:
                best[key] = (rank, entry)
        for key in sorted(best):
            path = best[key][1].path
            resolved = files.real(path)
            seen = found.setdefault(key, _Seen())
            marker = files.norm(resolved)
            if marker in seen.resolved:
                continue
            seen.resolved.add(marker)
            seen.copies.append(Copy(path=path, resolved=resolved, on_path=on_path))
    return found


def _confidence(owner: Optional[Owner]) -> str:
    if owner is None:
        return "heuristic"
    if owner.confidence == "exact":
        return "exact"
    return "strong" if owner.manager == "arp" else "heuristic"


def read_path_items(ctx: "Context") -> List[InventoryItem]:
    found = walk(ctx)
    paths: List[str] = []
    heads: Dict[str, bytes] = {}
    for seen in found.values():
        for copy in seen.copies:
            paths.append(copy.path)
            heads[copy.path] = files.read_head(copy.resolved, 512)
    owned = owners.attribute(ctx, paths, system=True, heads=heads)
    home = str(files.home(ctx))
    windows = files.is_windows(ctx)
    items: List[InventoryItem] = []
    for key in sorted(found):
        seen = found[key]
        copies: List[Copy] = []
        for copy in seen.copies:
            attr = owned.get(copy.path)
            version = attr.version if attr is not None else ""
            head = heads.get(copy.path, b"")
            if not version and files.appimage_type(head):
                version = files.split_name_version(os.path.basename(copy.resolved).rsplit(".", 1)[0])[1]
            copies.append(Copy(path=copy.path, resolved=copy.resolved,
                               owner=attr.owner if attr is not None else None,
                               version=version, on_path=copy.on_path))
        first = copies[0]
        attr = owned.get(first.path)
        version = first.version
        if not version and windows and first.resolved.lower().endswith(".exe"):
            version = files.pe_version(first.resolved)
            copies[0] = Copy(first.path, first.resolved, first.owner, version, first.on_path)
        facts: List[Tuple[str, str]] = [("resolved", first.resolved), ("folder", os.path.dirname(first.path))]
        if files.appimage_type(heads.get(first.path, b"")):
            facts.append(("appimage", "1"))
        if attr is not None and attr.companion:
            facts.append(("companion", "1"))
        if not first.on_path:
            facts.append(("on_path", "0"))
        system_scope = not files.inside(first.resolved, home)
        items.append(InventoryItem(
            id=det_id("path", key), name=key, version=version, population="detected",
            source="path", paths=tuple(c.path for c in copies), owner=first.owner,
            kind="command", scope="system" if system_scope else "user",
            confidence=_confidence(first.owner),
            evidence=first.owner.evidence if first.owner is not None else "",
            self_updates=bool(attr and attr.self_updates), needs_admin=system_scope,
            guidance=attr.guidance if attr is not None else "",
            copies=tuple(copies), facts=tuple(facts),
        ))
    return items


class PathSource(DetectionSource):
    name = "path"
    oses = frozenset(("linux", "windows"))
    cost = "cheap"

    def fingerprint(self, ctx: "Context") -> str:
        dirs = scan_dirs(ctx)
        return files.stamp([files.env_get(ctx, "PATH")] + [d + "=" + files.stat_stamp(d) for d, _ in dirs])

    def read(self, ctx: "Context") -> Sequence[InventoryItem]:
        return read_path_items(ctx)


register(PathSource())
