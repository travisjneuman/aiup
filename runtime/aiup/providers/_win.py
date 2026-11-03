"""Helpers the Windows providers share: read commands, PowerShell JSON calls, folders.

``run_w`` runs a read-only command and gives the exit status unsigned, the
way winget's HRESULT codes read. ``code_forms`` lists a code both ways for
``Step.ok_codes``. PowerShell scripts travel as ``-EncodedCommand`` with no
profile. ``Memo`` is the per-run cache for bulk reads.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple, TypeVar

from aiup.versions import version_cmp

if TYPE_CHECKING:
    from aiup.engine.context import Context



WINDOWS = frozenset({"windows"})
READ_TIMEOUT = 30.0                  # winget and choco start slowly
SLOW_TIMEOUT = 120.0                 # bulk reads that may touch the network
SMALL_MAX_BYTES = 1024 * 1024
BULK_MAX_BYTES = 8 * 1024 * 1024
FILE_MAX_BYTES = 4 * 1024 * 1024     # JSON files aiup reads itself
MEMO_TTL = 300.0
STORE_NOTE = "managed by Microsoft Store"   # winget msstore and Appx copies
_T = TypeVar("_T")


class ReadOut(NamedTuple):
    """What a read command printed.

    ``code`` is the exit status as an unsigned 32-bit number (winget's HRESULT
    codes are easier to compare that way), or None when the command did not
    start, timed out or printed more than the cap. ``error`` says why, and
    ``timed_out`` is True when the time limit stopped it.
    """

    code: Optional[int]
    out: str
    err: str
    error: str
    timed_out: bool = False


def unsigned(code: int) -> int:
    """An exit status as Windows stores it (``-1978335212`` becomes ``0x8A150014``)."""
    return code & 0xFFFFFFFF


def code_forms(*codes: int) -> Tuple[int, ...]:
    """Each code in both forms a caller might compare against: unsigned and signed.

    Python reports Windows exit codes unsigned; PowerShell and some wrappers
    report them signed. Listing both keeps ``Step.ok_codes`` right either way.
    """
    forms: List[int] = []
    for code in codes:
        value = unsigned(code)
        for form in (value, value - 0x100000000 if value >= 0x80000000 else value):
            if form not in forms:
                forms.append(form)
    return tuple(forms)


def run_w(ctx: "Context", argv: Sequence[str], timeout: float = READ_TIMEOUT,
          max_bytes: int = SMALL_MAX_BYTES, env: Optional[Dict[str, str]] = None) -> ReadOut:
    """Run a read-only command through ``ctx.run_read`` and normalize the result."""
    if env:
        result = ctx.run_read(tuple(argv), timeout, max_bytes, env=env)
    else:
        result = ctx.run_read(tuple(argv), timeout, max_bytes)
    error = str(getattr(result, "error", "") or "")
    timed_out = bool(getattr(result, "timed_out", False))
    if timed_out:
        error = error or "did not answer within {:.0f} seconds".format(timeout)
    elif getattr(result, "truncated", False):
        error = error or "printed more than {} bytes".format(max_bytes)
    code = getattr(result, "returncode", None)
    if error or code is None:
        return ReadOut(None, "", str(getattr(result, "stderr", "") or ""), error or "did not finish", timed_out)
    return ReadOut(unsigned(int(code)), str(result.stdout or ""), str(result.stderr or ""), "")


def is_windows(ctx: "Context") -> bool:
    """True when aiup runs on Windows."""
    return getattr(ctx.platform, "name", "") == "windows"


def which(ctx: "Context", command: str) -> Optional[str]:
    """Absolute path of ``command`` on PATH (PATHEXT applies), or None."""
    return ctx.platform.which(command)


def env_dir(name: str, fallback: str = "") -> Optional[Path]:
    """A folder from an environment variable, or ``fallback`` under it, if absolute."""
    value = os.environ.get(name, "")
    if not value:
        return None
    path = Path(value)
    if fallback:
        path = path / fallback
    return path if path.is_absolute() else None


def home_dir() -> Path:
    """The user's profile folder (``%USERPROFILE%``)."""
    return env_dir("USERPROFILE") or Path.home()


def windows_powershell() -> Optional[str]:
    """Absolute path of Windows PowerShell 5.1, never looked up on PATH."""
    root = env_dir("SystemRoot") or env_dir("windir")
    if root is None:
        return None
    exe = root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(exe) if exe.is_file() else None


def any_powershell(ctx: "Context") -> Optional[str]:
    """pwsh 7 when it is on PATH, else Windows PowerShell 5.1."""
    return which(ctx, "pwsh") or windows_powershell()


def encoded_command(script: str) -> str:
    """``-EncodedCommand`` text for a fixed script: UTF-16LE, then base64."""
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


_PS_PRELUDE = (
    "$ErrorActionPreference = 'Stop'\n"
    "$ProgressPreference = 'SilentlyContinue'\n"
    "try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }\n"
)


def powershell_argv(exe: str, script: str) -> Tuple[str, ...]:
    """argv that runs a fixed script with no profile and no prompts.

    The script travels as ``-EncodedCommand``, so no quoting or execution
    policy applies to it, and it always starts with UTF-8 output.
    """
    return (exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_command(_PS_PRELUDE + script))


def powershell_env(exe: str) -> Dict[str, str]:
    """PSModulePath fix for Windows PowerShell 5.1 started below PowerShell 7 (see the platform layer)."""
    from aiup.platform.windows import windows_powershell_env

    return windows_powershell_env(exe)


def powershell_json(ctx: "Context", exe: str, script: str, timeout: float = SLOW_TIMEOUT,
                    max_bytes: int = BULK_MAX_BYTES) -> Tuple[Optional[object], str]:
    """Run a fixed PowerShell script that prints one JSON document.

    Returns ``(value, "")`` or ``(None, reason)``. Text before the JSON (a
    module's warning, for example) is skipped.
    """
    out = run_w(ctx, powershell_argv(exe, script), timeout, max_bytes, powershell_env(exe))
    if out.code is None:
        return None, "PowerShell " + out.error
    if out.code != 0:
        return None, first_line(out.err or out.out) or "PowerShell exited {}".format(out.code)
    return parse_json_text(out.out)


def parse_json_text(text: str) -> Tuple[Optional[object], str]:
    """The first JSON array or object in ``text``."""
    starts = [index for index in (text.find("["), text.find("{")) if index >= 0]
    if not starts:
        return None, "no JSON in the output" if text.strip() else "empty output"
    try:
        return json.loads(text[min(starts):]), ""
    except ValueError as exc:
        return None, "unreadable JSON ({})".format(exc)


def read_json_file(path: Path, max_bytes: int = FILE_MAX_BYTES) -> Optional[object]:
    """A small JSON file, or None when missing, too large or unreadable."""
    text = read_text_file(path, max_bytes)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def read_text_file(path: Path, max_bytes: int = FILE_MAX_BYTES) -> Optional[str]:
    """A small UTF-8 text file (BOM allowed), or None."""
    try:
        if path.stat().st_size > max_bytes:
            return None
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            return handle.read(max_bytes)
    except OSError:
        return None


def first_line(text: str) -> str:
    """The first non-blank line of ``text``, stripped."""
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def newest(versions: Iterable[str]) -> str:
    """The newest of several version strings ("" when there are none)."""
    best = ""
    for version in versions:
        if version and (not best or version_cmp(version, best) > 0):
            best = version
    return best


def self_updated(installed: str, latest: str) -> bool:
    """True when the installed copy is newer than what the channel offers.

    Open question 6: an app that updated itself must never get an older build
    from a package manager. The engine reports such a tool ``self-updated``.
    """
    return bool(installed) and bool(latest) and version_cmp(installed, latest) > 0


def path_parts(path: str) -> Tuple[str, ...]:
    """Lower-case components of a resolved Windows path, for prefix checks."""
    try:
        resolved = os.path.realpath(path)
    except (OSError, ValueError):
        resolved = path
    return tuple(part for part in re.split(r"[\\/]+", resolved.lower()) if part)


def under(parts: Sequence[str], root: Optional[Path]) -> Optional[Tuple[str, ...]]:
    """The components of ``parts`` below ``root``, or None when it is not inside."""
    if root is None:
        return None
    base = path_parts(str(root))
    if not base or len(parts) <= len(base) or tuple(parts[:len(base)]) != base:
        return None
    return tuple(parts[len(base):])


def scratch_file(ctx: "Context", stem: str, suffix: str) -> Path:
    """A fresh private file name under aiup's cache folder (the file is not created)."""
    folder = Path(ctx.dirs.cache) / "tmp"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "{}-{}-{}{}".format(stem, os.getpid(), secrets.token_hex(6), suffix)


class Memo:
    """A small thread-safe in-process cache with a time limit per entry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: Dict[str, Tuple[float, object]] = {}

    def get(self, key: str, ttl: float, produce: Callable[[], _T]) -> _T:
        """The cached value for ``key``, produced again when older than ``ttl``."""
        now = time.monotonic()
        with self._lock:
            hit = self._values.get(key)
            if hit is not None and now - hit[0] < ttl:
                return hit[1]  # type: ignore[return-value]
        value = produce()
        with self._lock:
            self._values[key] = (time.monotonic(), value)
        return value

    def clear(self) -> None:
        """Forget everything (after a mutation)."""
        with self._lock:
            self._values.clear()
