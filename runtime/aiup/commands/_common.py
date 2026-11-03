"""Small helpers the command modules share (not a command itself).

Card output follows macOS ``ui_cards``; colors follow macOS ``ink`` (256-color
codes, only on a terminal and never with NO_COLOR or --plain).
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence, TextIO, Tuple

from aiup.errors import AiupError
from aiup.platform import term

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.cli import Args
    from aiup.engine.channels import Copy
    from aiup.engine.context import Context
    from aiup.model import CatalogEntry

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")

CARD_TITLES = {"attention": "needs attention", "owners": "installation ownership",
               "duplicates": "duplicate review"}


# ----- context ---------------------------------------------------------------------


def need(args: "Args", ctx: Optional["Context"]) -> Tuple["Context", "Catalog"]:
    """The context and catalog, or a clear error when the CLI did not provide them."""
    if ctx is None or args.catalog is None:
        raise AiupError("aiup {} needs the catalog and this computer's context".format(args.command))
    return ctx, args.catalog


def stdout() -> TextIO:
    """sys.stdout, set to replace characters the console cannot show."""
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError, OSError):
        pass
    return sys.stdout


def trash_name(os_name: str) -> str:
    """What this system calls the place removed files go."""
    return "Recycle Bin" if os_name == "windows" else "Trash"


# ----- text and color ------------------------------------------------------------------


def clean(text: object) -> str:
    """Drop escape sequences and control characters from text read from disk or tools."""
    return _CONTROL.sub("", _ANSI.sub("", str(text)))


def color_on(stream: Optional[TextIO] = None) -> bool:
    """macOS: ``[ -t 1 ] && [ -z "$NO_COLOR" ]``."""
    return term.color_enabled(sys.stdout if stream is None else stream)


def ink(text: str, code: str, stream: Optional[TextIO] = None) -> str:
    """Color ``text`` with a 256-color number ("141") or a full SGR code ("38;5;141")."""
    if not color_on(stream):
        return text
    sgr = code if ";" in code else "38;5;" + code
    return "\033[" + sgr + "m" + text + "\033[0m"


def plural(count: int, word: str, many: str = "") -> str:
    """"1 tool", "3 tools"; ``many`` names an irregular plural."""
    if count == 1:
        return "1 " + word
    return str(count) + " " + (many or word + "s")


def cards(title: str, items: Sequence[Tuple[str, str]], out: Optional[TextIO] = None) -> None:
    """Titled cards, wrapped to the terminal (macOS ``ui_cards``)."""
    stream = out or stdout()
    width = max(32, min(term.columns(88), 110))
    color = color_on(stream)
    rule = "─" if term.use_unicode(stream) else "-"

    def paint(text: str, code: str) -> str:
        return "\033[38;5;" + code + "m" + text + "\033[0m" if color else text

    lines = ["", paint("  aiup · " + CARD_TITLES.get(title, title), "141"), paint("  " + rule * (width - 4), "60")]
    for head, body in items:
        for part in textwrap.wrap(clean(head), width - 4):
            lines.append("  " + paint(part, "81"))
        for part in textwrap.wrap(clean(body), width - 6):
            lines.append("    " + part)
        lines.append("")
    stream.write("\n".join(lines) + "\n")
    stream.flush()


# ----- questions --------------------------------------------------------------------------


def ask(prompt: str) -> bool:
    """A [y/N] question on stderr; only y or yes is yes. Ctrl-C propagates."""
    try:
        sys.stderr.write(prompt)
        sys.stderr.flush()
        line = sys.stdin.readline()
    except (OSError, ValueError):
        return False
    return line.strip().lower() in ("y", "yes")


# ----- this computer ------------------------------------------------------------------------


def installed_copies(ctx: "Context", catalog: "Catalog") -> "Dict[str, Tuple[Copy, ...]]":
    """Catalog id -> installed copies, for every tool offered here that has one.

    Reads in parallel (``check_workers``), in catalog order. Never changes anything.
    """
    from aiup.engine.channels import find_copies

    entries = list(catalog.available_on(ctx.os_name))
    if not entries:
        return {}

    def one(entry: "CatalogEntry") -> "Tuple[Copy, ...]":
        try:
            return find_copies(entry, ctx)
        except (OSError, ValueError, NotImplementedError, AiupError):
            return ()

    workers = max(1, min(len(entries), ctx.config.check_workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        found = list(pool.map(one, entries))
    return {entry.id: copies for entry, copies in zip(entries, found) if copies}


def detect_sources() -> Optional[ModuleType]:
    """``aiup.detect.sources`` when it is part of this runtime, else None."""
    try:
        from aiup.detect import sources  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        if exc.name in ("aiup.detect", "aiup.detect.sources"):
            return None
        raise
    return sources


def detected_items(ctx: "Context", cheap_only: bool = False) -> List[object]:
    """Every InventoryItem the detection sources report (empty without aiup.detect)."""
    module = detect_sources()
    if module is None:
        return []
    found: List[object] = []
    for source in list(module.all_sources()):
        if cheap_only and getattr(source, "cost", "cheap") != "cheap":
            continue
        try:
            if hasattr(source, "available") and not source.available(ctx):
                continue
            found.extend(list(source.scan(ctx) or ()))
        except (OSError, ValueError, NotImplementedError, AiupError):
            continue
    return found


def owner_text(owner: object, fallback: str = "") -> str:
    """An InventoryItem owner (an Ownership, a string or None) as one short phrase.

    An owner that prints as a readable name (detect's ``Owner`` with a
    ``label``, such as "Programs and Features") shows that name; a bare
    Ownership shows "manager (package)".
    """
    if owner is None or owner == "":
        return fallback or "unknown"
    manager = getattr(owner, "manager", None)
    if manager is None:
        return clean(owner)
    if type(owner).__str__ is not object.__str__:
        label = clean(str(owner)).strip()
        if label and label != manager:
            return label
    package = clean(getattr(owner, "package", "") or "")
    return clean(manager) + (" (" + package + ")" if package else "")


def path_copies(ctx: "Context", command: str, extra: Sequence[str] = ()) -> List[Tuple[str, str]]:
    """Every executable named ``command`` on PATH (then ``extra`` folders), one per real file.

    Returns (path as found, resolved target), PATH order first. Honors PATHEXT
    on Windows through ``Platform.which_all``.
    """
    search = ctx.env.get("PATH", "")
    if extra:
        search = os.pathsep.join([search] + [d for d in extra if d])
    out: List[Tuple[str, str]] = []
    seen = set()
    try:
        found = ctx.platform.which_all(command, search)
    except (OSError, ValueError):
        found = []
    for path in found:
        try:
            target = str(Path(path).resolve())
        except (OSError, RuntimeError):
            target = str(path)
        key = os.path.normcase(target)
        if key in seen:
            continue
        seen.add(key)
        out.append((str(path), target))
    return out


def broken_links(ctx: "Context", command: str, extra: Sequence[str] = ()) -> List[str]:
    """Symbolic links named ``command`` on PATH whose target is gone."""
    out: List[str] = []
    seen = set()
    for folder in ctx.env.get("PATH", "").split(os.pathsep) + list(extra):
        if not folder:
            continue
        candidate = Path(folder) / command
        if str(candidate) in seen:
            continue
        seen.add(str(candidate))
        try:
            if candidate.is_symlink() and not candidate.exists():
                out.append(str(candidate))
        except OSError:
            continue
    return out


def read_version(ctx: "Context", argv: Sequence[str]) -> str:
    """First line of ``argv`` output (``node --version``), or ""."""
    try:
        result = ctx.run_read(list(argv), timeout=5.0, max_bytes=64 * 1024)
    except (OSError, ValueError):
        return ""
    text = getattr(result, "stdout", "") or ""
    if not text and getattr(result, "returncode", 1) == 0:
        text = getattr(result, "stderr", "") or ""
    if getattr(result, "returncode", 1) != 0:
        return ""
    first = text.strip().splitlines()
    return clean(first[0]).strip() if first else ""


# ----- paging --------------------------------------------------------------------------------


def _pager_argv(ctx: "Context") -> List[str]:
    """``$PAGER`` or ``less``, when one can run; [] means print directly."""
    raw = ctx.env.get("PAGER", "").strip()
    try:
        argv = shlex.split(raw, posix=ctx.os_name != "windows") if raw else ["less"]
    except ValueError:
        argv = []
    if not argv:
        return []
    program = ctx.platform.which(argv[0]) or shutil.which(argv[0])
    if not program:
        return []
    return [program] + argv[1:]


def paged(ctx: "Context", write: Callable[[], int]) -> int:
    """Run ``write`` (which prints to sys.stdout) through a pager on a terminal.

    macOS: ``LESS="${LESS:-FRX}" ${PAGER:-less}`` when stdout is a terminal
    and AIUP_NO_PAGER is not set. Without a pager it prints directly.
    """
    if ctx.config.no_pager or not term.is_tty(sys.stdout):
        return write()
    argv = _pager_argv(ctx)
    if not argv:
        return write()
    env = dict(os.environ)
    env.setdefault("LESS", "FRX")
    sys.stdout.flush()
    try:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, env=env, encoding="utf-8", errors="replace")
    except OSError:
        return write()
    saved = sys.stdout
    pipe = process.stdin
    if pipe is None:
        process.wait()
        return write()
    sys.stdout = pipe
    code = 0
    try:
        try:
            code = write()
        except BrokenPipeError:
            pass
    finally:
        sys.stdout = saved
        try:
            pipe.close()
        except (BrokenPipeError, OSError):
            pass
        while True:
            try:
                process.wait()
                break
            except KeyboardInterrupt:
                continue
    return code
