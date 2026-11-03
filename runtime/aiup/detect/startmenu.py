"""Windows Start Menu shortcuts (research 5.4).

Shortcuts are parsed in-process (MS-SHLLINK): the header flags, the
LinkInfo local path and, when that is missing, the environment-variable
target block. Advertised (MSI) shortcuts, targets that are not ``.exe``
files, Windows' own programs and uninstaller shortcuts are left out. Most
rows fold into an Uninstall entry during linking; the rest are portable apps
or leftovers.
"""

from __future__ import annotations

import ntpath
import os
import struct
from pathlib import Path
from typing import TYPE_CHECKING, List, Set, Tuple

from aiup.detect import files, owners
from aiup.detect.items import InventoryItem, det_id
from aiup.detect.sources import DetectionSource, register

if TYPE_CHECKING:
    from aiup.engine.context import Context

LNK_MAX = 64 * 1024
MAX_DEPTH = 4
_HEADER_SIZE = 0x4C
_HAS_ID_LIST = 0x1
_HAS_LINK_INFO = 0x2
_HAS_NAME = 0x4
_HAS_RELATIVE_PATH = 0x8
_HAS_WORKING_DIR = 0x10
_HAS_ARGUMENTS = 0x20
_HAS_ICON = 0x40
_IS_UNICODE = 0x80
_HAS_DARWIN_ID = 0x1000
_ENV_BLOCK = 0xA0000001


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0] if offset + 2 <= len(data) else 0


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0] if offset + 4 <= len(data) else 0


def _ansi(data: bytes, offset: int) -> str:
    if offset <= 0 or offset >= len(data):
        return ""
    end = data.find(b"\0", offset)
    raw = data[offset:end if end >= 0 else len(data)]
    try:
        return raw.decode("mbcs", errors="replace")
    except LookupError:
        return raw.decode("latin-1")


def _wide(data: bytes, offset: int) -> str:
    if offset <= 0 or offset >= len(data):
        return ""
    end = offset
    while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
        end += 2
    return data[offset:end].decode("utf-16-le", errors="replace")


def _expand(ctx: "Context", text: str) -> str:
    out = text
    for _ in range(4):
        start = out.find("%")
        end = out.find("%", start + 1) if start >= 0 else -1
        if start < 0 or end < 0:
            break
        value = files.env_get(ctx, out[start + 1:end])
        if not value:
            break
        out = out[:start] + value + out[end + 1:]
    return out


def parse_link(ctx: "Context", data: bytes) -> Tuple[str, bool]:
    """``(target path, advertised)`` of a ``.lnk`` file; ("", False) when unreadable."""
    if len(data) < _HEADER_SIZE or _u32(data, 0) != _HEADER_SIZE:
        return "", False
    flags = _u32(data, 20)
    if flags & _HAS_DARWIN_ID:
        return "", True
    offset = _HEADER_SIZE
    if flags & _HAS_ID_LIST:
        offset += 2 + _u16(data, offset)
    target = ""
    if flags & _HAS_LINK_INFO and offset + 28 <= len(data):
        size = _u32(data, offset)
        header = _u32(data, offset + 4)
        info_flags = _u32(data, offset + 8)
        if info_flags & 0x1 and size <= len(data) - offset:
            info = data[offset:offset + size]
            base = ""
            suffix = ""
            if header >= 0x24:
                base = _wide(info, _u32(info, 28))
                suffix = _wide(info, _u32(info, 32))
            if not base:
                base = _ansi(info, _u32(info, 16))
                suffix = _ansi(info, _u32(info, 24))
            if base:
                target = ntpath.join(base, suffix) if suffix else base
        offset += size
    unicode = bool(flags & _IS_UNICODE)
    for bit in (_HAS_NAME, _HAS_RELATIVE_PATH, _HAS_WORKING_DIR, _HAS_ARGUMENTS, _HAS_ICON):
        if flags & bit:
            count = _u16(data, offset)
            offset += 2 + count * (2 if unicode else 1)
    if not target:
        while offset + 8 <= len(data):
            block_size = _u32(data, offset)
            if block_size < 4:
                break
            if _u32(data, offset + 4) == _ENV_BLOCK and block_size >= 0x314:
                target = _wide(data, offset + 268) or _ansi(data, offset + 8)
                break
            offset += block_size
    return _expand(ctx, target.strip()) if target else "", False


def start_menu_roots(ctx: "Context") -> List[Tuple[Path, str]]:
    out: List[Tuple[Path, str]] = []
    roaming = files.roaming_appdata(ctx)
    out.append((roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs", "user"))
    program_data = files.env_get(ctx, "ProgramData")
    if program_data:
        out.append((Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs", "system"))
    return out


def _walk(folder: Path, depth: int = 0) -> List[Path]:
    out: List[Path] = []
    for entry in files.scandir(folder):
        try:
            if entry.is_dir():
                if depth < MAX_DEPTH:
                    out.extend(_walk(Path(entry.path), depth + 1))
            elif entry.name.lower().endswith(".lnk") and entry.is_file():
                out.append(Path(entry.path))
        except OSError:
            continue
    return out


def _skipped(ctx: "Context", name: str, target: str) -> bool:
    lowered = name.lower()
    if "uninstall" in lowered or lowered.startswith("uninst"):
        return True
    if not target.lower().endswith(".exe"):
        return True
    windows_dir = files.env_get(ctx, "SystemRoot") or "C:\\Windows"
    if files.inside(target, windows_dir):
        return True
    base = ntpath.basename(target).lower()
    # Squirrel shortcuts start Update.exe; their Uninstall entry already lists the app.
    return base.startswith("unins") or base == "update.exe"


class _Shortcut:
    def __init__(self, path: Path, scope: str, rel: str, target: str) -> None:
        self.path = path
        self.scope = scope
        self.rel = rel
        self.target = target


def read_shortcuts(ctx: "Context") -> List[_Shortcut]:
    out: List[_Shortcut] = []
    seen: Set[str] = set()
    for root, scope in start_menu_roots(ctx):
        for link in _walk(root):
            try:
                with open(link, "rb") as handle:
                    data = handle.read(LNK_MAX)
            except OSError:
                continue
            target, advertised = parse_link(ctx, data)
            if advertised or not target or _skipped(ctx, link.stem, target):
                continue
            if not os.path.isfile(target):
                continue
            resolved = files.real(target)
            key = files.norm(resolved)
            if key in seen:
                continue
            seen.add(key)
            rel = "/".join(files.relative_parts(str(link), str(root)))
            out.append(_Shortcut(link, scope, rel, resolved))
    return out


def read_items(ctx: "Context") -> List[InventoryItem]:
    shortcuts = read_shortcuts(ctx)
    owned = owners.attribute(ctx, [s.target for s in shortcuts], system=False)
    items: List[InventoryItem] = []
    for shortcut in shortcuts:
        found = owned.get(shortcut.target)
        owner = found.owner if found is not None else None
        version = (found.version if found is not None else "") or files.pe_version(shortcut.target)
        confidence = "heuristic"
        if owner is not None:
            confidence = "exact" if owner.confidence == "exact" else ("strong" if owner.manager == "arp" else "heuristic")
        key = shortcut.scope + ":" + shortcut.rel.lower()
        if key.endswith(".lnk"):
            key = key[:-4]
        facts: Tuple[Tuple[str, str], ...] = (("target", shortcut.target), ("shortcut", str(shortcut.path)))
        items.append(InventoryItem(
            id=det_id("startmenu", key), name=files.strip_version_words(shortcut.path.stem) or shortcut.path.stem,
            version=version, population="detected", source="startmenu",
            paths=(shortcut.target, str(shortcut.path)), owner=owner, kind="app",
            scope="user" if files.inside(shortcut.target, str(files.home(ctx))) else "system",
            confidence=confidence, evidence=owner.evidence if owner is not None else "Start Menu shortcut",
            self_updates=bool(found and found.self_updates), guidance=found.guidance if found is not None else "",
            facts=facts,
        ))
    return items


class StartMenuSource(DetectionSource):
    name = "startmenu"
    oses = frozenset(("windows",))
    cost = "cheap"

    def fingerprint(self, ctx: "Context") -> str:
        parts: List[str] = []
        for root, _scope in start_menu_roots(ctx):
            parts.append(str(root) + "=" + files.stat_stamp(root))
            for entry in files.scandir(root):
                parts.append(entry.name + "=" + files.stat_stamp(entry.path))
        return files.stamp(parts)

    def read(self, ctx: "Context") -> List[InventoryItem]:
        return read_items(ctx)


register(StartMenuSource())


__all__ = ["parse_link", "read_items", "start_menu_roots", "StartMenuSource"]
