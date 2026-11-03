"""Fast helper for fzf bindings (macOS: the fast-helper.py tui_fast_helper_render writes).

fzf runs this file for every keystroke, cursor move and key binding, as::

    "<python>" -I -S -B -X pycache_prefix="<cache>/pycache" "<runtime>/aiup/tui/fast.py" <verb>

It imports nothing outside the standard library, so each call costs one
small Python start. Binding commands carry no fzf placeholders: the query and
the current row come from ``FZF_QUERY`` and ``FZF_CURRENT_ITEM`` (fzf 0.73.0
and newer), so nothing typed into the search box ever passes through a shell.

The session folder (``AIUP_TUI_SESSION``) was written by ``aiup.tui.session``.
Each call checks the session token (``AIUP_TUI_TOKEN``) and the SHA-256
stamps of the files it reads, then answers from those files only.

Verbs:

- ``rows``: the list for the current query (fzf ``reload``).
- ``toggle`` / ``expand`` / ``collapse``: change the current row's category, then ``rows``.
- ``expand-all`` / ``collapse-all``: change every category, then ``rows``.
- ``enter``: an fzf action for enter (``transform``).
- ``nav-prev`` / ``nav-next``: ``pos(N)`` of the previous or next category header.
- ``jump``: a small category chooser, then ``pos(N)``.
- ``preview`` / ``keys`` / ``header``: preview window and header text.
- ``docs`` / ``copy``: open or copy the current row's URL, then a header message.

The picker imports this module too (``aiup.tui.fast``) for :func:`emit` and
:func:`fzf_action`, so the first list and every later one come from the same
code.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

MARKER = "aiup-tui-session-v1"
SCHEMA = 1
AVAILABLE_SLOT = "\x00available"
ENDED = "This aiup window's session ended or changed · press esc, then run aiup list again"
ENDED_ID = "__session:ended"
MAX_JSON = 16 * 1024 * 1024

ENV_SESSION = "AIUP_TUI_SESSION"
ENV_TOKEN = "AIUP_TUI_TOKEN"

# fzf accepts these instead of (...) around an action argument. "{}" is left
# out because fzf would read it as a placeholder; "$" and "%" because cmd.exe
# could expand them.
_DELIMITERS: Tuple[Tuple[str, str], ...] = (
    ("(", ")"), ("[", "]"), ("<", ">"), ("~", "~"), ("@", "@"), ("#", "#"),
    ("^", "^"), ("*", "*"), ("!", "!"), ("&", "&"), (";", ";"), ("/", "/"), ("|", "|"),
)

_ANSI = re.compile(r"\x1b\[[0-9;:?]*[ -/]*[@-~]")


class SessionError(Exception):
    """The session folder is missing, foreign or changed."""


# ----- small file helpers ---------------------------------------------------


def fzf_action(name: str, argument: str) -> str:
    """``name(argument)`` with a delimiter pair that does not occur in ``argument``."""
    for opening, closing in _DELIMITERS:
        if closing not in argument and opening not in argument:
            return name + opening + argument + closing
    raise ValueError("no fzf delimiter fits this argument")


def write_atomic(path: Path, text: str) -> None:
    """Write ``text`` through a temp file and ``os.replace``.

    Windows refuses a replace while another process has the target open,
    which happens when fzf runs a preview and a reload at once, so the
    replace is retried for up to half a second.
    """
    fd, temp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".next", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        for attempt in range(50):
            try:
                os.replace(temp, str(path))
                return
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.01)
    finally:
        if os.path.exists(temp):
            try:
                os.unlink(temp)
            except OSError:
                pass


def read_text(path: Path, default: str = "") -> str:
    """A small session file's text, or ``default`` when it cannot be read."""
    for attempt in range(3):
        try:
            if path.is_symlink():
                return default
            with open(str(path), "r", encoding="utf-8", newline="") as handle:
                return handle.read(MAX_JSON)
        except FileNotFoundError:
            return default
        except PermissionError:
            time.sleep(0.01 * (attempt + 1))
        except (OSError, UnicodeError):
            return default
    return default


def read_json(path: Path) -> object:
    """A session JSON file, or None."""
    text = read_text(path)
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def sha256_file(path: Path) -> str:
    """SHA-256 of a file's bytes, or "" when it cannot be read."""
    try:
        with open(str(path), "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return ""


# ----- session ---------------------------------------------------------------


class Session:
    """A validated session folder and its files."""

    def __init__(self, root: Path, meta: Mapping[str, object]) -> None:
        self.root = root
        self.meta = meta
        self._rows: Optional[List[Dict[str, object]]] = None
        self._updates: Optional[Dict[str, object]] = None

    # stamped files ------------------------------------------------------

    def stamped_json(self, name: str) -> object:
        """A stamped file, refused when its SHA-256 differs from meta.json."""
        stamps = self.meta.get("stamps")
        expected = stamps.get(name) if isinstance(stamps, dict) else None
        path = self.root / name
        if not isinstance(expected, str) or not hmac.compare_digest(sha256_file(path), expected):
            raise SessionError(name)
        data = read_json(path)
        if data is None:
            raise SessionError(name)
        return data

    def base_rows(self) -> List[Dict[str, object]]:
        """Catalog, packages and detected rows, in display order."""
        if self._rows is None:
            data = self.stamped_json("rows.json")
            rows = data.get("rows") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise SessionError("rows.json")
            self._rows = [r for r in rows if isinstance(r, dict) and isinstance(r.get("id"), str)]
        return self._rows

    def updates(self) -> Dict[str, object]:
        """The Updates section the prefetch keeps current (unstamped, replaced whole)."""
        if self._updates is None:
            data = read_json(self.root / "updates.json")
            self._updates = data if isinstance(data, dict) else {}
        return self._updates

    def all_rows(self) -> List[Dict[str, object]]:
        """Updates rows first (when shown), then the base rows."""
        rows: List[Dict[str, object]] = []
        if self.meta.get("updates"):
            extra = self.updates().get("rows")
            if isinstance(extra, list):
                rows.extend(r for r in extra if isinstance(r, dict) and isinstance(r.get("id"), str))
        rows.extend(self.base_rows())
        return rows

    # mutable state ------------------------------------------------------

    def expanded(self) -> Set[str]:
        """Categories the person opened."""
        return {line.strip() for line in read_text(self.root / "expanded").splitlines() if line.strip()}

    def save_expanded(self, values: Iterable[str]) -> None:
        """Store the open categories."""
        write_atomic(self.root / "expanded", "".join(v + "\n" for v in sorted(set(values))))

    def opened(self) -> Set[str]:
        """Open categories plus the ones a --category filter keeps open."""
        forced = self.meta.get("forced_open")
        extra = {str(c) for c in forced} if isinstance(forced, list) else set()
        return self.expanded() | extra

    def categories(self) -> Dict[str, List[str]]:
        """Category id -> [name, blurb, emoji]."""
        data = self.meta.get("categories")
        return data if isinstance(data, dict) else {}

    def text(self, key: str, default: str = "") -> str:
        """A string from meta.json."""
        value = self.meta.get(key)
        return value if isinstance(value, str) else default


def open_session(root_text: Optional[str] = None, token: Optional[str] = None) -> Session:
    """The session named by the environment, after the token and marker checks."""
    root_text = os.environ.get(ENV_SESSION, "") if root_text is None else root_text
    token = os.environ.get(ENV_TOKEN, "") if token is None else token
    if not root_text or not token:
        raise SessionError("no session")
    root = Path(root_text)
    if root.is_symlink() or not root.is_dir():
        raise SessionError("folder")
    stored = read_text(root / "token").strip()
    if not stored or not hmac.compare_digest(stored, token):
        raise SessionError("token")
    meta = read_json(root / "meta.json")
    if not isinstance(meta, dict) or meta.get("marker") != MARKER or meta.get("schema") != SCHEMA:
        raise SessionError("meta")
    return Session(root, meta)


# ----- current row -------------------------------------------------------------


def current_id(session: Optional[Session] = None) -> str:
    """The id of the row under the cursor, from FZF_CURRENT_ITEM.

    The id is the text before the first tab. If fzf ever passes only the
    displayed text, the row is found again in list.tsv by that text.
    """
    item = os.environ.get("FZF_CURRENT_ITEM", "")
    if not item:
        return ""
    if "\t" in item:
        return _ANSI.sub("", item.split("\t", 1)[0]).strip()
    if session is not None:
        wanted = _ANSI.sub("", item).strip()
        for line in read_text(session.root / "list.tsv").splitlines():
            row_id, _, text = line.partition("\t")
            if _ANSI.sub("", text).strip() == wanted:
                return row_id
    return _ANSI.sub("", item).strip()


def query() -> str:
    """The current search text."""
    return os.environ.get("FZF_QUERY", "")


def category_of(session: Session, row_id: str) -> str:
    """The category a row belongs to ("" when unknown)."""
    if row_id.startswith("__cat:"):
        return row_id[len("__cat:"):]
    if row_id.startswith("__update"):
        return "updates"
    for row in session.all_rows():
        if row.get("id") == row_id:
            return str(row.get("cat", ""))
    return ""


# ----- rows --------------------------------------------------------------------


def _tree(session: Session) -> List[Tuple[str, str]]:
    """The browse list: headers, and the rows of open categories."""
    opened = session.opened()
    lines: List[Tuple[str, str]] = []
    for row in session.all_rows():
        row_id = str(row["id"])
        category = str(row.get("cat", ""))
        if row.get("kind") == "header":
            parent = str(row.get("parent", ""))
            if parent and parent not in opened:
                continue
            text = row.get("open") if category in opened else row.get("text")
            lines.append((row_id, str(text or "")))
            continue
        top = category.split("/", 1)[0]
        if category in opened and (top == category or top in opened):
            lines.append((row_id, str(row.get("text", ""))))
    return lines


def _hint(session: Session, category: str) -> str:
    """The `· Category` suffix a search hit carries (headers are hidden then)."""
    names = session.categories()
    top = category.split("/", 1)[0]
    entry = names.get(top) or [top]
    name = str(entry[0]) if entry else top
    return session.text("hint_prefix", "  · ") + name + session.text("hint_suffix", "")


def _search(session: Session, text: str) -> List[Tuple[str, str]]:
    """Every row matching all search words, best first (macOS ranking).

    Rank: exact name, alias, name prefix, name substring, other match.
    An Updates row and its tool row count once (the Updates row comes first).
    """
    q = text.casefold().strip()
    terms = q.split()
    matches: List[Tuple[int, str, int, str, str]] = []
    seen: Set[str] = set()
    for index, row in enumerate(session.all_rows()):
        haystack = row.get("search")
        if not isinstance(haystack, str) or not haystack:
            continue
        row_id = str(row["id"])
        canonical = str(row.get("canon") or row_id)
        if canonical in seen or not all(term in haystack for term in terms):
            continue
        name = str(row.get("name", ""))
        raw_aliases = row.get("aliases")
        aliases = [str(a) for a in raw_aliases] if isinstance(raw_aliases, list) else []
        if q == name:
            score = 0
        elif q in aliases:
            score = 1
        elif name.startswith(q):
            score = 2
        elif q in name:
            score = 3
        else:
            score = 4
        display = str(row.get("text", "")) + _hint(session, str(row.get("cat", "")))
        matches.append((score, name, index, row_id, display))
        seen.add(canonical)
    matches.sort(key=lambda m: (m[0], m[1], m[2]))
    return [(m[3], m[4]) for m in matches]


def emit(session: Session, text: str) -> str:
    """The rows for ``text`` as fzf input; also written to list.tsv."""
    lines = _search(session, text) if text.strip() else _tree(session)
    body = "".join(row_id + "\t" + display + "\n" for row_id, display in lines)
    write_atomic(session.root / "list.tsv", body)
    write_atomic(session.root / "query", text)
    return body


def mutate(session: Session, mode: str, row_id: str) -> None:
    """Open or close the current row's category."""
    category = category_of(session, row_id)
    if not category:
        return
    values = session.expanded()
    if mode == "toggle":
        mode = "collapse" if category in values else "expand"
    if mode == "expand":
        values.add(category)
        if "/" in category:
            values.add(category.split("/", 1)[0])
    else:
        values.discard(category)
    session.save_expanded(values)


def all_categories(session: Session) -> Set[str]:
    """Every category id that has a header."""
    return {str(r.get("cat", "")) for r in session.all_rows() if r.get("kind") == "header"}


# ----- positions ---------------------------------------------------------------


def _listed_ids(session: Session) -> List[str]:
    return [line.split("\t", 1)[0] for line in read_text(session.root / "list.tsv").splitlines()]


def _cursor_index(session: Session, ids: Sequence[str]) -> int:
    """Index of the current row in list.tsv (FZF_POS when the id is missing)."""
    row_id = current_id(session)
    if row_id in ids:
        return ids.index(row_id)
    try:
        pos = int(os.environ.get("FZF_POS", "1"))
    except ValueError:
        pos = 1
    return max(0, min(len(ids) - 1, pos - 1)) if ids else 0


def nav(session: Session, direction: str) -> str:
    """``pos(N)`` of the previous or next category header (macOS category_nav_action)."""
    ids = _listed_ids(session)
    if not ids:
        return "ignore"
    here = _cursor_index(session, ids)
    headers = [i for i, value in enumerate(ids) if value.startswith("__cat:")]
    if direction == "previous":
        before = [i for i in headers if i < here]
        target = before[-1] if before else here
    else:
        after = [i for i in headers if i > here]
        target = after[0] if after else here
    return "pos({})".format(target + 1)


def jump(session: Session) -> str:
    """Pick a category in a small fzf, then ``pos(N)`` of its header.

    Only offered where the picker set ``palette`` (Linux). Headers are hidden
    while searching, so there is nothing to jump to then.
    """
    import subprocess

    fzf = session.text("fzf")
    lines = [line for line in read_text(session.root / "list.tsv").splitlines() if line.startswith("__cat:")]
    if not fzf or not lines:
        return "ignore"
    dot = session.text("dot", "·")
    argv = [fzf, "--ansi", "--no-multi", "--height=45%", "--border", "--delimiter=\t",
            "--with-nth=2", "--prompt", "category> ",
            "--header", "type to search {0} enter jump {0} esc cancel".format(dot)]
    env = dict(os.environ)
    env.pop("FZF_DEFAULT_COMMAND", None)
    try:
        done = subprocess.run(argv, input="\n".join(lines) + "\n", stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, env=env, encoding="utf-8", check=False)
    except OSError:
        return "ignore"
    chosen = (done.stdout or "").split("\n", 1)[0].split("\t", 1)[0]
    ids = [line.split("\t", 1)[0] for line in lines]
    all_ids = _listed_ids(session)
    if not chosen or chosen not in ids or chosen not in all_ids:
        return "ignore"
    return "pos({})".format(all_ids.index(chosen) + 1)


def enter(session: Session) -> str:
    """What enter does on the current row (macOS enter_action_for)."""
    row_id = current_id(session)
    if row_id.startswith("__cat:"):
        mutate(session, "toggle", row_id)
        return fzf_action("reload", session.text("rows_command"))
    if row_id.startswith("det:") and session.meta.get("mode") == "remove":
        return "accept"      # remove mode lists only detected items aiup can remove
    if (row_id.startswith(("det:", "__updates:status:", "__session:")) or not row_id):
        return "refresh-preview"
    return "accept"


# ----- text panels -------------------------------------------------------------


def keys_text(session: Optional[Session]) -> str:
    """The keys panel (``?``)."""
    dot = session.text("dot", "·") if session else "·"
    palette = bool(session.meta.get("palette")) if session else False
    jump_line = ("pgup/pgdn     previous or next category {} ctrl-g jump to one".format(dot) if palette
                 else "pgup/pgdn     previous or next category {} ctrl-g collapse all".format(dot))
    removing = session is not None and session.meta.get("mode") == "remove"
    act_lines = ([
        "enter         remove the marked or current rows, or open a category",
        "space         mark rows for one action {} ctrl-a mark all".format(dot),
    ] if removing else [
        "enter         act on the row: install, update, switch, open a category",
        "space         mark rows for one action {} ctrl-a mark all".format(dot),
        "ctrl-r        update the marked or current rows",
        "ctrl-d        remove the marked or current rows",
    ])
    lines = [
        "Keys",
        "",
        "type          search names and aliases",
    ] + act_lines + [
        "ctrl-o        open the official docs (also f3, alt-o) {} ctrl-y copy the URL".format(dot),
        "left/right    collapse or expand a category {} ctrl-e toggle it".format(dot),
        "alt-e/alt-c   expand or collapse every category",
        jump_line,
        "ctrl-/        show or hide this panel",
        "esc           close",
        "",
        "Problems and next steps: aiup attention",
        "Move the cursor to return to the item details.",
    ]
    return "\n".join(lines) + "\n"


def header_line(columns: int, palette: bool, no_matches: bool = False, dot: str = "·") -> str:
    """The header text for a width (macOS catalog_header_text). No newline."""
    if no_matches:
        return "No matches {0} try a name or alias {0} aiup coverage shows detection gaps".format(dot)
    if columns < 96:
        return "search {0} enter act {0} ? keys {0} esc close".format(dot)
    jump_word = "ctrl-g categories" if palette else "pgup/pgdn categories"
    return "search names/aliases {0} enter act {0} {1} {0} ? all keys {0} esc close".format(dot, jump_word)


def header_text(session: Session) -> str:
    """The fzf header for the current width and query."""
    _record_port(session)
    try:
        columns = int(os.environ.get("FZF_COLUMNS", "100"))
    except ValueError:
        columns = 100
    no_matches = bool(query().strip()) and not read_text(session.root / "list.tsv").strip()
    return header_line(columns, bool(session.meta.get("palette")), no_matches, session.text("dot", "·")) + "\n"


def _record_port(session: Session) -> None:
    """Save FZF_PORT once so the prefetch can reach fzf's --listen server."""
    port = os.environ.get("FZF_PORT", "")
    path = session.root / "port"
    if port.isdigit() and not path.exists():
        try:
            write_atomic(path, port)
        except OSError:
            pass


def _category_preview(session: Session, category: str) -> str:
    entry = session.categories().get(category) or [category, "", ""]
    name = str(entry[0]) if entry else category
    blurb = str(entry[1]) if len(entry) > 1 else ""
    bold, reset = session.text("bold"), session.text("reset")
    dot = session.text("dot", "·")
    is_open = category in session.opened()
    lines = [bold + name + reset]
    if blurb:
        lines.append(blurb)
    lines.append("")
    lines.append("category  " + category)
    lines.append("action    {} this category".format("collapse" if is_open else "expand"))
    if session.meta.get("palette"):
        lines.append("keys      enter/ctrl-e toggle {0} pgup/pgdn category {0} ctrl-g jump".format(dot))
    else:
        lines.append("keys      enter/ctrl-e toggle {0} pgup/pgdn category".format(dot))
    return "\n".join(lines) + "\n"


def _available_line(session: Session, row_id: str) -> str:
    """The available-version line for an installed tool ("" to leave it out)."""
    data = session.updates().get("available")
    entry = data.get(row_id) if isinstance(data, dict) else None
    label = session.text("available_label", "available ")
    if isinstance(entry, dict):
        status = entry.get("status")
        text = entry.get("version")
        text = _ANSI.sub("", text).strip() if isinstance(text, str) else ""
        text = "".join(ch for ch in text if ch.isprintable())
        if status == "newer":
            # "" means the manager says an update waits but names no version.
            shown = text or "unknown (an update is waiting)"
            return label + session.text("green") + shown + session.text("reset")
        if status == "managed":
            return label + (text or "managed by another updater")
        if status == "current":
            return label + "same as installed"
        if status == "failure":
            return label + "could not check just now"
    if session.updates().get("checking"):
        return label + "checking" + session.text("ellipsis", "…")
    return ""


def preview_text(session: Session) -> str:
    """The preview for the current row."""
    row_id = current_id(session)
    if row_id and not row_id.startswith("__session:"):
        try:
            write_atomic(session.root / "selected", row_id)
        except OSError:
            pass
    if not row_id:
        return "\n"
    if row_id.startswith("__session:"):
        return ENDED + "\n"
    if row_id.startswith("__cat:"):
        return _category_preview(session, row_id[len("__cat:"):])
    if row_id.startswith("__update"):
        extra = session.updates().get("preview")
        lines = extra.get(row_id) if isinstance(extra, dict) else None
        if isinstance(lines, list):
            return "\n".join(str(line) for line in lines) + "\n"
        return "No updates found in completed checks.\n"
    data = session.stamped_json("preview.json")
    lines = data.get("lines", {}).get(row_id) if isinstance(data, dict) else None
    if not isinstance(lines, list):
        return "No details for this row.\n"
    out: List[str] = []
    for line in lines:
        if line == AVAILABLE_SLOT:
            available = _available_line(session, row_id)
            if available:
                out.append(available)
            continue
        out.append(str(line))
    return "\n".join(out) + "\n"


# ----- docs and clipboard ------------------------------------------------------


def _url_for(session: Session, row_id: str) -> str:
    if row_id.startswith("__update:"):
        row_id = row_id[len("__update:"):]
    data = session.stamped_json("preview.json")
    urls = data.get("urls") if isinstance(data, dict) else None
    url = urls.get(row_id, "") if isinstance(urls, dict) else ""
    return url if isinstance(url, str) and _web_url(url) else ""


def _web_url(url: str) -> bool:
    lowered = url.lower()
    if not lowered.startswith(("https://", "http://")):
        return False
    return not any(ord(ch) < 32 or ord(ch) == 127 for ch in url)


def _platform() -> object:
    """aiup's Platform object, imported only for docs and copy."""
    runtime = str(Path(__file__).resolve().parents[2])
    if runtime not in sys.path:
        sys.path.insert(0, runtime)
    from aiup.platform import current  # noqa: PLC0415 (lazy on purpose)

    return current()


def _message(text: str, clear: bool = False) -> str:
    """A transform result that shows ``text`` in the header until the next load."""
    action = fzf_action("change-header", text.replace("\n", " "))
    return action + ("+clear-screen" if clear else "")


def docs(session: Session) -> str:
    """Open the current row's docs or web search in the browser."""
    row_id = current_id(session)
    url = _url_for(session, row_id)
    if not url:
        return _message("No docs link for this row")
    opened = False
    try:
        opened = bool(_platform().open_url(url))  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 (any failure falls back to the stdlib opener)
        try:
            import webbrowser

            opened = webbrowser.open(url)
        except Exception:  # noqa: BLE001
            opened = False
    dot = session.text("dot", "·")
    if opened:
        return _message("Opened " + url, clear=True)
    return _message("Could not open a browser {} {}".format(dot, url), clear=True)


def copy(session: Session) -> str:
    """Copy the current row's URL to the clipboard."""
    row_id = current_id(session)
    url = _url_for(session, row_id)
    if not url:
        return _message("No link to copy for this row")
    try:
        copied = bool(_platform().copy_text(url))  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        copied = False
    dot = session.text("dot", "·")
    if copied:
        return _message("Copied " + url)
    return _message("No clipboard tool found {} {}".format(dot, url))


# ----- entry -------------------------------------------------------------------

_ROW_VERBS = ("rows", "toggle", "expand", "collapse", "expand-all", "collapse-all")
_ACTION_VERBS = ("enter", "nav-prev", "nav-next", "jump", "docs", "copy")


def _ended(verb: str) -> str:
    """What to print when the session is gone, in the form the verb's caller reads."""
    if verb in _ROW_VERBS:
        return ENDED_ID + "\t" + ENDED + "\n"
    if verb in _ACTION_VERBS:
        return fzf_action("change-header", ENDED) + "\n"
    return ENDED + "\n"


# Internal command names the CLI routes here (``aiup __fzf-rows`` and so on,
# design doc section 2.1) mapped to verbs.
_INTERNAL: Dict[str, str] = {
    "__fzf-rows": "rows", "__search-query": "rows", "__fzf-header": "header",
    "__enter-action": "enter", "__cat-toggle": "toggle", "__cat-expand": "expand",
    "__cat-collapse": "collapse", "__cat-expand-all": "expand-all",
    "__cat-collapse-all": "collapse-all", "__cat-jump": "jump", "__cat-nav-prev": "nav-prev",
    "__cat-nav-next": "nav-next", "__fzf-preview": "preview", "__fzf-keys": "keys",
}


def answer(verb: str) -> str:
    """Answer one verb. Raises SessionError when the session is not valid."""
    if verb == "keys":
        try:
            return keys_text(open_session())
        except SessionError:
            return keys_text(None)
    session = open_session()
    if verb in _ROW_VERBS:
        if verb in ("toggle", "expand", "collapse"):
            mutate(session, verb, current_id(session))
        elif verb == "expand-all":
            session.save_expanded(all_categories(session))
        elif verb == "collapse-all":
            session.save_expanded(())
        return emit(session, query())
    if verb == "enter":
        return enter(session) + "\n"
    if verb in ("nav-prev", "nav-next"):
        return nav(session, "previous" if verb == "nav-prev" else "next") + "\n"
    if verb == "jump":
        return jump(session) + "\n"
    if verb == "preview":
        return preview_text(session)
    if verb == "header":
        return header_text(session)
    if verb == "docs":
        return docs(session) + "\n"
    if verb == "copy":
        return copy(session) + "\n"
    raise SessionError("unknown verb")


def main(argv: Sequence[str]) -> int:
    """Entry for fzf bindings. Always exits 0 so fzf shows what was printed."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace", newline="\n")
        except (ValueError, OSError):
            pass
    verb = argv[0] if argv else ""
    started = time.perf_counter()
    try:
        out = answer(verb)
    except (SessionError, OSError, ValueError):
        out = _ended(verb)
    sys.stdout.write(out)
    sys.stdout.flush()
    if os.environ.get("AIUP_TUI_TIMINGS") == "1":
        sys.stderr.write("aiup fast helper {} {:.1f} ms\n".format(verb, (time.perf_counter() - started) * 1000))
    return 0


def run(args: object, ctx: object = None) -> int:
    """Entry for the CLI's internal ``__`` commands (``aiup.commands`` routes them here).

    The picker itself starts this file directly; this path serves the same
    answers when a person or script runs ``aiup __fzf-rows`` inside a session.
    """
    command = str(getattr(args, "command", "") or "")
    verb = _INTERNAL.get(command, command[2:] if command.startswith("__") else command)
    return main([verb])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
