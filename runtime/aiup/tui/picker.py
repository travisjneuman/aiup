"""Builds and runs fzf for the picker (macOS: pick_catalog_tools,
ensure_fzf_for_interactive, catalog_fzf_style and tui_prefetch_*).

fzf needs 0.73.0 or newer. That is the release that exports
``FZF_CURRENT_ITEM`` to child processes, which lets every binding run a
fixed command with no ``{q}`` or ``{1}`` placeholder: the query and the
current row reach the fast helper through the environment, so typed text is
never put through a shell (``cmd.exe`` on Windows, ``sh`` on Linux). The other
features the picker needs are older: ``--id-nth`` (0.71), ``--with-shell``
and ``FZF_POS`` (0.51), ``FZF_QUERY`` (0.46), ``transform`` (0.45),
``--listen-unsafe`` (0.44), ``FZF_API_KEY`` (0.43), ``transform-header``
(0.40), ``--track`` and ``FZF_PORT`` (0.39).
"""

from __future__ import annotations

import http.client
import os
import re
import secrets
import shlex
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from aiup.errors import AiupError
from aiup.tui import fast
from aiup.tui.rows import Style, UpdateRecord
from aiup.tui.session import InstalledTool, LiveSession

if TYPE_CHECKING:
    from aiup.engine.context import Context
    from aiup.model import Target
    from aiup.platform.base import Platform

FZF_MINIMUM: Tuple[int, int, int] = (0, 73, 0)
FZF_MINIMUM_TEXT = "0.73.0"

PREVIEW_WINDOW = "down,33%,wrap,<7(hidden)"
COLORS = (
    "fg:252,fg+:255,bg+:236,hl:220,hl+:220,info:244,prompt:213,pointer:213,marker:82,spinner:213",
    "header:245,border:238,label:213,query:255,gutter:-1,separator:238,scrollbar:240,preview-border:238",
)
FZF_BORDERS = ("rounded", "sharp", "bold", "double", "block", "thinblock", "horizontal", "none")

PORT_WAIT = 10.0          # seconds to wait for fzf's listen port
PREFETCH_DELAY = 0.35     # let the first screen draw before reading versions
PREFETCH_DEADLINE = 90.0  # stop asking providers after this long
PUBLISH_EVERY = 2.0       # at most one list refresh this often while checking

_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


class PickerUnavailable(AiupError):
    """The picker cannot start here. The caller prints the plain list instead."""


# ----- fzf -------------------------------------------------------------------------


@dataclass(frozen=True)
class Fzf:
    """The fzf binary the picker uses."""

    path: str
    version: Tuple[int, int, int]


def parse_fzf_version(text: str) -> Optional[Tuple[int, int, int]]:
    """``(major, minor, patch)`` from ``fzf --version`` output, or None."""
    found = _VERSION.search(text or "")
    if found is None:
        return None
    return (int(found.group(1)), int(found.group(2)), int(found.group(3) or 0))


def version_text(version: Tuple[int, int, int]) -> str:
    """``0.73.0`` style text."""
    return ".".join(str(part) for part in version)


def find_fzf(platform: "Platform", install_hint: str) -> Fzf:
    """The fzf on PATH, checked against FZF_MINIMUM.

    ``install_hint`` names the command that gets a newer fzf here (for
    example "aiup only fzf"). Raises PickerUnavailable.
    """
    path = platform.which("fzf")
    if not path:
        raise PickerUnavailable("the picker needs fzf {} or newer. Install it with: {}".format(
            FZF_MINIMUM_TEXT, install_hint))
    try:
        done = subprocess.run([path, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=5, check=False)
        output = done.stdout[:4096].decode("utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        output = ""
    version = parse_fzf_version(output)
    if version is None:
        raise PickerUnavailable("could not read the fzf version from {}".format(path))
    if version < FZF_MINIMUM:
        raise PickerUnavailable("the picker needs fzf {} or newer; {} is {}. Get a newer one with: {}".format(
            FZF_MINIMUM_TEXT, path, version_text(version), install_hint))
    return Fzf(path, version)


# ----- binding commands ------------------------------------------------------------


@dataclass(frozen=True)
class Launch:
    """How fzf starts the fast helper."""

    python: str
    helper: str
    windows: bool
    pycache: str = ""   # <cache>/pycache, or "" to leave bytecode alone

    def command(self, verb: str) -> str:
        """The command line for one helper verb.

        Windows: fzf runs it with ``cmd /s/c`` (the man page; some builds
        add ``/v:on``), so every path is put in double quotes (``_check_path``
        refuses ``%``, ``!``, ``^`` and quotes, which cmd would still change). Linux: fzf runs it with
        ``sh -c`` (``--with-shell``), so every word is shell-quoted. ``-I``
        ignores ``PYTHONPYCACHEPREFIX``, so the bytecode folder is passed as
        ``-X pycache_prefix``.
        """
        if self.windows:
            prefix = ' -X "pycache_prefix={}"'.format(self.pycache) if self.pycache else ""
            return '"{}" -I -S -B{} "{}" {}'.format(self.python, prefix, self.helper, verb)
        words = [self.python, "-I", "-S", "-B"]
        if self.pycache:
            words += ["-X", "pycache_prefix=" + self.pycache]
        return " ".join(shlex.quote(word) for word in words + [self.helper, verb])

    def action(self, name: str, verb: str) -> str:
        """``name(command)`` with a delimiter the command does not contain."""
        return fast.fzf_action(name, self.command(verb))


def _check_path(path: str, windows: bool) -> None:
    """Refuse a path fzf or cmd.exe would change before running it."""
    if not path:
        raise PickerUnavailable("could not find the Python interpreter that runs aiup")
    if "{" in path or "}" in path:
        raise PickerUnavailable("the picker cannot run from a path with braces: " + path)
    if any(ord(ch) < 32 for ch in path):
        raise PickerUnavailable("the picker cannot run from a path with control characters")
    if windows and any(ch in path for ch in '%!^"'):
        raise PickerUnavailable("the picker cannot run from a path with %, !, ^ or quotes: " + path)


def make_launch(os_name: str) -> Launch:
    """The Launch for this Python and this copy of fast.py."""
    windows = os_name == "windows"
    python = sys.executable or ""
    helper = str(Path(fast.__file__).resolve())
    _check_path(python, windows)
    _check_path(helper, windows)
    # The launcher points sys.pycache_prefix at <cache>/pycache before aiup starts.
    pycache = str(getattr(sys, "pycache_prefix", None) or "")
    try:
        _check_path(pycache, windows)
    except PickerUnavailable:
        pycache = ""   # no prefix, or one fzf or cmd.exe would change: run without it
    return Launch(python, helper, windows, pycache)


def session_actions(launch: Launch) -> Dict[str, str]:
    """Command strings stored in meta.json for the helper to print back."""
    return {"rows_command": launch.command("rows")}


def bindings(launch: Launch, palette: bool) -> List[str]:
    """Every ``--bind`` value (macOS pick_catalog_tools key table)."""
    a = launch.action
    docs = a("transform", "docs") + "+refresh-preview"
    jump = a("transform", "jump") if palette else a("reload", "collapse-all")
    return [
        "space:toggle",
        "ctrl-a:toggle-all",
        "ctrl-/:toggle-preview",
        "?:show-preview+" + a("preview", "keys"),
        "resize:" + a("transform-header", "header") + "+refresh-preview",
        "change:" + a("reload", "rows"),
        "load:" + a("transform-header", "header"),
        "enter:" + a("transform", "enter"),
        "left:" + a("reload", "collapse"),
        "right:" + a("reload", "expand"),
        "pgup:" + a("transform", "nav-prev"),
        "pgdn:" + a("transform", "nav-next"),
        "ctrl-g:" + jump,
        "ctrl-e:" + a("reload", "toggle"),
        "alt-e:" + a("reload", "expand-all"),
        "alt-c:" + a("reload", "collapse-all"),
        "ctrl-o:" + docs,
        "f3:" + docs,
        "alt-o:" + docs,
        "ctrl-y:" + a("transform", "copy"),
    ]


# ----- look ------------------------------------------------------------------------


def style_options(style: Style) -> List[str]:
    """aiup's fzf look (macOS catalog_fzf_style), as separate options.

    Without color fzf draws black and white (NO_COLOR). With the ASCII glyph
    set fzf's own lines and spinner are ASCII too (``--no-unicode``).
    """
    g = style.glyphs
    ascii_only = g.pointer.isascii()
    border = g.border if g.border in FZF_BORDERS else "rounded"
    options = [
        "--border=" + border, "--border-label= aiup ", "--border-label-pos=3",
        "--info=inline-right", "--highlight-line",
        "--pointer=" + g.pointer, "--marker=" + g.marker, "--scrollbar=" + g.scrollbar,
    ]
    if ascii_only:
        options += ["--no-unicode", "--ellipsis=.."]
    if style.color:
        options += ["--color=" + COLORS[0], "--color=" + COLORS[1]]
    else:
        options.append("--color=bw")
    return options


def default_opts(style: Style, user_opts: str) -> str:
    """FZF_DEFAULT_OPTS: aiup's look, then the person's own options, then
    ``--no-height`` so the picker always takes the whole screen.

    The person's options come after aiup's, so their colors and borders win.
    """
    ours = " ".join(shlex.quote(option) for option in style_options(style))
    return " ".join(part for part in (ours, user_opts.strip(), "--no-height") if part)


def fzf_argv(fzf: Fzf, launch: Launch, style: Style, header: str, query: str = "",
             position: int = 0, palette: bool = True, mode: str = "") -> List[str]:
    """The fzf command line."""
    prompt = "aiup " + ((mode + " ") if mode else "") + style.glyphs.prompt + " "
    argv = [
        fzf.path, "--ansi", "--disabled", "--no-sort", "--multi", "--delimiter=\t", "--with-nth=2",
        "--track", "--id-nth=1", "--listen-unsafe=127.0.0.1:0", "--no-hscroll", "--print-query",
        "--expect=ctrl-d,ctrl-r", "--prompt", prompt, "--header", header,
        "--preview", launch.command("preview"), "--preview-window", PREVIEW_WINDOW,
    ]
    if not launch.windows:
        argv += ["--with-shell", "sh -c"]
    for value in bindings(launch, palette):
        argv += ["--bind", value]
    if query:
        argv += ["--query", query]
    if position > 0:
        argv += ["--bind", "start:pos({})".format(position)]
    return argv


def fzf_env(base: Mapping[str, str], live: LiveSession, style: Style, api_key: str,
            windows: bool, timings: bool = False) -> Dict[str, str]:
    """fzf's environment: the session, the listen key and the look."""
    env = dict(base)
    env.update(live.env())
    env["FZF_API_KEY"] = api_key
    env["FZF_DEFAULT_OPTS"] = default_opts(style, base.get("FZF_DEFAULT_OPTS", ""))
    env.pop("FZF_DEFAULT_COMMAND", None)
    if windows:
        # Without SHELL, fzf runs binding commands with cmd.exe.
        env.pop("SHELL", None)
    if timings:
        env["AIUP_TUI_TIMINGS"] = "1"
    else:
        env.pop("AIUP_TUI_TIMINGS", None)
    return env


# ----- result ----------------------------------------------------------------------


@dataclass
class PickResult:
    """What the person chose."""

    action: str                       # "apply" | "update" | "remove" | "cancel" | "none"
    ids: Tuple[str, ...] = ()
    query: str = ""
    selected: str = ""                # the first chosen row, as it was in the list


def _row_id(line: str) -> str:
    return line.split("\t", 1)[0].strip()


def resolve_ids(raw: Sequence[str], eligible_updates: Sequence[str],
                action: str = "apply") -> Tuple[str, ...]:
    """Tool ids to act on (macOS tui_resolve_update_selection).

    ``__updates:all`` stands for every eligible verified update and
    ``__update:<id>`` for its tool. Headers and status rows are dropped.
    Detected items (``det:``) are kept only for ``remove``: ``aiup remove``
    plans them with the remover detection verified, and ``aiup only`` refuses
    them.
    """
    out: List[str] = []
    seen: Set[str] = set()

    def add(tool: str) -> None:
        if tool and tool not in seen:
            seen.add(tool)
            out.append(tool)

    for row_id in raw:
        if row_id == "__updates:all":
            for tool in eligible_updates:
                add(tool)
        elif row_id.startswith("__update:"):
            add(row_id[len("__update:"):])
        elif row_id.startswith("__") or (row_id.startswith("det:") and action != "remove"):
            continue
        else:
            add(row_id)
    return tuple(out)


def parse_output(text: str, eligible_updates: Sequence[str], mode: str = "") -> PickResult:
    """fzf's stdout: query, expect key, then the chosen rows.

    In ``remove`` mode every key that accepts removes (macOS pick_catalog_tools
    remove); elsewhere enter applies, ctrl-d removes and ctrl-r updates.
    """
    lines = text.split("\n")
    query = lines[0] if lines else ""
    key = lines[1].strip() if len(lines) > 1 else ""
    chosen = [_row_id(line) for line in lines[2:] if line.strip()]
    if mode == "remove":
        action = "remove"
    else:
        action = {"ctrl-d": "remove", "ctrl-r": "update"}.get(key, "apply")
    ids = resolve_ids(chosen, eligible_updates, action)
    return PickResult(action=action if ids else "none", ids=ids, query=query,
                      selected=chosen[0] if chosen else "")


# ----- prefetch --------------------------------------------------------------------


@dataclass
class PrefetchState:
    """Answers gathered so far, keyed by tool id."""

    records: Dict[str, UpdateRecord] = field(default_factory=dict)
    available: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def eligible(self) -> List[str]:
        """Tools with a newer version that a batch may update.

        A pending update (the manager says one waits, version unknown) counts,
        as it does for ``aiup check``; a managed copy never does.
        """
        with self.lock:
            return [r.id for r in self.records.values() if r.status == "newer" and r.eligible]


class Prefetch:
    """Reads available versions after the picker opens (macOS tui_prefetch_*).

    Bulk ``outdated()`` reads run first, once per provider, then one
    ``latest()`` per installed tool with 2 or 3 workers. Results go to the
    session as one Updates section, at most every two seconds, and fzf is
    told to reload through its listen port.
    """

    def __init__(self, ctx: "Context", live: LiveSession, jobs: Sequence[Tuple[InstalledTool, "Target"]],
                 api_key: str, reload_action: str, workers: int) -> None:
        self.ctx = ctx
        self.live = live
        self.jobs = list(jobs)
        self.api_key = api_key
        self.reload_action = reload_action
        self.workers = max(1, min(3, workers))
        self.state = PrefetchState()
        self.stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="aiup-prefetch", daemon=True)
        self._published = 0.0

    def start(self) -> None:
        """Start in the background."""
        self._thread.start()

    def stop(self) -> None:
        """Ask the thread to finish; provider reads already running end on their timeout."""
        self.stop_event.set()

    def _run(self) -> None:
        try:
            self._work()
        except Exception as exc:  # noqa: BLE001 (a prefetch failure must never break the picker)
            self.ctx.log.write("tui prefetch stopped: {}".format(exc))

    def _work(self) -> None:
        port = self._wait_for_port()
        if port is None or self.stop_event.wait(PREFETCH_DELAY):
            return
        deadline = time.monotonic() + PREFETCH_DEADLINE
        self._bulk()
        pending: Set[Future] = set()
        pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="aiup-latest")
        try:
            for tool, target in self.jobs:
                pending.add(pool.submit(self._one, tool, target))
            while pending and not self.stop_event.is_set() and time.monotonic() < deadline:
                done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
                if done and time.monotonic() - self._published >= PUBLISH_EVERY:
                    self._publish(port, checking=bool(pending))
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        if not self.stop_event.is_set():
            self._mark_unfinished()
            self._publish(port, checking=False)

    def _mark_unfinished(self) -> None:
        """Tools still unanswered at the deadline stay listed as needing a check."""
        with self.state.lock:
            for tool, _target in self.jobs:
                if tool.id not in self.state.records:
                    self.state.records[tool.id] = UpdateRecord(
                        tool.id, tool.version, "", "checking", tool.eligible, tool.label, tool.lifecycle)

    def _wait_for_port(self) -> Optional[int]:
        end = time.monotonic() + PORT_WAIT
        while time.monotonic() < end:
            port = self.live.port()
            if port is not None:
                return port
            if self.stop_event.wait(0.05):
                return None
        return None

    def _bulk(self) -> None:
        from aiup.engine.latest import prefetch_outdated

        providers = []
        seen: Set[str] = set()
        for _tool, target in self.jobs:
            if target.channel in seen:
                continue
            seen.add(target.channel)
            provider = self.ctx.provider(target.channel)
            if provider is not None:
                providers.append(provider)
        try:
            prefetch_outdated(self.ctx, providers)
        except (OSError, ValueError, NotImplementedError):
            pass

    def _one(self, tool: InstalledTool, target: "Target") -> None:
        if self.stop_event.is_set():
            return
        from aiup.engine.latest import classify, read_latest

        provider = self.ctx.provider(target.channel)
        if provider is None:
            return
        latest = read_latest(self.ctx, provider, target, tool.id, tool.version)
        verdict = classify(tool.version, latest)
        if verdict == "update":
            # latest.version is "" when the manager says an update waits but names
            # no version (Latest.pending); rows and previews show "unknown".
            record = UpdateRecord(tool.id, tool.version, latest.version, "newer", tool.eligible,
                                  tool.label, tool.lifecycle)
            answer = ("newer", latest.version)
        elif verdict == "skipped":
            # Another updater owns this copy (Latest.managed): not an update, not a failure.
            record = UpdateRecord(tool.id, tool.version, "", "managed", tool.eligible,
                                  tool.label, tool.lifecycle, latest.managed)
            answer = ("managed", latest.managed)
        elif verdict in ("current", "self-updated"):
            record = UpdateRecord(tool.id, tool.version, latest.version, "current", tool.eligible,
                                  tool.label, tool.lifecycle)
            answer = ("current", "")
        else:
            # A channel that cannot read versions at all is not a failure worth a row.
            quiet = latest.unverified_reason.endswith("cannot read versions yet") or not tool.version
            record = UpdateRecord(tool.id, tool.version, "", "current" if quiet else "unavailable",
                                  tool.eligible, tool.label, tool.lifecycle)
            answer = ("failure", "")
        with self.state.lock:
            self.state.records[tool.id] = record
            self.state.available[tool.id] = answer

    def _publish(self, port: int, checking: bool) -> None:
        if self.stop_event.is_set():
            return
        with self.state.lock:
            records = sorted(self.state.records.values(), key=lambda r: r.id)
            available = dict(self.state.available)
        try:
            self.live.publish_updates(records, checking, available)
        except (OSError, AiupError):
            return
        self._published = time.monotonic()
        post_action(port, self.api_key, self.reload_action)


def post_action(port: int, api_key: str, action: str) -> bool:
    """Send one action to fzf's listen server on this computer."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("POST", "/", body=action.encode("utf-8"),
                           headers={"x-api-key": api_key, "Content-Type": "text/plain"})
        response = connection.getresponse()
        response.read(4096)
        return 200 <= response.status < 300
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


# ----- running fzf ----------------------------------------------------------------


@dataclass
class PickerRun:
    """Everything one picker window needs besides the session."""

    fzf: Fzf
    launch: Launch
    style: Style
    query: str = ""
    selected: str = ""                # row id to put the cursor on
    palette: bool = True
    timings: bool = False
    mode: str = ""
    jobs: Sequence[Tuple[InstalledTool, "Target"]] = ()


def _initial_rows(live: LiveSession, query: str) -> Tuple[str, bool]:
    """The first list (same code as every reload) and whether nothing matched."""
    session = fast.open_session(str(live.root), live.token)
    body = fast.emit(session, query)
    return body, bool(query.strip()) and not body.strip()


def _position(body: str, row_id: str) -> int:
    if not row_id:
        return 0
    for index, line in enumerate(body.split("\n")):
        if line.split("\t", 1)[0] == row_id:
            return index + 1
    return 0


def run_picker(ctx: "Context", live: LiveSession, run: PickerRun, columns: int) -> PickResult:
    """Show the picker until the person picks rows or closes it."""
    if not run.jobs:
        # session.create wrote the Updates section as "checking". With nothing
        # to check it would say so until the window closed, so it is marked
        # finished before the first list is drawn.
        try:
            live.publish_updates((), False, {})
        except (OSError, AiupError):
            pass
    body, no_matches = _initial_rows(live, run.query)
    header = fast.header_line(columns, run.palette, no_matches, run.style.glyphs.dot)
    argv = fzf_argv(run.fzf, run.launch, run.style, header, run.query,
                    _position(body, run.selected), run.palette, run.mode)
    api_key = secrets.token_urlsafe(32)
    env = fzf_env(os.environ, live, run.style, api_key, run.launch.windows, run.timings)
    reload_action = run.launch.action("reload", "rows") + "+refresh-preview"
    prefetch = Prefetch(ctx, live, run.jobs, api_key, reload_action, ctx.config.tui_prefetch_workers)
    if run.jobs:
        prefetch.start()
    try:
        out, status = _run_fzf(argv, env, body.encode("utf-8"))
    finally:
        prefetch.stop()
    text = out.decode("utf-8", errors="replace").replace("\r\n", "\n")
    if status in (1, 130):
        return PickResult(action="cancel", query=text.split("\n", 1)[0])
    if status != 0:
        raise AiupError("fzf stopped with status {}".format(status))
    return parse_output(text, prefetch.state.eligible(), run.mode)


def _run_fzf(argv: Sequence[str], env: Mapping[str, str], body: bytes) -> Tuple[bytes, int]:
    """Run fzf with ``body`` on stdin; return its stdout and exit status.

    fzf reads Ctrl-C as a key in raw mode. If an interrupt still reaches
    aiup, it waits for fzf to exit and reports a cancel (130).
    """
    try:
        process = subprocess.Popen(list(argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=dict(env))
    except OSError as exc:
        raise PickerUnavailable("could not start fzf: {}".format(exc.strerror or exc)) from exc
    try:
        out, _ = process.communicate(body)
        return out or b"", process.returncode
    except KeyboardInterrupt:
        while True:
            try:
                process.wait()
                break
            except KeyboardInterrupt:
                continue
        return b"", 130
