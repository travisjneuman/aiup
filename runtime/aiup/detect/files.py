"""Small file helpers for detection: bounded reads, stamps, and static metadata.

Nothing here runs a program. Versions come from file contents that can be read
without executing anything: Go build info, PE version resources (Windows),
AppImage magic bytes, script headers and file names.
"""

from __future__ import annotations

import hashlib
import json
import mmap
import os
import re
import stat
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

from aiup import paths as aiup_paths

JSON_MAX = 1024 * 1024          # manifests and JSON files
HEADER_MAX = 64 * 1024          # script headers
BINARY_SCAN_MAX = 256 * 1024 * 1024   # biggest binary searched for Go build info

_GO_MAGIC = b"\xff Go buildinf:"


# ----- environment and well-known folders ---------------------------------------


def is_windows(ctx: object) -> bool:
    return str(getattr(ctx, "os_name", "")) == "windows"


def env_of(ctx: object) -> Mapping[str, str]:
    env = getattr(ctx, "env", None)
    return env if isinstance(env, Mapping) else os.environ


def env_get(ctx: object, name: str) -> str:
    """An environment value; Windows names match without regard to case."""
    env = env_of(ctx)
    value = env.get(name)
    if value is None and is_windows(ctx):
        lowered = name.lower()
        for key, item in env.items():
            if key.lower() == lowered:
                value = item
                break
    return value or ""


def home(ctx: object) -> Path:
    return aiup_paths.home_dir(str(getattr(ctx, "os_name", "linux")), env_of(ctx))


def env_dir(ctx: object, name: str, *fallback: str) -> Optional[Path]:
    """``$NAME`` when it is an absolute path, else ``~/<fallback...>`` (None without one)."""
    value = env_get(ctx, name)
    if value and os.path.isabs(value):
        return Path(value)
    if fallback:
        return home(ctx).joinpath(*fallback)
    return None


def xdg_data_home(ctx: object) -> Path:
    return env_dir(ctx, "XDG_DATA_HOME", ".local", "share") or home(ctx) / ".local" / "share"


def xdg_data_dirs(ctx: object) -> Tuple[Path, ...]:
    value = env_get(ctx, "XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    out: List[Path] = []
    for part in value.split(":"):
        if part and os.path.isabs(part):
            out.append(Path(part))
    return tuple(out)


def local_appdata(ctx: object) -> Path:
    return aiup_paths.local_appdata(env_of(ctx))


def roaming_appdata(ctx: object) -> Path:
    return aiup_paths.roaming_appdata(env_of(ctx))


# ----- paths -----------------------------------------------------------------------


def norm(path: str) -> str:
    """A comparison key: normalized, and case-folded on Windows."""
    return os.path.normcase(os.path.normpath(path))


def real(path: str) -> str:
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return path


def inside(path: str, root: str) -> bool:
    """True when ``path`` is ``root`` or below it (compared with :func:`norm`)."""
    if not path or not root:
        return False
    p, r = norm(path), norm(root)
    if p == r:
        return True
    return p.startswith(r.rstrip("\\/") + os.sep)


def relative_parts(path: str, root: str) -> Tuple[str, ...]:
    """Path components of ``path`` below ``root``; () when it is not below it."""
    if not inside(path, root):
        return ()
    rel = os.path.relpath(os.path.normpath(path), os.path.normpath(root))
    if rel in (".", ""):
        return ()
    return tuple(p for p in rel.replace("\\", "/").split("/") if p)


def exists_dir(path: object) -> bool:
    try:
        return os.path.isdir(str(path))
    except (OSError, ValueError):
        return False


def scandir(path: object) -> List[os.DirEntry]:
    """Folder entries, sorted by name; [] when the folder cannot be read."""
    try:
        with os.scandir(str(path)) as it:
            return sorted(it, key=lambda e: e.name)
    except (OSError, ValueError):
        return []


def is_executable_entry(entry: os.DirEntry, windows: bool, pathext: Sequence[str]) -> bool:
    """A regular file (or a link to one) that PATH lookup would run."""
    try:
        if not entry.is_file():
            return False
    except OSError:
        return False
    if windows:
        lowered = entry.name.lower()
        return any(lowered.endswith(ext) for ext in pathext) or lowered.endswith(".ps1")
    try:
        mode = entry.stat().st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode) and bool(mode & 0o111)


# ----- stamps (cache fingerprints) -------------------------------------------------


def stat_stamp(path: object) -> str:
    """``mtime_ns:size`` of a file or folder, "-" when it is missing."""
    try:
        st = os.stat(str(path))
    except (OSError, ValueError):
        return "-"
    return "{}:{}".format(st.st_mtime_ns, st.st_size)


def stamp(parts: Iterable[str]) -> str:
    """A short digest of several stamp strings."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8", "replace"))
        digest.update(b"\0")
    return digest.hexdigest()[:24]


def stamp_paths(paths: Iterable[object]) -> str:
    return stamp(str(p) + "=" + stat_stamp(p) for p in paths)


# ----- bounded reads ------------------------------------------------------------------


def read_head(path: str, limit: int = HEADER_MAX) -> bytes:
    """Up to ``limit`` bytes from the start of a file (links followed); b"" on error."""
    try:
        with open(path, "rb") as handle:
            return handle.read(limit)
    except (OSError, ValueError):
        return b""


def read_text(path: object, limit: int = JSON_MAX) -> Optional[str]:
    """A whole text file no bigger than ``limit``, decoded as UTF-8; None otherwise."""
    try:
        with open(str(path), "rb") as handle:
            data = handle.read(limit + 1)
    except (OSError, ValueError):
        return None
    if len(data) > limit:
        return None
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def read_json(path: object, limit: int = JSON_MAX) -> Optional[object]:
    text = read_text(path, limit)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


# ----- static metadata ------------------------------------------------------------------


def appimage_type(head: bytes) -> int:
    """1 or 2 for an AppImage (ELF with ``AI`` at bytes 8 to 10), else 0."""
    if len(head) < 11 or not head.startswith(b"\x7fELF") or head[8:10] != b"AI":
        return 0
    return head[10] if head[10] in (1, 2) else 0


def _uvarint(data: bytes, pos: int) -> Tuple[int, int]:
    value = 0
    shift = 0
    while pos < len(data) and shift < 64:
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, pos
        shift += 7
    return -1, pos


def go_buildinfo(path: str) -> Optional[Tuple[str, str, str]]:
    """``(main package path, module, module version)`` from a Go binary, or None.

    Reads the ``\\xff Go buildinf:`` block that ``go version -m`` reads. Only
    the Go 1.18+ inline-string layout is parsed; older binaries return None.
    """
    try:
        size = os.path.getsize(path)
        if size < 64 or size > BINARY_SCAN_MAX:
            return None
        with open(path, "rb") as handle:
            with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as view:
                block = b""
                at = view.find(_GO_MAGIC)
                # The real header is 16-byte aligned with a 4 or 8 byte pointer
                # size; a stray copy of the magic text (a binary that embeds
                # debug/buildinfo) is skipped.
                for _ in range(8):
                    if at < 0:
                        return None
                    if at % 16 == 0 and view[at + 14:at + 15] in (b"\x04", b"\x08"):
                        block = view[at:at + 32 + 64 * 1024]
                        break
                    at = view.find(_GO_MAGIC, at + 1)
    except (OSError, ValueError):
        return None
    if len(block) < 32 or not (block[15] & 0x2):
        return None
    pos = 32
    length, pos = _uvarint(block, pos)       # Go version string
    if length < 0:
        return None
    pos += length
    length, pos = _uvarint(block, pos)       # module info
    if length < 0 or pos + length > len(block):
        return None
    info = block[pos:pos + length]
    if len(info) >= 33 and info[-17:-16] == b"\n":
        info = info[16:-16]
    main_path = module = version = ""
    for line in info.decode("utf-8", "replace").splitlines():
        fields = line.split("\t")
        if fields[0] == "path" and len(fields) > 1:
            main_path = fields[1]
        elif fields[0] == "mod" and len(fields) > 2:
            module, version = fields[1], fields[2]
    if not main_path:
        return None
    return main_path, module, version


def pe_version(path: str) -> str:
    """FileVersion from a Windows PE version resource, or "" (Windows only)."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return ""
    try:
        api = ctypes.WinDLL("version", use_last_error=True)  # type: ignore[attr-defined]
        api.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        api.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        api.GetFileVersionInfoW.restype = wintypes.BOOL
        api.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                                       ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
        api.VerQueryValueW.restype = wintypes.BOOL
        size = api.GetFileVersionInfoSizeW(path, None)
        if not size or size > JSON_MAX:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not api.GetFileVersionInfoW(path, 0, size, buf):
            return ""
        pointer = ctypes.c_void_p()
        length = wintypes.UINT()
        codes = ["040904b0", "040904e4", "04090000"]
        if api.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(pointer), ctypes.byref(length)) \
                and pointer.value and length.value >= 4:
            words = ctypes.cast(pointer, ctypes.POINTER(wintypes.WORD))
            codes.insert(0, "{:04x}{:04x}".format(words[0], words[1]))
        for code in codes:
            for key in ("FileVersion", "ProductVersion"):
                query = "\\StringFileInfo\\" + code + "\\" + key
                if api.VerQueryValueW(buf, query, ctypes.byref(pointer), ctypes.byref(length)) \
                        and pointer.value and length.value:
                    text = ctypes.wstring_at(pointer.value, length.value).rstrip("\0").strip()
                    if text:
                        return text.replace(", ", ".").replace(",", ".")
        if api.VerQueryValueW(buf, "\\", ctypes.byref(pointer), ctypes.byref(length)) \
                and pointer.value and length.value >= 52:
            dwords = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD))
            if dwords[0] == 0xFEEF04BD:
                ms, ls = dwords[2], dwords[3]
                return "{}.{}.{}.{}".format(ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    except (OSError, ValueError, AttributeError, TypeError):
        return ""
    return ""


_VERSION_IN_NAME = re.compile(
    r"[-_ ]v?(\d+(?:\.\d+)+(?:[-+~.]?[0-9A-Za-z]+)*?)"
    r"(?:[-_.](?:x86[-_]64|amd64|aarch64|arm64|armhf|i[36]86|x64|x86|linux|win(?:dows)?|portable))*$",
    re.IGNORECASE,
)


def split_name_version(stem: str) -> Tuple[str, str]:
    """``Name-1.2.3-x86_64`` -> ("Name", "1.2.3"); ("Name", "") without a version."""
    match = _VERSION_IN_NAME.search(stem)
    if not match or match.start() == 0:
        return stem, ""
    return stem[:match.start()], match.group(1)


_TRAILING_VERSION = re.compile(r"[\s_-]*(?:\(?v?\d+(?:[.\-]\d+)+[\w.\-]*\)?|\((?:x64|x86|64-bit|32-bit|arm64)\))\s*$",
                               re.IGNORECASE)


def strip_version_words(label: str) -> str:
    """``7-Zip 26.04 (x64)`` -> ``7-Zip``: trailing version and bitness tokens dropped."""
    text = label.strip()
    for _ in range(4):
        cut = _TRAILING_VERSION.sub("", text).strip()
        if cut == text or not cut:
            break
        text = cut
    return text
