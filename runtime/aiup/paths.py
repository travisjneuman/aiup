"""Where aiup keeps its files on each platform (design doc section 9.2).

| Dir     | Linux                                  | Windows                          |
| ------- | -------------------------------------- | -------------------------------- |
| config  | ${XDG_CONFIG_HOME:-~/.config}/aiup     | %LOCALAPPDATA%\\aiup\\config     |
| data    | ${XDG_DATA_HOME:-~/.local/share}/aiup  | %LOCALAPPDATA%\\aiup\\data       |
| state   | ${XDG_STATE_HOME:-~/.local/state}/aiup | %LOCALAPPDATA%\\aiup\\state      |
| cache   | ${XDG_CACHE_HOME:-~/.cache}/aiup       | %LOCALAPPDATA%\\aiup\\cache      |
| runtime | $XDG_RUNTIME_DIR/aiup or <cache>/run   | %LOCALAPPDATA%\\aiup\\cache\\run |

With ``AIUP_STATE_DIR`` set, all five go under it. The darwin layout reuses the
Linux one; it exists only so catalog export can run there.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from aiup.errors import AiupError

PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


@dataclass(frozen=True)
class Dirs:
    """The five aiup folders for this user."""

    config: Path       # preferences.json, channels.tsv
    data: Path         # generations, launcher, npm prefix, methods
    state: Path        # logs and history, notify-last, list-query, list-category, fzf-expanded
    cache: Path        # indexes, available-versions, release-notes, downloads, pycache
    runtime: Path      # TUI sessions, fzf socket (private, per user)


def home_dir(platform_name: str, env: Mapping[str, str]) -> Path:
    """The user's home folder: HOME on Linux, USERPROFILE on Windows."""
    name = "USERPROFILE" if platform_name == "windows" else "HOME"
    value = env.get(name, "")
    if value and Path(value).is_absolute():
        return Path(value)
    if platform_name != "windows":
        try:
            import pwd

            account_home = pwd.getpwuid(os.getuid()).pw_dir
        except (ImportError, KeyError, AttributeError):
            account_home = ""
        if account_home and Path(account_home).is_absolute():
            return Path(account_home)
    return Path.home().absolute()


def _xdg(env: Mapping[str, str], name: str, fallback: Path) -> Path:
    """An XDG base folder. Values that are not absolute paths are ignored."""
    value = env.get(name, "")
    if value and Path(value).is_absolute():
        return Path(value)
    return fallback


def _private_runtime_base(env: Mapping[str, str]) -> Optional[Path]:
    """$XDG_RUNTIME_DIR when it is absolute, owned by this user and mode 700."""
    value = env.get("XDG_RUNTIME_DIR", "")
    if not value or not Path(value).is_absolute():
        return None
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        return None
    try:
        info = os.stat(value, follow_symlinks=False)
    except OSError:
        return None
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != getuid():
        return None
    if stat.S_IMODE(info.st_mode) != PRIVATE_DIR_MODE:
        return None
    return Path(value)


def local_appdata(env: Mapping[str, str]) -> Path:
    """%LOCALAPPDATA%, or %USERPROFILE%\\AppData\\Local when it is unset."""
    value = env.get("LOCALAPPDATA", "")
    if value and Path(value).is_absolute():
        return Path(value)
    return home_dir("windows", env) / "AppData" / "Local"


def roaming_appdata(env: Mapping[str, str]) -> Path:
    """%APPDATA%, or %USERPROFILE%\\AppData\\Roaming when it is unset."""
    value = env.get("APPDATA", "")
    if value and Path(value).is_absolute():
        return Path(value)
    return home_dir("windows", env) / "AppData" / "Roaming"


def _state_dir_override(env: Mapping[str, str]) -> Optional[Path]:
    value = env.get("AIUP_STATE_DIR", "")
    if not value:
        return None
    return Path(value).expanduser().absolute()


def dirs_for(platform_name: str, env: Mapping[str, str]) -> Dirs:
    """The aiup folders for ``platform_name`` ("linux", "windows" or "darwin")."""
    root = _state_dir_override(env)
    if root is not None:
        return Dirs(config=root / "config", data=root / "data", state=root / "state",
                    cache=root / "cache", runtime=root / "run")
    if platform_name == "windows":
        base = local_appdata(env) / "aiup"
        cache = base / "cache"
        return Dirs(config=base / "config", data=base / "data", state=base / "state",
                    cache=cache, runtime=cache / "run")
    home = home_dir(platform_name, env)
    cache = _xdg(env, "XDG_CACHE_HOME", home / ".cache") / "aiup"
    runtime_base = _private_runtime_base(env)
    return Dirs(
        config=_xdg(env, "XDG_CONFIG_HOME", home / ".config") / "aiup",
        data=_xdg(env, "XDG_DATA_HOME", home / ".local" / "share") / "aiup",
        state=_xdg(env, "XDG_STATE_HOME", home / ".local" / "state") / "aiup",
        cache=cache,
        runtime=runtime_base / "aiup" if runtime_base is not None else cache / "run",
    )


def local_bin(platform_name: str, env: Mapping[str, str]) -> Path:
    """Where vendor installers put commands: AIUP_LOCAL_BIN, else ~/.local/bin."""
    value = env.get("AIUP_LOCAL_BIN", "")
    if value:
        return Path(value).expanduser().absolute()
    return home_dir(platform_name, env) / ".local" / "bin"


def npm_prefix(platform_name: str, env: Mapping[str, str]) -> Path:
    """aiup's own npm prefix (section 6.4): AIUP_NPM_PREFIX, else <data>/npm."""
    value = env.get("AIUP_NPM_PREFIX", "")
    if value:
        return Path(value).expanduser().absolute()
    return dirs_for(platform_name, env).data / "npm"


def npm_bin(platform_name: str, env: Mapping[str, str]) -> Path:
    """The folder npm puts command shims in for aiup's prefix.

    Windows puts them in the prefix folder itself; Linux uses ``<prefix>/bin``.
    """
    prefix = npm_prefix(platform_name, env)
    return prefix if platform_name == "windows" else prefix / "bin"


def refuse_symlink(path: Path) -> None:
    """Stop when a state folder or file is a symbolic link."""
    if path.is_symlink():
        raise AiupError("Refusing symbolic-link state path: " + str(path))


def private_mkdir(path: Path, parents: bool = False, exist_ok: bool = False) -> None:
    """``path.mkdir`` with mode 700 on POSIX and the inherited ACL on Windows.

    On Windows, Python 3.13 and later turn mode 700 into an ACL for SYSTEM,
    Administrators and the folder owner only. A folder made from an elevated
    session is owned by Administrators, so a later normal run by the same user
    would be locked out. The user's profile folders are already private there.
    """
    if os.name == "nt":
        path.mkdir(parents=parents, exist_ok=exist_ok)
    else:
        path.mkdir(mode=PRIVATE_DIR_MODE, parents=parents, exist_ok=exist_ok)


def ensure_dir(path: Path) -> Path:
    """Create a private folder (mode 700 on Linux) and its parents.

    Refuses a folder that is a symbolic link, as the macOS helpers do.
    """
    refuse_symlink(path)
    try:
        private_mkdir(path, parents=True, exist_ok=True)
    except OSError as exc:
        raise AiupError("Could not create " + str(path) + ": " + (exc.strerror or str(exc))) from exc
    refuse_symlink(path)
    if not path.is_dir():
        raise AiupError("Not a folder: " + str(path))
    return path
