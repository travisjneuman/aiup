"""Child processes: bounded reads, logged steps, and output decoding.

``run_read`` is for read-only provider queries: no terminal, stdin closed,
output capped, a wall-clock limit (macOS ``bounded_provider_capture``).

``run_step`` is for the commands an update runs: output streams to the run
log line by line (and to the terminal with ``echo``), the caller gets a tick
for its heartbeat, Ctrl-C gives the child a grace period and then stops its
whole tree, and a timeout stops the tree too (macOS ``run_with_heartbeat``).

``decode_output`` turns raw bytes into text: UTF-8 first, then on Windows
the console's original code page, the OEM code page and the ANSI code page,
then UTF-8 with replacement. It also removes terminal escape sequences,
carriage-return redraws and winget's spinner and progress-bar lines.

Every call takes an argv list; nothing runs through a shell. On Windows the
command is looked up with PATHEXT (so ``npm`` finds ``npm.cmd``), and
arguments to a ``.cmd`` or ``.bat`` file that cmd.exe would interpret
(``" % & | < > ^`` and line breaks) are refused.
"""

from __future__ import annotations

import codecs
import collections
import functools
import locale
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import IO, Any, Callable, Deque, Dict, List, Mapping, Optional, Sequence, Tuple

_WINDOWS = sys.platform == "win32"

DEFAULT_READ_MAX_BYTES = 1024 * 1024
STDERR_MAX_BYTES = 64 * 1024
TAIL_LINES = 20
_CHUNK = 65536
_LINE_LIMIT = 64 * 1024

_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_NO_WINDOW = 0x08000000
_BATCH_UNSAFE = frozenset('"%&|<>^\r\n')

_ECHO_LOCK = threading.Lock()


class ProcError(Exception):
    """A command was refused before it started (not found, unsafe arguments)."""


@dataclass(frozen=True)
class ReadResult:
    """Outcome of ``run_read``."""

    argv: Tuple[str, ...]
    returncode: Optional[int]     # None when the command did not start or was stopped
    stdout: str
    stderr: str
    duration: float
    timed_out: bool = False
    truncated: bool = False       # stdout passed max_bytes; the command was stopped
    error: str = ""               # why it did not start, when it did not

    @property
    def ok(self) -> bool:
        """True when the command ran to the end, exited 0, and fit the cap."""
        return not self.error and not self.timed_out and not self.truncated and self.returncode == 0


@dataclass(frozen=True)
class StepResult:
    """Outcome of ``run_step``."""

    argv: Tuple[str, ...]
    returncode: Optional[int]     # None when the command did not start
    duration: float
    timed_out: bool = False
    interrupted: bool = False     # Ctrl-C or the cancel event stopped it
    error: str = ""
    tail: Tuple[str, ...] = ()    # last lines of output, already decoded and cleaned

    def ok(self, ok_codes: Sequence[int] = (0,)) -> bool:
        """True when the step ran to the end with an accepted exit code."""
        return (
            not self.error
            and not self.timed_out
            and not self.interrupted
            and self.returncode is not None
            and self.returncode in ok_codes
        )


# ----- argv and environment ------------------------------------------------


def resolve_argv(argv: Sequence[str], env: Optional[Mapping[str, str]] = None) -> List[str]:
    """argv with the command replaced by its absolute path.

    Raises ``ProcError`` when the command is not found or when a Windows
    batch file would get arguments cmd.exe interprets. ``env``'s PATH is
    used for the lookup when it has one.
    """
    if not argv:
        raise ValueError("empty argv")
    args = [str(arg) for arg in argv]
    if any("\0" in arg for arg in args):
        raise ProcError("refusing an argument with a NUL character")
    command = args[0]
    from aiup.platform import current

    path_value = env.get("PATH") if env else None
    resolved = current().which(command, path_value or None)
    if resolved is None:
        raise ProcError("command not found: " + command)
    args[0] = resolved
    if _WINDOWS and resolved.lower().endswith((".cmd", ".bat")):
        for arg in args[1:]:
            if any(ch in _BATCH_UNSAFE for ch in arg):
                raise ProcError(
                    "refusing to pass characters cmd.exe would interpret to " + os.path.basename(resolved)
                )
    return args


def child_env(extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """aiup's environment plus ``extra``. Child Python on Windows runs in UTF-8 mode."""
    env = dict(os.environ)
    if extra:
        for key, value in extra.items():
            if not key or "=" in key or "\0" in key or "\0" in value:
                raise ProcError("refusing an invalid environment variable: " + repr(key))
            env[key] = value
    if _WINDOWS:
        env.setdefault("PYTHONUTF8", "1")
    return env


def _popen_flags(new_group: bool) -> Dict[str, Any]:
    """Popen keywords that put the child in its own group (or not)."""
    if _WINDOWS:
        flags = _CREATE_NEW_PROCESS_GROUP if new_group else 0
        if not _has_console():
            flags |= _CREATE_NO_WINDOW
        return {"creationflags": flags} if flags else {}
    return {"start_new_session": True} if new_group else {}


@functools.lru_cache(maxsize=1)
def _has_console() -> bool:
    """Windows: True when aiup has a console (console children then share it)."""
    try:
        import ctypes

        return bool(ctypes.windll.kernel32.GetConsoleWindow())  # type: ignore[attr-defined]
    except (ImportError, OSError, AttributeError):
        return True


def install_interrupt_handlers() -> None:
    """Map Windows Ctrl-Break to KeyboardInterrupt, so it ends with exit 130 too.

    Call once from the main thread at start. No effect on Linux or macOS,
    where Ctrl-C already raises KeyboardInterrupt.
    """
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is None:
        return
    try:
        signal.signal(sigbreak, signal.default_int_handler)
    except (ValueError, OSError):
        return


# ----- reads ---------------------------------------------------------------


def run_read(
    argv: Sequence[str],
    timeout: float = 5.0,
    max_bytes: int = DEFAULT_READ_MAX_BYTES,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[str] = None,
    input_bytes: Optional[bytes] = None,
    clean: bool = True,
) -> ReadResult:
    """Run a read-only command and return its decoded output.

    The child gets no terminal (its own session on Linux and macOS, its own
    process group on Windows), stdin closed unless ``input_bytes`` is given,
    and at most ``timeout`` seconds. Stdout over ``max_bytes`` stops the
    command and marks the result truncated. Stderr keeps its first 64 KiB.
    Ctrl-C stops the child's tree and is raised again.
    """
    start = time.monotonic()
    args_tuple = tuple(str(arg) for arg in argv)
    try:
        args = resolve_argv(argv, env)
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env(env),
            cwd=cwd,
            **_popen_flags(True),
        )
    except (ProcError, OSError) as exc:
        return ReadResult(args_tuple, None, "", "", time.monotonic() - start, error=_error_text(exc))

    out = _Capture(max_bytes)
    err = _Capture(STDERR_MAX_BYTES, stop_on_overflow=False)
    threads = [
        _start_thread(out.pump, proc.stdout),
        _start_thread(err.pump, proc.stderr),
    ]
    if input_bytes is not None:
        threads.append(_start_thread(_feed, proc.stdin, input_bytes))

    timed_out = False
    try:
        deadline = start + max(0.1, timeout)
        while True:
            try:
                proc.wait(timeout=0.05)
                break
            except subprocess.TimeoutExpired:
                if out.overflow.is_set():
                    _stop_now(proc)
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    _stop_now(proc)
                    break
    except KeyboardInterrupt:
        _stop_now(proc)
        raise
    for thread in threads:
        thread.join(timeout=2.0)

    truncated = out.overflow.is_set()
    returncode = None if (timed_out or truncated) else proc.returncode
    return ReadResult(
        argv=tuple(args),
        returncode=returncode,
        stdout=decode_output(out.data(), clean=clean),
        stderr=decode_output(err.data(), clean=clean),
        duration=time.monotonic() - start,
        timed_out=timed_out,
        truncated=truncated,
    )


def run_feed(argv: Sequence[str], data: bytes, timeout: float = 10.0,
             env: Optional[Mapping[str, str]] = None) -> Optional[int]:
    """Run a command with ``data`` on stdin and every output discarded.

    For clipboard tools such as wl-copy and xclip, which leave a process
    behind that would hold a captured pipe open. Returns the exit code, or
    None when the command did not start or did not finish in time.
    """
    try:
        args = resolve_argv(argv, env)
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=child_env(env),
            **_popen_flags(True),
        )
    except (ProcError, OSError):
        return None
    try:
        proc.communicate(input=data, timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop_now(proc)
        return None
    except (OSError, ValueError):
        _stop_now(proc)
        return None
    except KeyboardInterrupt:
        _stop_now(proc)
        raise
    return proc.returncode


class _Capture:
    """Collects one pipe up to a byte cap, in a reader thread."""

    def __init__(self, limit: int, stop_on_overflow: bool = True) -> None:
        self.limit = max(0, limit)
        self.stop_on_overflow = stop_on_overflow
        self.overflow = threading.Event()
        self._chunks: List[bytes] = []
        self._size = 0
        self._lock = threading.Lock()

    def pump(self, stream: Optional[IO[bytes]]) -> None:
        """Read until end of file; keep at most ``limit`` bytes."""
        if stream is None:
            return
        try:
            while True:
                chunk = _read_chunk(stream)
                if not chunk:
                    return
                with self._lock:
                    room = self.limit - self._size
                    if room > 0:
                        kept = chunk[:room]
                        self._chunks.append(kept)
                        self._size += len(kept)
                    if len(chunk) > room:
                        if self.stop_on_overflow:
                            self.overflow.set()
                            return
        except (OSError, ValueError):
            return
        finally:
            _close_quietly(stream)

    def data(self) -> bytes:
        """What has been collected so far."""
        with self._lock:
            return b"".join(self._chunks)


def _read_chunk(stream: IO[bytes]) -> bytes:
    read1 = getattr(stream, "read1", None)
    if read1 is not None:
        return bytes(read1(_CHUNK))
    return bytes(stream.read(_CHUNK))


def _feed(stream: Optional[IO[bytes]], data: bytes) -> None:
    if stream is None:
        return
    try:
        stream.write(data)
    except (OSError, ValueError):
        pass
    finally:
        _close_quietly(stream)


def _start_thread(target: Callable[..., None], *args: Any) -> threading.Thread:
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()
    return thread


def _close_quietly(stream: Any) -> None:
    try:
        stream.close()
    except (OSError, ValueError):
        pass


def _stop_now(proc: "subprocess.Popen[Any]") -> None:
    """Stop a child and its tree at once, then reap it."""
    from aiup.platform import current

    if proc.poll() is None:
        current().kill_tree(proc.pid, grace=0.5)
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=2.0)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _error_text(exc: BaseException) -> str:
    if isinstance(exc, ProcError):
        return str(exc)
    if isinstance(exc, FileNotFoundError):
        return "command not found: " + (exc.filename or str(exc))
    if isinstance(exc, PermissionError):
        return "permission denied: " + (exc.filename or str(exc))
    return str(exc) or exc.__class__.__name__


# ----- steps ---------------------------------------------------------------


def _stderr_fd() -> Optional[int]:
    """aiup's stderr file descriptor, or None (keep stdout) when it has none."""
    try:
        return sys.stderr.fileno() if sys.stderr is not None else None
    except (AttributeError, OSError, ValueError):
        return None


def run_step(
    argv: Sequence[str],
    log_path: str,
    *,
    echo: Optional[IO[str]] = None,
    timeout: Optional[float] = None,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[str] = None,
    interactive: bool = False,
    cancel: Optional[threading.Event] = None,
    on_tick: Optional[Callable[[float], None]] = None,
    tick_seconds: float = 1.0,
    grace: float = 5.0,
    new_group: bool = False,
    stdout_to_stderr: bool = False,
) -> StepResult:
    """Run one step of an action and log its output.

    Non-interactive steps get stdin closed; stdout and stderr are merged,
    decoded and cleaned line by line, appended to ``log_path`` and, when
    ``echo`` is given, written to it too (``--verbose`` passes stderr).

    Interactive steps (sudo prompts, AUR reviews) use the real terminal for
    stdin, stdout and stderr, so their output is not logged; the log gets
    one line saying so. ``stdout_to_stderr=True`` (``--json`` runs) sends an
    interactive child's stdout to aiup's stderr, so only JSON reaches stdout.

    ``on_tick(elapsed)`` runs about every ``tick_seconds`` while the child
    runs, in the calling thread, for the heartbeat. Ctrl-C in the calling
    thread, or ``cancel`` being set (parallel lanes), waits up to ``grace``
    seconds for the child and then stops its tree; the result then has
    ``interrupted=True`` and KeyboardInterrupt is not raised again, so the
    caller must check it. A second Ctrl-C during the wait stops the tree at
    once. ``timeout`` stops the tree when it passes.

    By default the child stays in aiup's process group so terminal Ctrl-C
    and sudo prompts reach it (section 9.1). ``new_group=True`` detaches it.
    The caller writes its own START and DONE lines around the step.
    """
    start = time.monotonic()
    args_tuple = tuple(str(arg) for arg in argv)
    try:
        log = _open_log(log_path)
    except OSError as exc:
        return StepResult(args_tuple, None, 0.0, error="cannot write the log: " + _error_text(exc))

    try:
        try:
            args = resolve_argv(argv, env)
            if interactive:
                _log_line(log, "(interactive step: its output went to the terminal and is not logged)")
                out = _stderr_fd() if stdout_to_stderr else None
                proc = subprocess.Popen(args, stdout=out, env=child_env(env), cwd=cwd, **_popen_flags(new_group))
            else:
                proc = subprocess.Popen(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=child_env(env),
                    cwd=cwd,
                    **_popen_flags(new_group),
                )
        except (ProcError, OSError) as exc:
            message = _error_text(exc)
            _log_line(log, "aiup: " + message)
            return StepResult(args_tuple, None, time.monotonic() - start, error=message)

        tail: Deque[str] = collections.deque(maxlen=TAIL_LINES)
        reader: Optional[threading.Thread] = None
        if not interactive:
            reader = _start_thread(_pump_lines, proc.stdout, log, echo, tail)

        timed_out, interrupted = _supervise(proc, start, timeout, cancel, on_tick, tick_seconds, grace)

        if reader is not None:
            reader.join(timeout=5.0)
        returncode = proc.returncode
        return StepResult(
            argv=tuple(args),
            returncode=returncode,
            duration=time.monotonic() - start,
            timed_out=timed_out,
            interrupted=interrupted,
            tail=tuple(tail),
        )
    finally:
        _close_quietly(log)


def _supervise(
    proc: "subprocess.Popen[Any]",
    start: float,
    timeout: Optional[float],
    cancel: Optional[threading.Event],
    on_tick: Optional[Callable[[float], None]],
    tick_seconds: float,
    grace: float,
) -> Tuple[bool, bool]:
    """Wait for a step's child. Returns (timed_out, interrupted)."""
    next_tick = start + max(0.2, tick_seconds)
    try:
        while True:
            try:
                proc.wait(timeout=0.2)
                return False, False
            except subprocess.TimeoutExpired:
                pass
            now = time.monotonic()
            if cancel is not None and cancel.is_set():
                _stop_gracefully(proc, grace)
                return False, True
            if timeout is not None and now - start >= timeout:
                _stop_now(proc)
                return True, False
            if on_tick is not None and now >= next_tick:
                next_tick = now + max(0.2, tick_seconds)
                on_tick(now - start)
    except KeyboardInterrupt:
        _stop_gracefully(proc, grace)
        return False, True


def _stop_gracefully(proc: "subprocess.Popen[Any]", grace: float) -> None:
    """Give the child ``grace`` seconds to finish, then stop its tree."""
    try:
        proc.wait(timeout=max(0.0, grace))
        return
    except subprocess.TimeoutExpired:
        pass
    except KeyboardInterrupt:
        pass
    _stop_now(proc)


def _open_log(log_path: str) -> IO[bytes]:
    """Open the run log for appending: mode 600 on POSIX, never through a link."""
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(log_path, flags, 0o600)
    return os.fdopen(fd, "ab", buffering=0)


def _log_line(log: IO[bytes], text: str) -> None:
    try:
        log.write((text + "\n").encode("utf-8", errors="replace"))
    except (OSError, ValueError):
        pass


def _pump_lines(stream: Optional[IO[bytes]], log: IO[bytes], echo: Optional[IO[str]], tail: Deque[str]) -> None:
    """Split a step's output into lines; log, echo and remember each kept one."""
    if stream is None:
        return
    buffer = b""
    try:
        while True:
            chunk = _read_chunk(stream)
            if not chunk:
                break
            buffer += chunk
            while True:
                cut = buffer.find(b"\n")
                if cut < 0:
                    break
                _emit_line(buffer[:cut], log, echo, tail)
                buffer = buffer[cut + 1:]
            buffer = _trim_redraws(buffer)
            if len(buffer) > _LINE_LIMIT:
                _emit_line(buffer, log, echo, tail)
                buffer = b""
        if buffer:
            _emit_line(buffer, log, echo, tail)
    except (OSError, ValueError):
        return
    finally:
        _close_quietly(stream)


def _trim_redraws(buffer: bytes) -> bytes:
    """Drop text a later carriage return redrew over, in a line still open.

    Progress bars redraw one line with CR and may never end it, so without
    this the buffer would hold every frame. A CR at the very end is kept: it
    may be the first half of CRLF.
    """
    if len(buffer) < 4096:
        return buffer
    cut = buffer.rfind(b"\r", 0, len(buffer) - 1)
    return buffer[cut + 1:] if cut >= 0 else buffer


def _emit_line(raw: bytes, log: IO[bytes], echo: Optional[IO[str]], tail: Deque[str]) -> None:
    # Splitting UTF-16LE output on b"\n" leaves the newline's high byte at
    # the start of the next line; drop it so the line decodes as UTF-16 again.
    if len(raw) % 2 and raw.startswith(b"\x00"):
        raw = raw[1:]
    line = clean_line(_decode_bytes(raw))
    if line is None:
        return
    _log_line(log, line)
    tail.append(line)
    if echo is not None:
        with _ECHO_LOCK:
            try:
                echo.write(line + "\n")
                echo.flush()
            except (OSError, ValueError):
                pass


# ----- decoding ------------------------------------------------------------

_ANSI_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"           # CSI: colors, cursor moves, erase
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC: titles, links
    r"|\x1b[@-Z\\-_]"                     # other two-byte escapes
)
_SPINNER_CHARS = frozenset("-\\|/")
_PROGRESS_RE = re.compile(
    r"^\s*[▀-▟]+[\s▀-▟]*"
    r"(?:\d[\d.,]*\s*(?:%|[KMGT]?i?B\s*/\s*\d[\d.,]*\s*[KMGT]?i?B))?\s*$"
)


def decode_output(data: bytes, clean: bool = True) -> str:
    """Decode a child's output and, with ``clean``, tidy it for parsing and logs.

    Cleaning removes ANSI escape sequences, keeps only the last text a
    carriage return drew on each line, drops lines that were only a spinner
    frame (``-``, ``\\``, ``|`` or ``/`` alone) or a block-character progress
    bar, and strips trailing spaces (never tabs, so empty trailing TSV fields
    survive). Blank lines in the output are kept.
    """
    if not data:
        return ""
    text = _decode_bytes(data).replace("\r\n", "\n")
    if not clean:
        return text
    lines = (clean_line(line) for line in text.split("\n"))
    return "\n".join(line for line in lines if line is not None)


def clean_line(line: str) -> Optional[str]:
    """One line of output as a person would have seen it, or None to drop it."""
    line = _ANSI_RE.sub("", line.lstrip("﻿"))
    if line.endswith("\r"):
        line = line[:-1]
    if "\r" in line:
        segments = [segment for segment in line.split("\r") if segment.strip()]
        if not segments:
            return None
        line = segments[-1]
    stripped = line.strip()
    if len(stripped) == 1 and stripped in _SPINNER_CHARS:
        return None
    if stripped and _PROGRESS_RE.match(line):
        return None
    return line.rstrip(" ")


def _decode_bytes(data: bytes) -> str:
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8):].decode("utf-8", errors="replace")
    if data.startswith(codecs.BOM_UTF16_LE) or _looks_utf16le(data):
        body = data[2:] if data.startswith(codecs.BOM_UTF16_LE) else data
        return body.decode("utf-16-le", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for encoding in _fallback_encodings():
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _looks_utf16le(data: bytes) -> bool:
    """True for BOM-less UTF-16LE text, which some Windows tools write to pipes."""
    sample = data[:200]
    if len(sample) < 4 or len(sample) % 2:
        return False
    odd = sample[1::2]
    return odd.count(0) >= len(odd) * 0.9 and sample[0::2].count(0) == 0


@functools.lru_cache(maxsize=1)
def _fallback_encodings() -> Tuple[str, ...]:
    """Encodings to try after UTF-8, most likely first."""
    names: List[str] = []
    if _WINDOWS:
        from aiup.platform.term import original_output_codepage

        for codepage in (original_output_codepage(), _win_codepage("GetOEMCP"), _win_codepage("GetACP")):
            if codepage and codepage != 65001:
                names.append("cp%d" % codepage)
    else:
        try:
            names.append(locale.getpreferredencoding(False))
        except (ValueError, LookupError):
            pass
    usable: List[str] = []
    for name in names:
        try:
            canonical = codecs.lookup(name).name
        except LookupError:
            continue
        if canonical != "utf-8" and canonical not in usable:
            usable.append(canonical)
    return tuple(usable)


def _win_codepage(function: str) -> int:
    try:
        import ctypes

        return int(getattr(ctypes.windll.kernel32, function)())  # type: ignore[attr-defined]
    except (ImportError, OSError, AttributeError, ValueError):
        return 0
