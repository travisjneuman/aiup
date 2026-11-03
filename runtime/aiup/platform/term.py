"""Terminal setup: tty checks, Windows VT mode and code pages, colors, glyphs.

Call ``enable()`` once at start. On Windows it turns on
ENABLE_VIRTUAL_TERMINAL_PROCESSING for stdout and stderr, switches the console
to the UTF-8 code page (65001) and restores the old modes and code pages at
exit. On every platform it makes stdout and stderr replace characters they
cannot encode instead of raising.

Color rule (``color_enabled``), first match wins:

1. ``NO_COLOR`` set to anything non-empty: no color (``--plain`` sets it).
2. ``FORCE_COLOR`` set, not empty, and not ``0`` or ``false``: color.
3. ``TERM=dumb``: no color.
4. The stream is not a terminal: no color.
5. Windows console where VT mode could not be turned on: no color.

Glyph rule (``use_unicode``), first match wins:

1. ``AIUP_ASCII=1``: ASCII.
2. The stream's encoding is not UTF-8: ASCII.
3. ``TERM=linux`` (the Linux text console, whose fonts lack most glyphs): ASCII.
4. Windows legacy console host: ASCII. A console counts as legacy when none of
   the markers newer terminals set is present (``WT_SESSION`` for Windows
   Terminal, ``TERM_PROGRAM``, ``ConEmuANSI=ON``, ``TERM``, ``WEZTERM_PANE``).
   conhost does no font fallback and its default fonts lack ``◐`` and ``❯``.
5. Otherwise Unicode.

The TUI may apply its own rule on top; these are the defaults.
"""

from __future__ import annotations

import atexit
import codecs
import os
import shutil
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TextIO

_WINDOWS = sys.platform == "win32"

_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
_STD_OUTPUT_HANDLE = -11 & 0xFFFFFFFF
_STD_ERROR_HANDLE = -12 & 0xFFFFFFFF
_UTF8_CODEPAGE = 65001


@dataclass(frozen=True)
class GlyphSet:
    """Characters the TUI and reports draw with."""

    installed: str      # row mark: installed through aiup's channel
    on_disk: str        # row mark: present, installed some other way
    absent: str         # row mark: not installed
    detected: str       # row mark: detected-only software
    manual: str         # row mark: needs a manual step
    pointer: str        # fzf prompt pointer
    bar: str            # category meter cell
    rule: str           # horizontal rule
    dot: str            # separator between header parts
    border: str         # fzf --border style


UNICODE_GLYPHS = GlyphSet(
    installed="●", on_disk="◐", absent="○", detected="◇", manual="◆",
    pointer="❯", bar="━", rule="─", dot="·", border="rounded",
)

# Spec 9.5: "* ~ o ? !", ">", square frame and "#".
ASCII_GLYPHS = GlyphSet(
    installed="*", on_disk="~", absent="o", detected="?", manual="!",
    pointer=">", bar="#", rule="-", dot="|", border="sharp",
)


@dataclass
class _ConsoleState:
    """What ``enable()`` changed, so ``restore()`` can put it back."""

    enabled: bool = False
    vt: Dict[int, bool] = field(default_factory=dict)          # fd -> VT works
    old_modes: Dict[int, int] = field(default_factory=dict)    # fd -> mode before
    old_output_cp: int = 0
    old_input_cp: int = 0
    changed_output_cp: bool = False
    changed_input_cp: bool = False


_STATE = _ConsoleState()
_LOCK = threading.Lock()


@dataclass(frozen=True)
class TermCaps:
    """Terminal facts after ``enable()``."""

    stdin_tty: bool
    stdout_tty: bool
    stderr_tty: bool
    color_stdout: bool
    color_stderr: bool
    truecolor: bool
    unicode: bool
    vt: bool                  # Windows: VT mode is on for stderr. Elsewhere: True.
    original_codepage: int    # Windows console output code page before enable(); 0 elsewhere


def is_tty(stream: Optional[Any]) -> bool:
    """True when ``stream`` is an open terminal. Never raises."""
    if stream is None:
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def interactive() -> bool:
    """True when stdin and stderr are both terminals (Context.interactive)."""
    return is_tty(sys.stdin) and is_tty(sys.stderr)


def columns(default: int = 80) -> int:
    """Terminal width, or ``default`` when it cannot be read."""
    try:
        return max(20, shutil.get_terminal_size((default, 24)).columns)
    except (OSError, ValueError):
        return default


def enable() -> TermCaps:
    """Prepare the terminal once per process and report what it supports."""
    with _LOCK:
        if not _STATE.enabled:
            _STATE.enabled = True
            if _WINDOWS:
                _windows_enable()
                atexit.register(restore)
            _reconfigure_streams()
    return caps()


def caps() -> TermCaps:
    """Current terminal facts (call ``enable()`` first on Windows)."""
    return TermCaps(
        stdin_tty=is_tty(sys.stdin),
        stdout_tty=is_tty(sys.stdout),
        stderr_tty=is_tty(sys.stderr),
        color_stdout=color_enabled(sys.stdout),
        color_stderr=color_enabled(sys.stderr),
        truecolor=truecolor(),
        unicode=use_unicode(sys.stderr),
        vt=_vt_ok(sys.stderr) if _WINDOWS else True,
        original_codepage=_STATE.old_output_cp,
    )


def restore() -> None:
    """Put back the console modes and code pages ``enable()`` changed."""
    if not _WINDOWS:
        return
    with _LOCK:
        kernel32 = _kernel32()
        if kernel32 is None:
            return
        for fd, mode in list(_STATE.old_modes.items()):
            handle = kernel32.GetStdHandle(_STD_OUTPUT_HANDLE if fd == 1 else _STD_ERROR_HANDLE)
            if handle:
                kernel32.SetConsoleMode(handle, mode)
        _STATE.old_modes.clear()
        if _STATE.changed_output_cp and _STATE.old_output_cp:
            kernel32.SetConsoleOutputCP(_STATE.old_output_cp)
            _STATE.changed_output_cp = False
        if _STATE.changed_input_cp and _STATE.old_input_cp:
            kernel32.SetConsoleCP(_STATE.old_input_cp)
            _STATE.changed_input_cp = False


def original_output_codepage() -> int:
    """The Windows console output code page before ``enable()`` changed it.

    Falls back to the current one when ``enable()`` has not run, and 0 when
    there is no console (or not on Windows). ``proc.decode_output`` uses it
    to read programs that write in the console's old code page.
    """
    if not _WINDOWS:
        return 0
    if _STATE.old_output_cp:
        return _STATE.old_output_cp
    kernel32 = _kernel32()
    if kernel32 is None:
        return 0
    try:
        return int(kernel32.GetConsoleOutputCP())
    except OSError:
        return 0


def color_enabled(stream: Optional[TextIO] = None) -> bool:
    """True when ANSI colors should be written to ``stream`` (default stderr)."""
    target = sys.stderr if stream is None else stream
    if os.environ.get("NO_COLOR", ""):
        return False
    force = os.environ.get("FORCE_COLOR", "").strip().lower()
    if force and force not in ("0", "false"):
        return True
    if os.environ.get("TERM", "") == "dumb":
        return False
    if not is_tty(target):
        return False
    if _WINDOWS and not _vt_ok(target):
        return False
    return True


def truecolor() -> bool:
    """True when the terminal says it takes 24-bit color."""
    if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
        return True
    if _WINDOWS and os.environ.get("WT_SESSION"):
        return True
    term = os.environ.get("TERM", "")
    return term.endswith("-direct") or term.endswith("truecolor")


def use_unicode(stream: Optional[TextIO] = None) -> bool:
    """True when the Unicode glyph set should be used (rule in the module doc)."""
    target = sys.stderr if stream is None else stream
    if os.environ.get("AIUP_ASCII", "") == "1":
        return False
    if not _encoding_is_utf8(getattr(target, "encoding", None)):
        return False
    if os.environ.get("TERM", "") == "linux":
        return False
    if _WINDOWS and is_tty(target) and legacy_console():
        return False
    return True


def glyphs(stream: Optional[TextIO] = None) -> GlyphSet:
    """The glyph set ``use_unicode`` picks for ``stream``."""
    return UNICODE_GLYPHS if use_unicode(stream) else ASCII_GLYPHS


def legacy_console() -> bool:
    """True on Windows when no marker of a newer terminal is set."""
    if not _WINDOWS:
        return False
    if os.environ.get("ConEmuANSI", "").upper() == "ON":
        return False
    markers = ("WT_SESSION", "TERM_PROGRAM", "TERM", "WEZTERM_PANE")
    return not any(os.environ.get(name) for name in markers)


# ----- internals -----------------------------------------------------------


def _encoding_is_utf8(encoding: Optional[str]) -> bool:
    if not encoding:
        return False
    try:
        return codecs.lookup(encoding).name == "utf-8"
    except LookupError:
        return False


def _reconfigure_streams() -> None:
    """Replace unencodable characters; UTF-8 output on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            if _WINDOWS:
                reconfigure(encoding="utf-8", errors="replace")
            else:
                reconfigure(errors="replace")
        except (ValueError, OSError, LookupError):
            continue


def _vt_ok(stream: Any) -> bool:
    try:
        fd = stream.fileno()
    except (AttributeError, ValueError, OSError):
        return False
    return _STATE.vt.get(fd, False)


_KERNEL32: Optional[Any] = None


def _kernel32() -> Optional[Any]:
    """kernel32 with argument types set, or None when ctypes is unusable."""
    if not _WINDOWS:
        return None
    global _KERNEL32
    if _KERNEL32 is not None:
        return _KERNEL32
    try:
        import ctypes
        from ctypes import wintypes

        k = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        k.GetStdHandle.argtypes = [wintypes.DWORD]
        k.GetStdHandle.restype = wintypes.HANDLE
        k.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.GetConsoleMode.restype = wintypes.BOOL
        k.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.SetConsoleMode.restype = wintypes.BOOL
        k.GetConsoleOutputCP.argtypes = []
        k.GetConsoleOutputCP.restype = wintypes.UINT
        k.GetConsoleCP.argtypes = []
        k.GetConsoleCP.restype = wintypes.UINT
        k.SetConsoleOutputCP.argtypes = [wintypes.UINT]
        k.SetConsoleOutputCP.restype = wintypes.BOOL
        k.SetConsoleCP.argtypes = [wintypes.UINT]
        k.SetConsoleCP.restype = wintypes.BOOL
    except (ImportError, OSError, AttributeError):
        return None
    _KERNEL32 = k
    return k



def _windows_enable() -> None:
    """VT mode on stdout and stderr, UTF-8 code pages. Failures leave plain output."""
    kernel32 = _kernel32()
    if kernel32 is None:
        return
    import ctypes
    from ctypes import wintypes

    for fd, which in ((1, _STD_OUTPUT_HANDLE), (2, _STD_ERROR_HANDLE)):
        handle = kernel32.GetStdHandle(which)
        mode = wintypes.DWORD(0)
        if not handle or not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            _STATE.vt[fd] = False  # not a console (pipe or file)
            continue
        old = int(mode.value)
        if old & _ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            _STATE.vt[fd] = True
            continue
        if kernel32.SetConsoleMode(handle, old | _ENABLE_VIRTUAL_TERMINAL_PROCESSING):
            _STATE.old_modes[fd] = old
            _STATE.vt[fd] = True
        else:
            _STATE.vt[fd] = False

    output_cp = int(kernel32.GetConsoleOutputCP())
    input_cp = int(kernel32.GetConsoleCP())
    _STATE.old_output_cp = output_cp
    _STATE.old_input_cp = input_cp
    if output_cp and output_cp != _UTF8_CODEPAGE and kernel32.SetConsoleOutputCP(_UTF8_CODEPAGE):
        _STATE.changed_output_cp = True
    if input_cp and input_cp != _UTF8_CODEPAGE and kernel32.SetConsoleCP(_UTF8_CODEPAGE):
        _STATE.changed_input_cp = True
