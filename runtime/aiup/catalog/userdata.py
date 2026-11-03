"""User data paths from catalog/tool-meta.tsv (design doc section 5.5).

Linux paths start with ``~/`` or one of ``$XDG_CONFIG_HOME/``,
``$XDG_DATA_HOME/``, ``$XDG_STATE_HOME/``, ``$XDG_CACHE_HOME/``. Windows paths
start with ``%APPDATA%\\``, ``%LOCALAPPDATA%\\`` or ``%USERPROFILE%\\``. Only
those variables are expanded; any other ``$`` or ``%`` is a load error. A path
must name something below its base folder, never the base itself, and never
use ``..``, so ``aiup remove`` can only ever move data inside the user's own
folders to the Trash.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, Dict, Mapping, Optional, Tuple

from aiup.errors import CatalogError
from aiup.paths import home_dir, local_appdata, roaming_appdata

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

LINUX_BASES: Tuple[str, ...] = (
    "~", "$XDG_CONFIG_HOME", "$XDG_DATA_HOME", "$XDG_STATE_HOME", "$XDG_CACHE_HOME",
)
WINDOWS_BASES: Tuple[str, ...] = ("%APPDATA%", "%LOCALAPPDATA%", "%USERPROFILE%")


def _split_base(os_name: str, raw: str) -> Tuple[str, Tuple[str, ...]]:
    """Return (base, components) or raise ValueError with the reason."""
    if _CONTROL.search(raw):
        raise ValueError("control character in path")
    if os_name == "linux":
        bases, seps = LINUX_BASES, "/"
    elif os_name == "windows":
        bases, seps = WINDOWS_BASES, "\\/"
    else:
        raise ValueError("unknown OS '{}'".format(os_name))
    found = [b for b in bases if raw.startswith(b) and len(raw) > len(b) and raw[len(b)] in seps]
    if not found:
        raise ValueError("path must start with one of " + ", ".join(b + seps[0] for b in bases))
    base = found[0]
    rest = raw[len(base) + 1:]
    if "$" in rest or "%" in rest:
        raise ValueError("only the base folder variables are expanded")
    if os_name == "windows":
        parts = tuple(re.split(r"[\\/]", rest))
        if ":" in rest:
            raise ValueError("':' is not allowed after the base folder")
    else:
        parts = tuple(rest.split("/"))
    if not parts or any(p in ("", ".", "..") for p in parts):
        raise ValueError("path must name something below its base, without '.', '..' or empty parts")
    return base, parts


def check_data_path(os_name: str, raw: str, location: str) -> str:
    """Validate one unexpanded data path at load time; return it unchanged."""
    try:
        _split_base(os_name, raw)
    except ValueError as exc:
        raise CatalogError("bad {} data path '{}': {}".format(os_name, raw, exc), location) from exc
    return raw


def _xdg(env: Mapping[str, str], name: str, fallback: Path) -> Path:
    value = env.get(name, "")
    return Path(value) if value and Path(value).is_absolute() else fallback


def _linux_bases(env: Mapping[str, str]) -> Dict[str, Callable[[], Path]]:
    home = home_dir("linux", env)
    return {
        "~": lambda: home,
        "$XDG_CONFIG_HOME": lambda: _xdg(env, "XDG_CONFIG_HOME", home / ".config"),
        "$XDG_DATA_HOME": lambda: _xdg(env, "XDG_DATA_HOME", home / ".local" / "share"),
        "$XDG_STATE_HOME": lambda: _xdg(env, "XDG_STATE_HOME", home / ".local" / "state"),
        "$XDG_CACHE_HOME": lambda: _xdg(env, "XDG_CACHE_HOME", home / ".cache"),
    }


def _windows_bases(env: Mapping[str, str]) -> Dict[str, Callable[[], Path]]:
    return {
        "%APPDATA%": lambda: roaming_appdata(env),
        "%LOCALAPPDATA%": lambda: local_appdata(env),
        "%USERPROFILE%": lambda: home_dir("windows", env),
    }


def _inside(base: Path, candidate: Path, os_name: str) -> bool:
    pure = PureWindowsPath if os_name == "windows" else PurePosixPath
    base_parts = pure(str(base)).parts
    cand_parts = pure(str(candidate)).parts
    if os_name == "windows":
        base_parts = tuple(p.lower() for p in base_parts)
        cand_parts = tuple(p.lower() for p in cand_parts)
    return len(cand_parts) > len(base_parts) and cand_parts[:len(base_parts)] == base_parts


def expand_data_path(os_name: str, raw: str, env: Mapping[str, str]) -> Optional[Path]:
    """Expand one catalog data path for this user.

    Returns None when the path is malformed or would land outside its base
    folder, so callers skip it instead of touching anything unexpected.
    """
    try:
        base, parts = _split_base(os_name, raw)
    except ValueError:
        return None
    bases = _linux_bases(env) if os_name == "linux" else _windows_bases(env)
    root = bases[base]()
    candidate = root.joinpath(*parts)
    return candidate if _inside(root, candidate, os_name) else None
