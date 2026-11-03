#!/usr/bin/env python3
"""aiup launcher for Linux and Windows.

Public installs run the published release. A one-line pointer on main
(macos/release) names the exact commit whose runtime and catalog form the
release. The launcher downloads the files listed in runtime/FILES at that
commit, checks every size and SHA-256, and runs the result in this same
Python process. Files addressed by commit never change, so an unchanged
release costs one tiny request. When the release cannot be checked, or a new
download fails validation, the last validated release keeps running.

Running a checkout is an explicit development opt-in: AIUP_SOURCE_PATH is used
only when it is set and not empty.

The launcher also owns PATH setup (``setup-path``), so the shell installer,
the PowerShell installer and the runtime share one implementation.

Standard library only. Python 3.9 or newer.
"""

from __future__ import annotations

import concurrent.futures
import errno
import hashlib
import importlib
import os
import re
import secrets
import shutil
import socket
import ssl
import stat
import sys
import tempfile
import time
import urllib.error
import warnings
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, NoReturn, Optional, Sequence, Tuple

AIUP_LAUNCHER_REVISION = 1
AIUP_LAUNCHER_KIND = "python"
DEFAULT_REPO_RAW = "https://raw.githubusercontent.com/travisjneuman/aiup"
AIUP_REPO_RAW = (os.environ.get("AIUP_REPO_RAW", "") or DEFAULT_REPO_RAW).rstrip("/")
AIUP_RELEASE_URL = os.environ.get("AIUP_RELEASE_URL", "") or AIUP_REPO_RAW + "/main/macos/release"

MIN_PYTHON = (3, 9)
POINTER_MAX_BYTES = 4096
POINTER_TIMEOUT = 10.0
POINTER_SOCKET_TIMEOUT = 5.0
FILES_MAX_BYTES = 65536
FILE_MAX_BYTES = 1048576
TOTAL_MAX_BYTES = 8388608
FILE_TIMEOUT = 30.0
FILE_RETRIES = 2
DOWNLOAD_WORKERS = 6
LOCK_TRIES = 400
LOCK_SLEEP = 0.05
LOCK_STALE_SECONDS = 3600
GENERATION_KEEP_SECONDS = 86400
TEMP_STALE_SECONDS = 3600

IS_WINDOWS = os.name == "nt"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
GENERATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ALLOWED_PATH_RE = re.compile(
    r"^(runtime/aiup_main\.py|runtime/aiup/[a-z0-9_/]+\.py|macos/catalog/manifest\.tsv|catalog/[a-z0-9-]+\.tsv)$"
)
REQUIRED_PATHS = (
    "runtime/aiup_main.py",
    "runtime/aiup/cli.py",
    "runtime/aiup/version.py",
    "macos/catalog/manifest.tsv",
    "catalog/platforms.tsv",
)
FILES_LIST_PATH = "runtime/FILES"
RELEASE_RECORD = "release"
GENERATION_EXTRAS = (RELEASE_RECORD, FILES_LIST_PATH)
VERSION_HEADER = "# aiup-runtime-version: "
PY_VERSION_RE = re.compile(r'^AIUP_VERSION = "([^"]+)"$', re.MULTILINE)
PLATFORMS_COLUMNS = 15


class LauncherError(Exception):
    """A failure the launcher reports in one line."""


def warn(message: str) -> None:
    print("aiup: " + message, file=sys.stderr)


def die(message: str) -> NoReturn:
    warn(message)
    sys.exit(1)


def short_error(exc: BaseException) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text.splitlines()[0][:300]


# ---------------------------------------------------------------------------
# Folders (same rules as runtime/aiup/paths.py, section 9.2 of the design doc)
# ---------------------------------------------------------------------------


def platform_name() -> str:
    if IS_WINDOWS:
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def home_dir(env: Mapping[str, str]) -> Path:
    value = env.get("USERPROFILE" if IS_WINDOWS else "HOME", "")
    if value and Path(value).is_absolute():
        return Path(value)
    return Path.home()


def _absolute_env(env: Mapping[str, str], name: str, fallback: Path) -> Path:
    value = env.get(name, "")
    if value and Path(value).is_absolute():
        return Path(value)
    return fallback


def data_and_cache_dirs(env: Mapping[str, str]) -> Tuple[Path, Path]:
    """aiup's data folder (generations live here) and cache folder."""
    override = env.get("AIUP_STATE_DIR", "")
    if override:
        root = Path(override).expanduser().absolute()
        return root / "data", root / "cache"
    if IS_WINDOWS:
        local = _absolute_env(env, "LOCALAPPDATA", home_dir(env) / "AppData" / "Local")
        return local / "aiup" / "data", local / "aiup" / "cache"
    home = home_dir(env)
    data = _absolute_env(env, "XDG_DATA_HOME", home / ".local" / "share") / "aiup"
    cache = _absolute_env(env, "XDG_CACHE_HOME", home / ".cache") / "aiup"
    return data, cache


def private_mkdir(path: Path, parents: bool = False, exist_ok: bool = False) -> None:
    """Mode 700 on POSIX. On Windows the inherited profile ACL: Python 3.13+
    turns mode 700 into an ACL for the folder owner, and a folder made from an
    elevated session is owned by Administrators, which locks out later normal
    runs."""
    if IS_WINDOWS:
        path.mkdir(parents=parents, exist_ok=exist_ok)
    else:
        path.mkdir(mode=0o700, parents=parents, exist_ok=exist_ok)


def ensure_private_dir(path: Path) -> None:
    if path.is_symlink():
        raise LauncherError("refusing a symbolic-link aiup folder: " + str(path))
    private_mkdir(path, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise LauncherError("not a folder: " + str(path))


def read_first_line(path: Path) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.readline().strip()
    except OSError:
        return None


def write_text_atomic(path: Path, text: str, mode: int = 0o600) -> None:
    """Write a temp file beside ``path`` and move it into place."""
    fd, tmp_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if not IS_WINDOWS:
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_bytes_private(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(str(path), flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


# ---------------------------------------------------------------------------
# HTTPS downloads
# ---------------------------------------------------------------------------


class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise urllib.error.URLError("refused a redirect away from HTTPS: " + newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener() -> urllib.request.OpenerDirector:
    context = ssl.create_default_context()
    return urllib.request.build_opener(_HttpsOnlyRedirect(), urllib.request.HTTPSHandler(context=context))


def fetch_bytes(url: str, max_bytes: int, timeout: float, socket_timeout: float = 10.0) -> bytes:
    """GET one HTTPS URL with a size cap and an overall time limit.

    ``socket_timeout`` bounds the connection and each read.
    """
    if urllib.parse.urlsplit(url).scheme != "https":
        raise LauncherError("refused a URL that is not HTTPS: " + url)
    request = urllib.request.Request(url, headers={"User-Agent": "aiup-launcher/" + str(AIUP_LAUNCHER_REVISION),
                                                   "Accept-Encoding": "identity"})
    deadline = time.monotonic() + timeout
    chunks: List[bytes] = []
    total = 0
    with _opener().open(request, timeout=min(timeout, socket_timeout)) as response:
        length = response.headers.get("Content-Length", "")
        if length.isdigit() and int(length) > max_bytes:
            raise LauncherError("download was larger than " + str(max_bytes) + " bytes: " + url)
        while True:
            if time.monotonic() > deadline:
                raise LauncherError("download took longer than " + str(int(timeout)) + " seconds: " + url)
            chunk = response.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise LauncherError("download was larger than " + str(max_bytes) + " bytes: " + url)
            chunks.append(chunk)
    return b"".join(chunks)


def _offline(exc: BaseException) -> bool:
    """True for errors a retry a second later cannot fix: no DNS, no route,
    connection refused. Offline runs then fall back at once."""
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, (socket.gaierror, ConnectionRefusedError)):
        return True
    return isinstance(reason, OSError) and reason.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH,
                                                           errno.ENETDOWN)


def fetch_with_retries(url: str, max_bytes: int, timeout: float, retries: int,
                       socket_timeout: float = 10.0) -> bytes:
    last: Optional[BaseException] = None
    for attempt in range(retries + 1):
        try:
            return fetch_bytes(url, max_bytes, timeout, socket_timeout)
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                raise LauncherError("HTTP " + str(exc.code) + " for " + url) from exc
            last = exc
        except LauncherError:
            raise
        except Exception as exc:  # network errors, TLS errors, truncated reads
            last = exc
            if _offline(exc):
                break
        if attempt < retries:
            time.sleep(1.0 + attempt)
    raise LauncherError("could not download " + url + ": " + short_error(last or LauncherError("unknown error")))


# ---------------------------------------------------------------------------
# Release pointer and runtime/FILES
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileEntry:
    sha256: str
    size: int
    path: str


def parse_pointer(text: str) -> Tuple[str, str]:
    """First non-comment line of macos/release: ``<version> <40 hex>``."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 2 and VERSION_RE.match(parts[0]) and SHA1_RE.match(parts[1]):
            return parts[0], parts[1]
        break
    raise LauncherError("the aiup release pointer was invalid")


def parse_files_list(text: str) -> Tuple[str, List[FileEntry]]:
    """Parse runtime/FILES. Returns the runtime version and the entries."""
    version = ""
    entries: List[FileEntry] = []
    seen = set()
    total = 0
    for number, raw in enumerate(text.split("\n"), 1):
        if "\r" in raw:
            raise LauncherError("runtime/FILES line " + str(number) + " has a carriage return")
        if not raw:
            continue
        if raw.startswith("#"):
            if raw.startswith(VERSION_HEADER) and not version:
                version = raw[len(VERSION_HEADER):].strip()
            continue
        parts = raw.split("  ")
        if len(parts) != 3:
            raise LauncherError("runtime/FILES line " + str(number) + " is not 'sha256  size  path'")
        digest, size_text, path = parts
        if not SHA256_RE.match(digest) or not size_text.isdigit():
            raise LauncherError("runtime/FILES line " + str(number) + " has a bad hash or size")
        if not ALLOWED_PATH_RE.match(path) or "//" in path or path.endswith("/") or path in seen:
            raise LauncherError("runtime/FILES line " + str(number) + " lists a path that is not allowed: " + path)
        size = int(size_text)
        if size > FILE_MAX_BYTES:
            raise LauncherError("runtime/FILES lists a file larger than 1 MiB: " + path)
        total += size
        seen.add(path)
        entries.append(FileEntry(digest, size, path))
    if not version or not VERSION_RE.match(version):
        raise LauncherError("runtime/FILES has no valid aiup-runtime-version line")
    missing = [path for path in REQUIRED_PATHS if path not in seen]
    if missing:
        raise LauncherError("runtime/FILES does not list " + ", ".join(missing))
    if total > TOTAL_MAX_BYTES:
        raise LauncherError("runtime/FILES lists more than 8 MiB of files")
    return version, entries


def rel_path(root: Path, repo_path: str) -> Path:
    return root.joinpath(*repo_path.split("/"))


def _header_version(text: str) -> str:
    for line in text.splitlines():
        if line.startswith(VERSION_HEADER):
            return line[len(VERSION_HEADER):].strip()
        if line and not line.startswith("#"):
            break
    return ""


def _check_platforms(text: str) -> None:
    ids = set()
    for number, line in enumerate(text.split("\n"), 1):
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) > PLATFORMS_COLUMNS or not fields[0]:
            raise LauncherError("catalog/platforms.tsv line " + str(number) + " does not parse")
        if fields[0] in ids:
            raise LauncherError("catalog/platforms.tsv repeats the id " + fields[0])
        ids.add(fields[0])
    if "fzf" not in ids:
        raise LauncherError("catalog/platforms.tsv has no fzf row")


def validate_generation(gen_dir: Path, expected_version: Optional[str], deep: bool = True) -> str:
    """Check a generation folder and return its version.

    Every listed file must be present with the right size and SHA-256, the
    four version strings must agree, catalog/platforms.tsv must parse with an
    fzf row, and nothing unlisted may be present besides ``release``,
    ``runtime/FILES`` and ``__pycache__``. With ``deep`` every ``.py`` file is
    also compiled (syntax only, nothing runs). Activation uses ``deep``; a
    start of an already validated generation checks hashes only.
    """
    try:
        files_text = rel_path(gen_dir, FILES_LIST_PATH).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LauncherError("could not read runtime/FILES: " + short_error(exc)) from exc
    version, entries = parse_files_list(files_text)
    if expected_version is not None and version != expected_version:
        raise LauncherError("runtime/FILES names " + version + ", expected " + expected_version)
    texts: Dict[str, str] = {}
    listed = set()
    for entry in entries:
        path = rel_path(gen_dir, entry.path)
        if path.is_symlink() or not path.is_file():
            raise LauncherError("missing file: " + entry.path)
        data = path.read_bytes()
        if len(data) != entry.size or hashlib.sha256(data).hexdigest() != entry.sha256:
            raise LauncherError("size or SHA-256 mismatch: " + entry.path)
        listed.add(entry.path)
        if entry.path in ("runtime/aiup/version.py", "macos/catalog/manifest.tsv", "catalog/platforms.tsv") \
                or (deep and entry.path.endswith(".py")):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise LauncherError("not UTF-8: " + entry.path) from exc
            texts[entry.path] = text
            if deep and entry.path.endswith(".py"):
                try:
                    # Newer Pythons warn about style (for example an invalid
                    # escape); only real syntax errors stop a release.
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        compile(text, str(path), "exec", dont_inherit=True)
                except (SyntaxError, ValueError) as exc:
                    raise LauncherError("syntax check failed for " + entry.path + ": " + short_error(exc)) from exc
    match = PY_VERSION_RE.search(texts["runtime/aiup/version.py"])
    found = {
        "runtime/aiup/version.py": match.group(1) if match else "",
        "macos/catalog/manifest.tsv": _header_version(texts["macos/catalog/manifest.tsv"]),
        "catalog/platforms.tsv": _header_version(texts["catalog/platforms.tsv"]),
    }
    for name, value in found.items():
        if value != version:
            raise LauncherError("version mismatch: " + name + " says '" + value + "', runtime/FILES says " + version)
    _check_platforms(texts["catalog/platforms.tsv"])
    for root, dirs, names in os.walk(str(gen_dir)):
        for name in list(dirs):
            if os.path.islink(os.path.join(root, name)):
                raise LauncherError("unexpected link in the generation: " + name)
            if name == "__pycache__":
                dirs.remove(name)
        for name in names:
            rel = Path(root, name).relative_to(gen_dir).as_posix()
            if rel not in listed and rel not in GENERATION_EXTRAS:
                raise LauncherError("unexpected file in the generation: " + rel)
    return version


# ---------------------------------------------------------------------------
# Generations, activation lock and retention
# ---------------------------------------------------------------------------


class Store:
    """The launcher's files under the data folder."""

    def __init__(self, data_dir: Path, cache_dir: Path) -> None:
        self.data = data_dir
        self.cache = cache_dir
        self.generations = data_dir / "generations"
        self.current_pointer = data_dir / "current-generation"
        self.previous_pointer = data_dir / "previous-generation"
        self.lock = data_dir / "activation.lock"
        self.reaper = data_dir / ".activation-lock-reaper"

    def read_pointer(self, pointer: Path) -> Optional[str]:
        if pointer.is_symlink():
            return None
        gen_id = read_first_line(pointer)
        if not gen_id or not GENERATION_ID_RE.match(gen_id):
            return None
        path = self.generations / gen_id
        if path.is_symlink() or not path.is_dir():
            return None
        return gen_id

    def release_of(self, gen_id: str) -> str:
        return read_first_line(self.generations / gen_id / RELEASE_RECORD) or ""


def pid_alive(pid: int) -> bool:
    """True when a process with this id exists. Never signals it."""
    if pid <= 0:
        return False
    if IS_WINDOWS:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: it exists
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _age_seconds(path: Path) -> float:
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return 0.0


def _lock_owner_alive(store: Store, owner: str) -> bool:
    if _age_seconds(store.lock) > LOCK_STALE_SECONDS:
        return False
    if not owner:
        # Created but not written yet, or unreadable: give it a minute.
        return _age_seconds(store.lock) < 60
    pid_text = owner.split(" ", 1)[0]
    if not pid_text.isdigit():
        return False
    return pid_alive(int(pid_text))


def acquire_activation_lock(store: Store) -> str:
    owner = str(os.getpid()) + " " + str(int(time.time())) + " " + secrets.token_hex(8)
    for _ in range(LOCK_TRIES):
        try:
            fd = os.open(str(store.lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if store.lock.is_symlink():
                raise LauncherError("refusing a symbolic-link activation lock")
            current = read_first_line(store.lock)
            if current is not None and not _lock_owner_alive(store, current):
                if store.reaper.is_dir() and _age_seconds(store.reaper) > 60:
                    try:
                        os.rmdir(str(store.reaper))
                    except OSError:
                        pass
                try:
                    os.mkdir(str(store.reaper))
                except OSError:
                    pass
                else:
                    try:
                        confirmed = read_first_line(store.lock)
                        if confirmed == current and not _lock_owner_alive(store, confirmed or ""):
                            os.unlink(str(store.lock))
                    except OSError:
                        pass
                    finally:
                        try:
                            os.rmdir(str(store.reaper))
                        except OSError:
                            pass
            time.sleep(LOCK_SLEEP)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(owner + "\n")
        return owner
    raise LauncherError("timed out waiting for another aiup activation")


def release_activation_lock(store: Store, owner: str) -> None:
    if read_first_line(store.lock) == owner:
        try:
            os.unlink(str(store.lock))
        except OSError:
            pass


def pycache_mirror(prefix: Path, source_dir: Path) -> Path:
    """Where ``sys.pycache_prefix`` puts bytecode for files under ``source_dir``."""
    text = str(source_dir)
    if len(text) > 1 and text[1] == ":":
        text = text[2:]
    return prefix / text.lstrip("\\/")


def remove_tree_if(root: Path, allow: Callable[[str], bool]) -> bool:
    """Remove ``root`` only when every file in it passes ``allow``."""
    doomed: List[Path] = []
    for walk_root, dirs, names in os.walk(str(root)):
        for name in dirs:
            if os.path.islink(os.path.join(walk_root, name)):
                return False
        for name in names:
            path = Path(walk_root, name)
            rel = path.relative_to(root).as_posix()
            if path.is_symlink() or not allow(rel):
                return False
            doomed.append(path)
    for path in doomed:
        try:
            path.unlink()
        except OSError:
            return False
    for walk_root, _dirs, _names in os.walk(str(root), topdown=False):
        try:
            os.rmdir(walk_root)
        except OSError:
            return False
    return True


def _is_pyc(rel: str) -> bool:
    return "__pycache__/" in rel and rel.endswith(".pyc")


def remove_generation(store: Store, gen_dir: Path) -> bool:
    try:
        _version, entries = parse_files_list(rel_path(gen_dir, FILES_LIST_PATH).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, LauncherError):
        return False
    allowed = {entry.path for entry in entries}
    allowed.update(GENERATION_EXTRAS)
    removed = remove_tree_if(gen_dir, lambda rel: rel in allowed or _is_pyc(rel))
    if removed:
        mirror = pycache_mirror(store.cache / "pycache", gen_dir)
        if mirror.is_dir():
            remove_tree_if(mirror, lambda rel: rel.endswith(".pyc"))
    return removed


def prune_generations(store: Store, current_id: str) -> None:
    """Keep the current and previous generations and any younger than a day.

    The previous one stays because an aiup started just before the switch
    may still be running from it and importing modules on demand.
    """
    try:
        children = list(store.generations.iterdir())
    except OSError:
        return
    keep = {current_id, store.read_pointer(store.previous_pointer) or ""}
    for child in children:
        name = child.name
        if name.startswith(".") or name in keep or not GENERATION_ID_RE.match(name):
            continue
        if child.is_symlink() or not child.is_dir() or _age_seconds(child) < GENERATION_KEEP_SECONDS:
            continue
        if not rel_path(child, FILES_LIST_PATH).is_file():
            continue  # not made by this launcher
        if not remove_generation(store, child):
            warn("left an aiup generation in place: " + str(child))


def sweep_stale_temporaries(store: Store) -> None:
    """Remove downloads, staging folders and pointer temps older than an hour."""
    prefixes = (".current-generation.", ".previous-generation.", ".aiup-")
    try:
        for child in store.data.iterdir():
            if child.name.startswith(prefixes) and child.is_file() and not child.is_symlink() \
                    and _age_seconds(child) > TEMP_STALE_SECONDS:
                try:
                    child.unlink()
                except OSError:
                    pass
    except OSError:
        pass
    try:
        for child in store.generations.iterdir():
            if child.name.startswith(".staging-") and child.is_dir() and not child.is_symlink() \
                    and _age_seconds(child) > TEMP_STALE_SECONDS:
                remove_tree_if(child, lambda rel: bool(ALLOWED_PATH_RE.match(rel)) or rel in GENERATION_EXTRAS
                               or _is_pyc(rel))
    except OSError:
        pass


def safe_version(version: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", version)


def download_release(store: Store, version: str, commit: str) -> Path:
    """Download and deep-validate a release into a new staging folder."""
    base = AIUP_REPO_RAW + "/" + commit + "/"
    files_bytes = fetch_with_retries(base + FILES_LIST_PATH, FILES_MAX_BYTES, FILE_TIMEOUT, FILE_RETRIES)
    try:
        files_text = files_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LauncherError("runtime/FILES is not UTF-8") from exc
    listed_version, entries = parse_files_list(files_text)
    if listed_version != version:
        raise LauncherError("the aiup release pointer named " + version + " but runtime/FILES is " + listed_version)
    staging = store.generations / (".staging-" + safe_version(version) + "-" + str(int(time.time())) + "-"
                                   + str(os.getpid()) + "-" + secrets.token_hex(4))
    private_mkdir(staging)
    try:
        files_path = rel_path(staging, FILES_LIST_PATH)
        private_mkdir(files_path.parent, parents=True, exist_ok=True)
        write_bytes_private(files_path, files_bytes)

        def fetch_one(entry: FileEntry) -> None:
            data = fetch_with_retries(base + entry.path, min(FILE_MAX_BYTES, entry.size), FILE_TIMEOUT, FILE_RETRIES)
            if len(data) != entry.size or hashlib.sha256(data).hexdigest() != entry.sha256:
                raise LauncherError("size or SHA-256 mismatch after download: " + entry.path)
            dest = rel_path(staging, entry.path)
            private_mkdir(dest.parent, parents=True, exist_ok=True)
            write_bytes_private(dest, data)

        with concurrent.futures.ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
            futures = [pool.submit(fetch_one, entry) for entry in entries]
            try:
                for future in concurrent.futures.as_completed(futures):
                    future.result()
            except BaseException:
                for future in futures:
                    future.cancel()
                raise
        write_bytes_private(staging / RELEASE_RECORD, (commit + "\n").encode("ascii"))
        validate_generation(staging, version, deep=True)
    except BaseException:
        remove_tree_if(staging, lambda rel: True)
        raise
    return staging


def rename_folder(source: Path, target: Path) -> None:
    """Rename a folder. On Windows, retry briefly while a virus scanner
    still holds one of the files that were just written."""
    for attempt in range(10):
        try:
            os.rename(str(source), str(target))
            return
        except PermissionError:
            if not IS_WINDOWS or attempt == 9:
                raise
            time.sleep(0.2 * (attempt + 1))


def activate(store: Store, staging: Path, version: str) -> str:
    """Move a validated staging folder into place and point current at it."""
    gen_id = safe_version(version) + "-" + str(int(time.time())) + "-" + str(os.getpid())
    target = store.generations / gen_id
    owner = acquire_activation_lock(store)
    try:
        if target.exists():
            raise LauncherError("a generation with this id already exists: " + gen_id)
        previous = store.read_pointer(store.current_pointer)
        rename_folder(staging, target)
        old_previous: Optional[str] = None
        had_previous = store.previous_pointer.is_file()
        if had_previous:
            try:
                old_previous = store.previous_pointer.read_text(encoding="utf-8")
            except OSError:
                old_previous = None
        switched = False
        try:
            if previous:
                write_text_atomic(store.previous_pointer, previous + "\n")
            write_text_atomic(store.current_pointer, gen_id + "\n")
            switched = True
        finally:
            if not switched:
                try:
                    if had_previous and old_previous is not None:
                        write_text_atomic(store.previous_pointer, old_previous)
                    elif not had_previous and store.previous_pointer.is_file():
                        store.previous_pointer.unlink()
                except OSError:
                    pass
                if read_first_line(store.current_pointer) != gen_id:
                    remove_generation(store, target)
        prune_generations(store, gen_id)
    finally:
        release_activation_lock(store, owner)
    return gen_id


# ---------------------------------------------------------------------------
# Running the runtime in this process
# ---------------------------------------------------------------------------


def _prepare_terminal() -> None:
    """Run the runtime's terminal setup (VT mode and UTF-8 on Windows, safe
    output encoding everywhere) and its Ctrl-Break mapping. Both are
    idempotent, so a runtime that also calls them is fine. A runtime without
    them still runs."""
    for module_name, function_name in (("aiup.platform.term", "enable"),
                                       ("aiup.platform.proc", "install_interrupt_handlers")):
        try:
            getattr(importlib.import_module(module_name), function_name)()
        except Exception:  # noqa: BLE001  setup is best effort; aiup prints plain text without it
            continue


def run_runtime(runtime_dir: Path, release_root: Path, generation: str, cache_dir: Path,
                argv: Sequence[str]) -> NoReturn:
    """Import aiup.cli from ``runtime_dir`` and exit with its status.

    ``release_root`` holds the files at their repo paths. AIUP_CATALOG_DIR
    names its ``catalog/`` folder; the manifest sits at ``../macos/catalog``.
    """
    os.environ["AIUP_ACTIVE_RUNTIME"] = str(runtime_dir / "aiup_main.py")
    os.environ["AIUP_ACTIVE_GENERATION"] = generation
    os.environ["AIUP_CATALOG_DIR"] = str(release_root / "catalog")
    os.environ["AIUP_LAUNCHER_PATH"] = str(Path(__file__).resolve())
    os.environ["AIUP_PYTHON"] = sys.executable
    os.environ["AIUP_LAUNCHER_REVISION"] = str(AIUP_LAUNCHER_REVISION)
    os.environ["AIUP_LAUNCHER_KIND"] = AIUP_LAUNCHER_KIND
    if IS_WINDOWS:
        os.environ["PYTHONUTF8"] = "1"
    # The shims pass -B so nothing lands inside a generation or a checkout.
    # Bytecode still helps startup, so keep it under the cache folder instead.
    try:
        prefix = cache_dir / "pycache"
        ensure_private_dir(prefix)
        sys.pycache_prefix = str(prefix)
        sys.dont_write_bytecode = False
    except (OSError, LauncherError):
        sys.dont_write_bytecode = True
    sys.path.insert(0, str(runtime_dir))
    try:
        cli = importlib.import_module("aiup.cli")
        _prepare_terminal()
        status = cli.main(list(argv))
    except KeyboardInterrupt:
        status = 130
    sys.exit(status)


def run_source(source: str, cache_dir: Path, argv: Sequence[str]) -> NoReturn:
    path = Path(source).expanduser()
    if not path.is_file():
        die("AIUP_SOURCE_PATH is not a file: " + source)
    path = path.resolve()
    runtime_dir = path.parent
    if path.name != "aiup_main.py" or not (runtime_dir / "aiup" / "cli.py").is_file():
        die("AIUP_SOURCE_PATH must name runtime/aiup_main.py in an aiup checkout: " + source)
    run_runtime(runtime_dir, runtime_dir.parent, "development", cache_dir, argv)


def launch(argv: Sequence[str]) -> NoReturn:
    data_dir, cache_dir = data_and_cache_dirs(os.environ)
    source = os.environ.get("AIUP_SOURCE_PATH", "")
    if source:
        run_source(source, cache_dir, argv)
    if platform_name() == "darwin":
        die("on macOS, install aiup with macos/install-aiup. This launcher is for Linux and Windows.")

    store = Store(data_dir, cache_dir)
    try:
        ensure_private_dir(store.data)
        ensure_private_dir(store.generations)
    except (OSError, LauncherError) as exc:
        die("could not create the aiup folders: " + short_error(exc))
    sweep_stale_temporaries(store)

    current = store.read_pointer(store.current_pointer)
    current_version = ""
    if current:
        try:
            current_version = validate_generation(store.generations / current, None, deep=False)
        except (OSError, LauncherError) as exc:
            warn("the installed aiup release failed validation (" + short_error(exc) + "); downloading it again")
            current = None

    def run_generation(gen_id: str) -> NoReturn:
        run_runtime(store.generations / gen_id / "runtime", store.generations / gen_id, gen_id, cache_dir, argv)

    def fall_back(reason: str) -> NoReturn:
        if not current:
            die(reason)
        warn(reason + "; running the installed release " + current_version)
        run_generation(current)

    # Each step only records what went wrong; aiup itself runs outside the
    # except blocks, so its own errors are never chained to a network error.
    problem = ""
    version = commit = ""
    try:
        pointer = fetch_with_retries(AIUP_RELEASE_URL, POINTER_MAX_BYTES, POINTER_TIMEOUT, 1,
                                     socket_timeout=POINTER_SOCKET_TIMEOUT)
        version, commit = parse_pointer(pointer.decode("utf-8", errors="replace"))
    except Exception as exc:
        problem = "could not check for a new aiup release (" + short_error(exc) + ")"
    if problem:
        fall_back(problem)

    if current and store.release_of(current) == commit:
        run_generation(current)

    staging: Optional[Path] = None
    try:
        staging = download_release(store, version, commit)
    except Exception as exc:
        problem = "could not fetch aiup " + version + " (" + short_error(exc) + ")"
    if problem or staging is None:
        fall_back(problem or "could not fetch aiup " + version)

    gen_id = ""
    try:
        gen_id = activate(store, staging, version)
    except Exception as exc:
        problem = "could not activate aiup " + version + " (" + short_error(exc) + ")"
        if staging.exists():
            remove_tree_if(staging, lambda rel: True)
    if problem or not gen_id:
        fall_back(problem or "could not activate aiup " + version)
    run_generation(gen_id)


# ---------------------------------------------------------------------------
# setup-path: make the aiup command reachable from every shell
# ---------------------------------------------------------------------------

PATH_BEGIN = "# >>> aiup PATH >>>"
PATH_END = "# <<< aiup PATH <<<"
PATH_ENTRY = "# aiup-path: "
PATH_COMMENT = (
    "# Added by aiup so new, login and non-interactive shells find its commands.",
    "# The aiup installer's uninstall option removes this block.",
)
SETUP_PATH_USAGE = """usage: aiup_launcher.py setup-path [--remove] [--all] [--system] [--check] DIR...

Adds each DIR to PATH for every shell, or removes it with --remove.
  Linux:   marked blocks in ~/.profile, ~/.bash_profile or ~/.bash_login when
           present, ~/.bashrc, ~/.zshenv, fish conf.d and systemd environment.d.
  Windows: the user PATH in the registry (HKCU\\Environment).
  --remove  remove DIR (with --all: every entry aiup added; DIR is optional)
  --system  Windows only: the machine PATH (needs an elevated terminal)
  --check   report where each DIR is set up; changes nothing
Set AIUP_NO_MODIFY_PATH=1 to print the lines instead of editing anything."""


@dataclass(frozen=True)
class PathFile:
    path: Path
    kind: str     # "posix", "fish" or "envd"
    top: bool     # insert the block at the top (~/.bashrc returns early when not interactive)
    owned: bool   # the whole file belongs to aiup
    create: bool  # create the file when it is missing


def _shell_available(name: str) -> bool:
    if shutil.which(name):
        return True
    try:
        with open("/etc/shells", "r", encoding="utf-8", errors="replace") as handle:
            return any(os.path.basename(line.strip()) == name for line in handle)
    except OSError:
        return False


def _systemd_user_session(env: Mapping[str, str]) -> bool:
    runtime_dir = env.get("XDG_RUNTIME_DIR", "")
    if not runtime_dir and hasattr(os, "getuid"):
        runtime_dir = "/run/user/" + str(os.getuid())
    return bool(runtime_dir) and os.path.isdir(os.path.join(runtime_dir, "systemd"))


def posix_targets(env: Mapping[str, str]) -> List[PathFile]:
    home = home_dir(env)
    config = _absolute_env(env, "XDG_CONFIG_HOME", home / ".config")
    shell_name = os.path.basename(env.get("SHELL", ""))
    bash_profile = home / ".bash_profile"
    bash_login = home / ".bash_login"
    fish_file = config / "fish" / "conf.d" / "aiup.fish"
    envd_file = config / "environment.d" / "60-aiup.conf"
    targets = [PathFile(home / ".profile", "posix", False, False, True)]
    if os.path.lexists(str(bash_profile)):
        targets.append(PathFile(bash_profile, "posix", False, False, False))
    elif os.path.lexists(str(bash_login)):
        targets.append(PathFile(bash_login, "posix", False, False, False))
    targets.append(PathFile(home / ".bashrc", "posix", True, False, _shell_available("bash")))
    targets.append(PathFile(home / ".zshenv", "posix", False, False,
                            shell_name == "zsh" or _shell_available("zsh")))
    targets.append(PathFile(fish_file, "fish", False, True,
                            _shell_available("fish") or (config / "fish").is_dir()))
    if sys.platform != "darwin":
        targets.append(PathFile(envd_file, "envd", False, True, _systemd_user_session(env)))
    return targets


def _sh_double_quoted(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")


def _sh_word(directory: str, home: str) -> str:
    if directory == home or directory.startswith(home.rstrip("/") + "/"):
        return '"$HOME' + _sh_double_quoted(directory[len(home.rstrip("/")):]) + '"'
    return "'" + directory.replace("'", "'\\''") + "'"


def _fish_word(directory: str, home: str) -> str:
    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")
    if directory == home or directory.startswith(home.rstrip("/") + "/"):
        return '"$HOME' + escape(directory[len(home.rstrip("/")):]) + '"'
    return '"' + escape(directory) + '"'


ENVD_SAFE_RE = re.compile(r"^[A-Za-z0-9._/@+,=-]+$")


def _envd_word(directory: str, home: str) -> Optional[str]:
    if directory == home or directory.startswith(home.rstrip("/") + "/"):
        rest = directory[len(home.rstrip("/")):]
        if rest and not ENVD_SAFE_RE.match(rest):
            return None
        return "${HOME}" + rest
    return directory if ENVD_SAFE_RE.match(directory) else None


def render_block(kind: str, dirs: Sequence[str], home: str) -> List[str]:
    lines = [PATH_BEGIN]
    lines.extend(PATH_COMMENT)
    lines.extend(PATH_ENTRY + directory for directory in dirs)
    if kind == "posix":
        for directory in reversed(dirs):
            word = _sh_word(directory, home)
            lines.append('case ":${PATH}:" in *:' + word + ':*) ;; *) PATH=' + word
                         + '"${PATH:+:$PATH}"; export PATH ;; esac')
    elif kind == "fish":
        for directory in reversed(dirs):
            word = _fish_word(directory, home)
            lines.append("if type -q fish_add_path")
            lines.append("    fish_add_path --path " + word)
            lines.append("else if not contains -- " + word + " $PATH")
            lines.append("    set -gx PATH " + word + " $PATH")
            lines.append("end")
    else:
        words = [w for w in (_envd_word(d, home) for d in dirs) if w is not None]
        if words:
            lines.append("PATH=" + ":".join(words) + ":${PATH}")
    lines.append(PATH_END)
    return lines


@dataclass
class ParsedFile:
    lines: List[str]
    start: int          # index of PATH_BEGIN, or -1
    end: int            # index of PATH_END, or -1
    dirs: List[str]     # aiup-path entries in the block
    legacy: bool        # a marked block with no aiup-path entries (older format)


def parse_path_file(text: str) -> ParsedFile:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    starts = [i for i, line in enumerate(lines) if line.rstrip("\r") == PATH_BEGIN]
    ends = [i for i, line in enumerate(lines) if line.rstrip("\r") == PATH_END]
    if not starts and not ends:
        return ParsedFile(lines, -1, -1, [], False)
    if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
        raise LauncherError("has unmatched or repeated aiup PATH markers")
    start, end = starts[0], ends[0]
    dirs = [line.rstrip("\r")[len(PATH_ENTRY):] for line in lines[start + 1:end]
            if line.startswith(PATH_ENTRY)]
    return ParsedFile(lines, start, end, dirs, not dirs)


def _backup(real: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = real.with_name(real.name + ".aiup-backup-" + stamp)
    counter = 1
    while os.path.lexists(str(backup)):
        backup = real.with_name(real.name + ".aiup-backup-" + stamp + "-" + str(counter))
        counter += 1
    shutil.copy2(str(real), str(backup))
    return backup


def _display(path: Path, home: str) -> str:
    text = str(path)
    if text.startswith(home.rstrip("/") + "/"):
        return "~" + text[len(home.rstrip("/")):]
    return text


def edit_path_file(target: PathFile, add: Sequence[str], remove: Sequence[str], remove_all: bool,
                   home: str) -> Optional[str]:
    """Apply one change to one file. Returns a line to show, or None."""
    real = Path(os.path.realpath(str(target.path)))
    exists = real.is_file()
    if not exists and (not add or not target.create):
        return None
    text = ""
    if exists:
        with open(real, "r", encoding="utf-8", errors="surrogateescape", newline="") as handle:
            text = handle.read()
    parsed = parse_path_file(text)
    lines = parsed.lines
    if parsed.legacy and add and not remove_all:
        return _display(target.path, home) + ": has an older aiup PATH block; left as it is"
    current = list(parsed.dirs)
    if add:
        wanted = current + [d for d in add if d not in current]
    elif remove_all:
        wanted = []
    else:
        wanted = [d for d in current if d not in remove]
    if parsed.start >= 0 and wanted == current and not (parsed.legacy and remove_all):
        return None
    if parsed.start < 0 and not wanted:
        return None
    block = render_block(target.kind, wanted, home) if wanted else []
    if parsed.start >= 0:
        before = lines[:parsed.start]
        after = lines[parsed.end + 1:]
        if not block:
            if parsed.start == 0 and after and after[0].strip() == "":
                after = after[1:]
            elif before and before[-1].strip() == "":
                before = before[:-1]
        new_lines = before + block + after
    elif target.top:
        offset = 1 if lines and lines[0].startswith("#!") else 0
        new_lines = lines[:offset] + block + ([""] if lines[offset:] else []) + lines[offset:]
    else:
        new_lines = lines + ([""] if lines and lines[-1].strip() else []) + block
    new_text = "\n".join(new_lines) + ("\n" if new_lines else "")
    if target.owned and not block and not any(line.strip() for line in new_lines):
        # The file only ever held the aiup block, so remove it entirely.
        if exists:
            real.unlink()
            return _display(target.path, home) + ": removed"
        return None
    real.parent.mkdir(parents=True, exist_ok=True)
    note = ""
    mode = 0o644
    if exists:
        mode = stat.S_IMODE(real.stat().st_mode)
        if not target.owned:
            note = " (backup: " + _display(_backup(real), home) + ")"
    write_text_atomic(real, new_text, mode)
    verb = "updated" if exists else "created"
    return _display(target.path, home) + ": " + verb + note


def check_path_files(dirs: Sequence[str], env: Mapping[str, str]) -> int:
    home = str(home_dir(env))
    for target in posix_targets(env):
        real = Path(os.path.realpath(str(target.path)))
        name = _display(target.path, home)
        if not real.is_file():
            print(name + ": not present")
            continue
        try:
            with open(real, "r", encoding="utf-8", errors="surrogateescape") as handle:
                parsed = parse_path_file(handle.read())
        except (OSError, LauncherError) as exc:
            print(name + ": " + short_error(exc))
            continue
        if parsed.legacy:
            print(name + ": older aiup PATH block")
            continue
        if not dirs and not parsed.dirs:
            print(name + ": no aiup PATH block")
            continue
        for directory in dirs or parsed.dirs:
            print(name + ": " + ("has " if directory in parsed.dirs else "missing ") + directory)
    for directory in dirs:
        in_path = directory in os.environ.get("PATH", "").split(os.pathsep)
        print("this shell: " + ("has " if in_path else "missing ") + directory)
    return 0


def posix_setup_path(dirs: Sequence[str], remove: bool, remove_all: bool) -> int:
    env = os.environ
    home = str(home_dir(env))
    status = 0
    for target in posix_targets(env):
        try:
            message = edit_path_file(target, [] if remove else dirs, dirs, remove_all, home)
        except (OSError, LauncherError) as exc:
            warn(_display(target.path, home) + ": " + short_error(exc))
            status = 1
            continue
        if message:
            print(message)
        if target.kind == "envd" and not remove:
            for directory in dirs:
                if _envd_word(directory, home) is None:
                    print(_display(target.path, home) + ": skipped " + directory + " (characters environment.d cannot hold)")
    return status


# --- Windows ---------------------------------------------------------------

WIN_USER_KEY = "Environment"
WIN_MACHINE_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def _win_norm(entry: str) -> str:
    import winreg

    value = entry.strip().strip('"')
    if not value:
        return ""
    value = winreg.ExpandEnvironmentStrings(value).rstrip("\\/")
    return os.path.normcase(os.path.normpath(value)) if value else ""


def _win_path_has(value: str, directory: str) -> bool:
    wanted = _win_norm(directory)
    return any(_win_norm(part) == wanted for part in value.split(";"))


def _win_read_path(machine: bool) -> Tuple[str, int]:
    import winreg

    hive = winreg.HKEY_LOCAL_MACHINE if machine else winreg.HKEY_CURRENT_USER
    with winreg.OpenKey(hive, WIN_MACHINE_KEY if machine else WIN_USER_KEY, 0, winreg.KEY_READ) as key:
        try:
            value, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return "", winreg.REG_EXPAND_SZ
    return str(value or ""), int(value_type)


def _win_is_elevated() -> bool:
    import ctypes

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _win_broadcast() -> None:
    import ctypes
    from ctypes import wintypes

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        send = user32.SendMessageTimeoutW
        send.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR, wintypes.UINT,
                         wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        send.restype = ctypes.c_size_t
        result = ctypes.c_size_t(0)
        # HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG, 5 seconds
        send(wintypes.HWND(0xFFFF), 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(result))
    except (AttributeError, OSError):
        pass


def _win_record_file() -> Path:
    data_dir, _cache = data_and_cache_dirs(os.environ)
    return data_dir / "path-entries.txt"


def _win_recorded() -> List[str]:
    try:
        with open(_win_record_file(), "r", encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]
    except OSError:
        return []


def _win_write_recorded(entries: Sequence[str]) -> None:
    record = _win_record_file()
    if not entries:
        try:
            record.unlink()
        except OSError:
            pass
        return
    ensure_private_dir(record.parent)
    write_text_atomic(record, "".join(entry + "\n" for entry in entries))


def windows_setup_path(dirs: Sequence[str], remove: bool, remove_all: bool, machine: bool) -> int:
    import winreg

    scope = "machine PATH" if machine else "user PATH"
    if machine and not _win_is_elevated():
        warn("changing the machine PATH needs an elevated terminal. aiup never elevates itself.")
        return 1
    try:
        value, value_type = _win_read_path(machine)
    except OSError as exc:
        warn("could not read the " + scope + ": " + short_error(exc))
        return 1
    if value_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
        warn("the " + scope + " is not a text value; left as it is")
        return 1
    recorded = [] if machine else _win_recorded()
    new_value = value
    added: List[str] = []
    if remove:
        targets = list(dirs) + (recorded if remove_all else [])
        wanted = {_win_norm(d) for d in targets}
        parts = value.split(";")
        kept = [part for part in parts if not part.strip() or _win_norm(part) not in wanted]
        new_value = ";".join(kept)
    else:
        for directory in reversed(list(dirs)):
            if not _win_path_has(new_value, directory):
                new_value = directory + (";" + new_value if new_value else "")
                added.append(directory)
    if new_value == value:
        print("The " + scope + " already " + ("lacks" if remove else "has") + " " + ", ".join(dirs or recorded))
    else:
        hive = winreg.HKEY_LOCAL_MACHINE if machine else winreg.HKEY_CURRENT_USER
        try:
            with winreg.OpenKey(hive, WIN_MACHINE_KEY if machine else WIN_USER_KEY, 0,
                                winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "Path", 0, value_type, new_value)
        except OSError as exc:
            warn("could not write the " + scope + ": " + short_error(exc))
            return 1
        _win_broadcast()
        print("Updated the " + scope + ". Programs that are already open keep their old PATH until restarted.")
    if not machine:
        try:
            if remove:
                gone = {_win_norm(d) for d in dirs}
                _win_write_recorded([] if remove_all else [r for r in recorded if _win_norm(r) not in gone])
            elif added:
                _win_write_recorded(recorded + [d for d in added if d not in recorded])
        except (OSError, LauncherError) as exc:
            warn("could not record the PATH entries aiup added: " + short_error(exc))
    process_parts = os.environ.get("PATH", "").split(";")
    if not remove:
        for directory in reversed(list(dirs)):
            if not any(_win_norm(p) == _win_norm(directory) for p in process_parts):
                os.environ["PATH"] = directory + ";" + os.environ.get("PATH", "")
    return 0


def windows_check(dirs: Sequence[str]) -> int:
    for label, machine in (("user PATH", False), ("machine PATH", True)):
        try:
            value, _value_type = _win_read_path(machine)
        except OSError as exc:
            print(label + ": " + short_error(exc))
            continue
        for directory in dirs:
            print(label + ": " + ("has " if _win_path_has(value, directory) else "missing ") + directory)
    for directory in dirs:
        print("this shell: " + ("has " if _win_path_has(os.environ.get("PATH", ""), directory) else "missing ")
              + directory)
    return 0


def setup_path(args: Sequence[str]) -> int:
    remove = remove_all = machine = check = False
    dirs: List[str] = []
    for arg in args:
        if arg == "--remove":
            remove = True
        elif arg == "--all":
            remove_all = True
        elif arg == "--system":
            machine = True
        elif arg == "--check":
            check = True
        elif arg in ("-h", "--help"):
            print(SETUP_PATH_USAGE)
            return 0
        elif arg.startswith("-"):
            print("aiup: unknown setup-path option '" + arg + "'.\n" + SETUP_PATH_USAGE, file=sys.stderr)
            return 2
        else:
            dirs.append(arg)
    if remove_all and not remove:
        print("aiup: --all goes with --remove.", file=sys.stderr)
        return 2
    if not dirs and not remove_all:
        print(SETUP_PATH_USAGE, file=sys.stderr)
        return 2
    clean: List[str] = []
    for directory in dirs:
        if any(ch in directory for ch in "\n\r\0") or (not IS_WINDOWS and ":" in directory) \
                or (IS_WINDOWS and (";" in directory or '"' in directory)):
            warn("refusing a directory with characters PATH cannot hold: " + repr(directory))
            return 2
        if not os.path.isabs(directory):
            warn("setup-path needs absolute directories: " + directory)
            return 2
        normalized = os.path.normpath(directory)
        if normalized not in clean:
            clean.append(normalized)
    if check:
        return windows_check(clean) if IS_WINDOWS else check_path_files(clean, os.environ)
    if not remove and os.environ.get("AIUP_NO_MODIFY_PATH", "") == "1":
        print("AIUP_NO_MODIFY_PATH=1 is set, so nothing was edited. Add these to PATH yourself:")
        for directory in clean:
            print("  " + directory)
        return 0
    if IS_WINDOWS:
        return windows_setup_path(clean, remove, remove_all, machine)
    if machine:
        warn("--system is for Windows. On Linux the shared aiup command goes in /usr/local/bin,"
             " which is already on PATH.")
        return 1
    return posix_setup_path(clean, remove, remove_all)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Sequence[str]) -> int:
    if sys.version_info[:2] < MIN_PYTHON:
        die("aiup needs Python 3.9 or newer; this is " + sys.version.split()[0] + " at " + sys.executable
            + ". Run the aiup installer again to pick a newer Python.")
    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None and geteuid() == 0 and os.environ.get("AIUP_ALLOW_ROOT", "") != "1":
        die("refusing to run as root. Run aiup as your own user (AIUP_ALLOW_ROOT=1 allows it, for containers).")
    if argv and argv[0] == "setup-path":
        return setup_path(argv[1:])
    launch(argv)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
