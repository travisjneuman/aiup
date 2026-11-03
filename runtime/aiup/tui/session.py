"""The picker's session folder, saved UI state and snapshot cache (macOS:
tui_session_create, tui_session_context_valid, tui_generation_* and the
list-query / fzf-expanded state files).

A session is one picker window. Everything the fast helper needs is written
here once, before fzf starts:

- ``token`` (mode 600): a random secret the fast helper must present.
- ``meta.json``: marker, schema, owner pid, view, category names, the fzf
  action strings, display strings, and SHA-256 stamps of the two files below.
- ``rows.json``: every catalog, package and detected row, in order.
- ``preview.json``: preview lines and docs URLs per row id.
- ``updates.json``: the Updates section; the prefetch replaces it whole.
- ``expanded``, ``query``, ``list.tsv``, ``selected``, ``port``: small
  files the fast helper and fzf keep current while the window is open.

The folder is built under a staging name and renamed into place, so the fast
helper never sees half a session.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from aiup.engine.cache import (
    atomic_write_bytes, atomic_write_json, atomic_write_text, read_json, read_text_bounded,
    remove_quietly,
)
from aiup.paths import Dirs, ensure_dir, private_mkdir
from aiup.tui import fast
from aiup.tui.preview import (
    LABEL_WIDTH, inventory_preview_lines, item_url, tool_preview_lines, updates_previews,
)
from aiup.tui.rows import (
    DIM, GREEN, HINT, CategoryInfo, InventoryRecord, Style, ToolRecord, UpdateRecord,
    catalog_rows, detected_rows, packages_rows, updates_section,
)
from aiup.version import AIUP_VERSION

if TYPE_CHECKING:
    from aiup.platform.base import Platform

SESSIONS_FOLDER = "sessions"
SNAPSHOT_SCHEMA = 1
SNAPSHOT_MAX_BYTES = 16 * 1024 * 1024
STATE_MAX_BYTES = 64 * 1024

# UI state kept between picker windows, in the state folder (macOS names).
STATE_QUERY = "list-query"
STATE_CATEGORY = "list-category"
STATE_SELECTED = "list-selected"
STATE_EXPANDED = "fzf-expanded"

UPDATES_NAME = "Updates"
UPDATES_BLURB = "Newer versions aiup verified for the tools installed here."


# ----- data -------------------------------------------------------------------


@dataclass(frozen=True)
class InstalledTool:
    """An installed catalog tool the prefetch checks for a newer version."""

    id: str
    channel: str
    version: str
    label: str = ""
    lifecycle: str = "active"
    eligible: bool = True            # False when held or excluded: shown, never batch-updated

    def to_json(self) -> List[object]:
        """Compact form for the snapshot cache."""
        return [self.id, self.channel, self.version, self.label, self.lifecycle, self.eligible]

    @staticmethod
    def from_json(data: object) -> Optional["InstalledTool"]:
        """Read the compact form back, or None when it does not fit."""
        if not isinstance(data, list) or len(data) != 6:
            return None
        if not all(isinstance(v, str) for v in data[:5]) or not isinstance(data[5], bool):
            return None
        return InstalledTool(str(data[0]), str(data[1]), str(data[2]), str(data[3]), str(data[4]), bool(data[5]))


@dataclass
class SessionData:
    """Everything one picker window shows, ready to write (and to cache)."""

    rows: List[Dict[str, object]]
    lines: Dict[str, List[str]]
    urls: Dict[str, str]
    categories: Dict[str, List[str]]
    installed: List[InstalledTool] = field(default_factory=list)
    forced_open: List[str] = field(default_factory=list)
    show_updates: bool = True
    all_open: bool = False           # --view all: every category starts open

    def to_json(self) -> Dict[str, object]:
        """The snapshot cache document."""
        return {
            "schema": SNAPSHOT_SCHEMA, "rows": self.rows, "lines": self.lines, "urls": self.urls,
            "categories": self.categories, "installed": [t.to_json() for t in self.installed],
            "forced_open": self.forced_open, "show_updates": self.show_updates,
            "all_open": self.all_open,
        }

    @staticmethod
    def from_json(data: object) -> Optional["SessionData"]:
        """A snapshot read back, or None when its shape is wrong."""
        if not isinstance(data, dict) or data.get("schema") != SNAPSHOT_SCHEMA:
            return None
        rows, lines, urls = data.get("rows"), data.get("lines"), data.get("urls")
        categories, installed = data.get("categories"), data.get("installed")
        if not (isinstance(rows, list) and isinstance(lines, dict) and isinstance(urls, dict)
                and isinstance(categories, dict) and isinstance(installed, list)):
            return None
        tools = [t for t in (InstalledTool.from_json(item) for item in installed) if t is not None]
        forced = data.get("forced_open")
        return SessionData(
            rows=[r for r in rows if isinstance(r, dict)], lines=lines, urls=urls,
            categories=categories, installed=tools,
            forced_open=[str(c) for c in forced] if isinstance(forced, list) else [],
            show_updates=bool(data.get("show_updates")), all_open=bool(data.get("all_open")),
        )

    def header_ids(self) -> Set[str]:
        """Every category id that has a header row."""
        return {str(r.get("cat", "")) for r in self.rows if r.get("kind") == "header"}


def _category_entry(info: CategoryInfo) -> List[str]:
    return [info.name, info.blurb, info.emoji]


def populations(view: str, category_filter: str) -> Tuple[bool, bool, bool]:
    """Which populations a view and --category show: (catalog, packages, detected)."""
    if category_filter == "detected":
        return (False, False, True)
    if category_filter == "packages" or category_filter.startswith("packages/"):
        return (False, True, False)
    if category_filter:
        return (True, False, False)
    if view == "managed":
        return (True, False, False)
    if view == "detected":
        return (False, False, True)
    if view == "available":
        return (False, True, False)
    return (True, True, True)


def assemble(
    categories: Sequence[CategoryInfo], tools: Sequence[ToolRecord],
    packages: Sequence[InventoryRecord], detected: Sequence[InventoryRecord],
    installed: Sequence[InstalledTool], style: Style, os_name: str, *,
    view: str = "overview", sort_mode: str = "id", category_filter: str = "",
    manager_names: Optional[Mapping[str, str]] = None, mode: str = "browse",
) -> SessionData:
    """Rows, previews and URLs for one picker window.

    ``categories`` holds the catalog categories plus the ``packages`` and
    ``detected`` pseudo categories. ``category_filter`` is the --category
    value, already checked by the CLI. In ``remove`` mode only installed
    catalog tools show (macOS pick_catalog_tools remove), with no updates
    row; the caller passes only the inventory rows aiup can remove.
    """
    installed_only = view == "installed" or mode == "remove"
    names = {c.id: c for c in categories}
    want_catalog, want_packages, want_detected = populations(view, category_filter)
    rows: List[Dict[str, object]] = []
    lines: Dict[str, List[str]] = {}
    urls: Dict[str, str] = {}
    meta_categories: Dict[str, List[str]] = {"updates": [UPDATES_NAME, UPDATES_BLURB, ""]}
    if want_catalog:
        shown = [c for c in categories if not _pseudo(c.id)]
        if category_filter:
            shown = [c for c in shown if c.id == category_filter]
        keep = {c.id for c in shown}
        members = [t for t in tools if t.category in keep]
        for row in catalog_rows(shown, members, style, sort_mode, installed_only=installed_only):
            rows.append(row.to_json())
        for record in members:
            info = names.get(record.category)
            lines[record.id] = tool_preview_lines(record, info.name if info else record.category, style)
            if record.docs:
                urls[record.id] = record.docs
        meta_categories.update({c.id: _category_entry(c) for c in shown})
    if want_packages and packages:
        info = names.get("packages") or CategoryInfo("packages", "Packages")
        chosen = list(packages)
        if category_filter.startswith("packages/"):
            manager = category_filter.split("/", 1)[1]
            chosen = [p for p in chosen if p.source == manager]
        for row in packages_rows(info, chosen, style, manager_names):
            rows.append(row.to_json())
        meta_categories["packages"] = _category_entry(info)
        for manager in sorted({p.source or "other" for p in chosen}):
            label = (manager_names or {}).get(manager, manager)
            meta_categories["packages/" + manager] = [label, "Packages installed with " + label + ".", ""]
        _inventory_previews(chosen, os_name, style, lines, urls)
    if want_detected and detected:
        info = names.get("detected") or CategoryInfo("detected", "Detected")
        for row in detected_rows(info, detected, style):
            rows.append(row.to_json())
        meta_categories["detected"] = _category_entry(info)
        _inventory_previews(detected, os_name, style, lines, urls)
    forced: List[str] = []
    if category_filter:
        forced.append(category_filter)
        if "/" in category_filter:
            forced.append(category_filter.split("/", 1)[0])
    return SessionData(
        rows=rows, lines=lines, urls=urls, categories=meta_categories,
        installed=list(installed), forced_open=forced,
        show_updates=want_catalog and not category_filter and view != "detected" and mode != "remove",
        all_open=(view == "all"),
    )


def _pseudo(category_id: str) -> bool:
    return category_id in ("packages", "detected", "updates")


def _inventory_previews(records: Iterable[InventoryRecord], os_name: str, style: Style,
                        lines: Dict[str, List[str]], urls: Dict[str, str]) -> None:
    for record in records:
        lines[record.id] = inventory_preview_lines(record, os_name, style)
        urls[record.id] = item_url(record, os_name)


# ----- display strings the fast helper uses ----------------------------------------


def display_strings(style: Style) -> Dict[str, str]:
    """Colors and glyphs fast.py needs, so it never formats with its own palette."""
    g = style.glyphs
    label = style.paint(DIM, "available".ljust(LABEL_WIDTH - 1)) + " "
    return {
        "dot": g.dot, "ellipsis": g.ellipsis,
        "bold": style.sgr("1"), "reset": style.reset, "green": style.sgr("1;" + GREEN),
        "hint_prefix": "  " + style.sgr(HINT) + g.dot + " ",
        "hint_suffix": style.reset,
        "available_label": label,
    }


# ----- the live session ------------------------------------------------------------


class LiveSession:
    """One open session folder."""

    def __init__(self, root: Path, token: str, style: Style) -> None:
        self.root = root
        self.token = token
        self.style = style
        self._lock = threading.Lock()
        self._closed = False

    def env(self) -> Dict[str, str]:
        """Variables fzf passes on to the fast helper."""
        return {fast.ENV_SESSION: str(self.root), fast.ENV_TOKEN: self.token}

    def publish_updates(self, records: Sequence[UpdateRecord], checking: bool,
                        available: Mapping[str, Tuple[str, str]]) -> None:
        """Replace the Updates section and the available-version answers.

        ``available`` maps a tool id to (status, text) with status newer,
        current, managed or failure. ``text`` is the newer version ("" when
        the manager names none) or, for managed, the note saying who updates
        the copy. The write is one ``os.replace``; on
        Windows it is retried briefly while a helper has the file open.
        """
        document = {
            "rows": [row.to_json() for row in updates_section(records, self.style, checking)],
            "preview": updates_previews(records, self.style, checking),
            "available": {tool: {"status": status, "version": version}
                          for tool, (status, version) in available.items()},
            "checking": checking,
        }
        data = json.dumps(document, separators=(",", ":")).encode("utf-8")
        with self._lock:
            # After close() a late prefetch answer is dropped; writing it
            # would create the removed folder again.
            if self._closed:
                return
            for attempt in range(25):
                try:
                    atomic_write_bytes(self.root / "updates.json", data)
                    return
                except PermissionError:
                    if attempt == 24:
                        raise
                    time.sleep(0.02)

    def read_text(self, name: str) -> str:
        """A small mutable file from the session ("" when missing)."""
        return read_text_bounded(self.root / name, STATE_MAX_BYTES) or ""

    def expanded(self) -> Set[str]:
        """The open categories right now."""
        return {line.strip() for line in self.read_text("expanded").splitlines() if line.strip()}

    def port(self) -> Optional[int]:
        """fzf's listen port, once the header helper recorded it."""
        text = self.read_text("port").strip()
        if text.isdigit() and text.isascii() and 0 < int(text) < 65536:
            return int(text)
        return None

    def close(self) -> None:
        """Remove the session folder. Later publish_updates calls do nothing."""
        with self._lock:
            self._closed = True
            remove_session(self.root)


def _write(root: Path, name: str, data: bytes) -> str:
    atomic_write_bytes(root / name, data)
    return hashlib.sha256(data).hexdigest()


def create(
    dirs: Dirs, data: SessionData, style: Style, *, expanded: Iterable[str],
    actions: Mapping[str, str], fzf_path: str, palette: bool, platform_name: str,
    view: str = "overview", sort_mode: str = "id", category_filter: str = "", mode: str = "",
) -> LiveSession:
    """Write a new session folder and return it.

    ``actions`` holds the fzf command strings the helper prints back
    (``rows_command`` is the one enter needs). ``palette`` is True where the
    nested category chooser (ctrl-g) works.
    """
    base = ensure_dir(dirs.runtime / SESSIONS_FOLDER)
    name = "{}-{}".format(os.getpid(), secrets.token_hex(6))
    staging = base / (".staging-" + name)
    private_mkdir(staging)
    try:
        token = secrets.token_hex(24)
        atomic_write_text(staging / "token", token)
        stamps = {
            "rows.json": _write(staging, "rows.json",
                                json.dumps({"rows": data.rows}, separators=(",", ":")).encode("utf-8")),
            "preview.json": _write(staging, "preview.json",
                                   json.dumps({"lines": data.lines, "urls": data.urls},
                                              separators=(",", ":")).encode("utf-8")),
        }
        known = data.header_ids() | {"updates"}
        opened = sorted(known if data.all_open else (set(expanded) & known))
        atomic_write_text(staging / "expanded", "".join(c + "\n" for c in opened))
        atomic_write_text(staging / "query", "")
        meta: Dict[str, object] = {
            "marker": fast.MARKER, "schema": fast.SCHEMA, "aiup_version": AIUP_VERSION,
            "owner_pid": os.getpid(), "created": int(time.time()), "platform": platform_name,
            "view": view, "sort": sort_mode, "category_filter": category_filter, "mode": mode,
            "stamps": stamps, "categories": data.categories, "forced_open": data.forced_open,
            "updates": data.show_updates, "palette": palette, "fzf": fzf_path,
        }
        meta.update(actions)
        meta.update(display_strings(style))
        atomic_write_json(staging / "meta.json", meta)
        root = base / name
        os.rename(str(staging), str(root))
    except BaseException:
        remove_session(staging)
        raise
    live = LiveSession(root, token, style)
    if data.show_updates:
        live.publish_updates((), True, {})
    return live


# ----- cleanup -------------------------------------------------------------------


def _familiar(folder: Path) -> bool:
    """True for a folder this code made: a staging folder or a marked session."""
    if folder.name.startswith(".staging-"):
        return True
    meta = read_json(folder / "meta.json", STATE_MAX_BYTES * 16)
    return isinstance(meta, dict) and meta.get("marker") == fast.MARKER


def _owner_pid(folder: Path) -> Optional[int]:
    head = folder.name.replace(".staging-", "", 1).split("-", 1)[0]
    return int(head) if head.isdigit() and head.isascii() else None


def remove_session(folder: Path) -> None:
    """Delete one session folder. Links are never followed."""
    try:
        if folder.is_symlink() or not folder.is_dir():
            return
        shutil.rmtree(str(folder), ignore_errors=True)
    except OSError:
        pass


def cleanup_stale(dirs: Dirs, platform: "Platform", ttl: int) -> int:
    """Remove sessions whose window is gone, or that are older than ``ttl``.

    Only folders this code made are touched. Returns how many were removed.
    """
    base = dirs.runtime / SESSIONS_FOLDER
    if base.is_symlink() or not base.is_dir():
        return 0
    removed = 0
    now = time.time()
    for folder in base.iterdir():
        if folder.is_symlink() or not folder.is_dir() or not _familiar(folder):
            continue
        pid = _owner_pid(folder)
        if pid == os.getpid():
            continue
        try:
            age = now - folder.stat().st_mtime
        except OSError:
            continue
        if pid is None or age > ttl or not _alive(platform, pid):
            remove_session(folder)
            removed += 1
    return removed


def _alive(platform: "Platform", pid: int) -> bool:
    try:
        return bool(platform.pid_alive(pid))
    except (OSError, ValueError, NotImplementedError):
        return True


# ----- UI state between windows --------------------------------------------------


@dataclass
class UiState:
    """Where the person was when the picker last closed."""

    query: str = ""
    category: str = ""
    selected: str = ""
    expanded: Set[str] = field(default_factory=set)
    known: bool = False              # False when nothing was saved yet


def _state_text(dirs: Dirs, name: str) -> Optional[str]:
    return read_text_bounded(dirs.state / name, STATE_MAX_BYTES)


def load_ui_state(dirs: Dirs) -> UiState:
    """The saved query, category, selected row and open categories."""
    expanded_text = _state_text(dirs, STATE_EXPANDED)
    return UiState(
        query=(_state_text(dirs, STATE_QUERY) or "").split("\n", 1)[0],
        category=(_state_text(dirs, STATE_CATEGORY) or "").strip(),
        selected=(_state_text(dirs, STATE_SELECTED) or "").strip(),
        expanded={line.strip() for line in (expanded_text or "").splitlines() if line.strip()},
        known=expanded_text is not None,
    )


def save_ui_state(dirs: Dirs, state: UiState) -> None:
    """Store the UI state. Failures are ignored: it is a convenience."""
    files = {
        STATE_QUERY: state.query.replace("\n", " ") + "\n",
        STATE_CATEGORY: state.category + "\n",
        STATE_SELECTED: state.selected + "\n",
        STATE_EXPANDED: "".join(c + "\n" for c in sorted(state.expanded)),
    }
    try:
        for name, text in files.items():
            atomic_write_text(dirs.state / name, text)
    except OSError:
        pass
    except Exception:  # noqa: BLE001 (AiupError from a symlinked state folder)
        pass


def read_back(live: LiveSession) -> UiState:
    """The UI state from a session that just closed."""
    selected = live.read_text("selected").strip()
    category = ""
    if selected.startswith("__cat:"):
        category = selected[len("__cat:"):]
    return UiState(query=live.read_text("query").split("\n", 1)[0], category=category,
                   selected=selected, expanded=live.expanded(), known=True)


# ----- snapshot cache ------------------------------------------------------------


def snapshot_key(parts: Sequence[str]) -> str:
    """A file-safe key for everything the snapshot depends on."""
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def file_stamp(path: Path) -> str:
    """Size and mtime of a settings file, so editing it starts a new snapshot."""
    try:
        info = path.stat()
    except OSError:
        return "-"
    return "{}:{}".format(info.st_size, info.st_mtime_ns)


def _snapshot_path(dirs: Dirs, key: str) -> Path:
    return dirs.cache / "tui" / "v{}".format(SNAPSHOT_SCHEMA) / "generations" / (key + ".json")


def load_snapshot(dirs: Dirs, key: str, ttl: int) -> Optional[SessionData]:
    """A cached SessionData younger than ``ttl`` seconds, or None."""
    path = _snapshot_path(dirs, key)
    try:
        if path.is_symlink() or time.time() - path.stat().st_mtime > ttl:
            return None
    except OSError:
        return None
    return SessionData.from_json(read_json(path, SNAPSHOT_MAX_BYTES))


def save_snapshot(dirs: Dirs, key: str, data: SessionData) -> None:
    """Cache a SessionData. Older snapshots in the folder are removed."""
    path = _snapshot_path(dirs, key)
    try:
        atomic_write_bytes(path, json.dumps(data.to_json(), separators=(",", ":")).encode("utf-8"))
        for other in path.parent.glob("*.json"):
            if other.name != path.name:
                remove_quietly(other)
    except OSError:
        pass
    except Exception:  # noqa: BLE001 (AiupError from a symlinked cache folder)
        pass


def drop_snapshots(dirs: Dirs) -> None:
    """Forget every snapshot (after the picker changed a tool)."""
    folder = _snapshot_path(dirs, "x").parent
    if folder.is_symlink() or not folder.is_dir():
        return
    for other in folder.glob("*.json"):
        remove_quietly(other)
