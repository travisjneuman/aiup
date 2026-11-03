"""Preview text for the picker and for ``aiup preview TOOL`` (macOS:
print_catalog_preview, tui_preview_static_render and the Updates preview).

The picker renders every preview once into the session (``preview.json``);
the fast helper prints the stored lines and adds the one line that can change
while the picker is open: the available version.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Sequence
from urllib.parse import quote_plus

from aiup.tui.rows import (
    DIM, FAINT, PENDING_TEXT, InventoryRecord, Style, ToolRecord, UpdateRecord, clean,
)

# The fast helper replaces this line with the available version, or drops it.
AVAILABLE_SLOT = "\x00available"

LABEL_WIDTH = 10

STATE_WORDS: Mapping[str, str] = {
    "installed": "installed",
    "on-disk": "on disk",
    "absent": "not installed",
}

OS_WORDS: Mapping[str, str] = {"linux": "Linux", "windows": "Windows", "darwin": "macOS"}


def field_line(name: str, value: str, style: Style) -> str:
    """``name`` in a dim 10-cell column, then ``value``."""
    return style.paint(DIM, name.ljust(LABEL_WIDTH - 1)) + " " + value


def docs_kind(url: str) -> str:
    """"GitHub" for a github.com URL, otherwise "website"."""
    lowered = url.lower()
    return "GitHub" if lowered.startswith(("https://github.com/", "http://github.com/")) else "website"


def tool_preview_lines(record: ToolRecord, category_name: str, style: Style) -> List[str]:
    """Preview lines for one catalog tool."""
    dot = " " + style.glyphs.dot + " "
    title = [style.paint("1", clean(record.id)), clean(category_name),
             STATE_WORDS.get(record.state, record.state)]
    if record.lifecycle:
        title.append(clean(record.lifecycle))
    lines = [dot.join(title)]
    if record.label:
        lines.append(clean(record.label))
    if record.docs:
        lines.append(field_line(docs_kind(record.docs), clean(record.docs), style))
    if record.state in ("installed", "on-disk"):
        lines.append(field_line("installed", clean(record.version) or "version unknown", style))
        lines.append(AVAILABLE_SLOT)
    if record.installed_channel:
        lines.append(field_line("found via", clean(record.installed_channel), style))
    if record.channel and record.channel != record.installed_channel:
        lines.append(field_line("channel", clean(record.channel), style))
    for name, value in record.notes:
        lines.append(field_line(clean(name), clean(value), style))
    if record.action:
        lines.append(field_line("action", clean(record.action), style))
    keys = dot.join(["enter act", "ctrl-r update", "ctrl-d remove", "ctrl-o docs", "ctrl-/ hide"])
    lines.append(field_line("keys", style.paint(FAINT, keys), style))
    return lines


def search_query(record: InventoryRecord, os_name: str) -> str:
    """The web search a person may choose for a detected item."""
    words = [clean(record.name), clean(record.version)]
    words.append(OS_WORDS.get(os_name, os_name))
    if record.source:
        words.append(clean(record.source))
    return " ".join(w for w in words if w)


def search_url(record: InventoryRecord, os_name: str) -> str:
    """A web search URL for a detected item (macOS detected_search_url)."""
    return "https://www.google.com/search?q=" + quote_plus(search_query(record, os_name))


def item_url(record: InventoryRecord, os_name: str) -> str:
    """The docs URL when known, else the web search URL."""
    return record.docs or search_url(record, os_name)


def inventory_preview_lines(record: InventoryRecord, os_name: str, style: Style) -> List[str]:
    """Preview lines for a package or a detected-only item."""
    dot = " " + style.glyphs.dot + " "
    if record.population == "package":
        lines = [dot.join([style.paint("1", clean(record.name)), "package",
                           clean(record.source) or "package manager"])]
        lines.append(field_line("version", clean(record.version) or "unknown", style))
        if record.path:
            lines.append(field_line("location", clean(record.path), style))
        lines.append(field_line("action", "update or remove with " + (clean(record.source) or "its manager"), style))
        keys = dot.join(["enter update", "ctrl-d remove", "ctrl-o docs" if record.docs else "ctrl-o search",
                         "ctrl-y copy URL", "ctrl-/ hide"])
    else:
        lines = [dot.join([style.paint("1", clean(record.name)), "updates handled elsewhere"])]
        item = clean(record.name) + ((dot + clean(record.version)) if record.version else "")
        lines.append(field_line("item", item, style))
        if record.manual:
            lines.append(field_line("update", "manual: " + (clean(record.guidance) or "use the app's own updater"), style))
        else:
            lines.append(field_line("action", "ctrl-d removes it. Update it with the app or package manager that owns it.",
                                    style))
        if record.owner:
            lines.append(field_line("owner", clean(record.owner), style))
        lines.append(field_line("found via", clean(record.source) or "unknown", style))
        if record.path:
            lines.append(field_line("location", clean(record.path), style))
        keys = dot.join((["ctrl-o guidance"] if record.manual else ["ctrl-d remove", "ctrl-o guidance"])
                        + ["ctrl-y copy URL", "ctrl-/ hide"])
    lines.append(field_line("keys", style.paint(FAINT, keys), style))
    lines.append(style.paint(FAINT, item_url(record, os_name)))
    return lines


def updates_previews(records: Sequence[UpdateRecord], style: Style, checking: bool = False) -> Dict[str, List[str]]:
    """Preview lines for every Updates row id (macOS fast helper wording)."""
    g = style.glyphs
    out: Dict[str, List[str]] = {}
    eligible = [r for r in records if r.status == "newer" and r.eligible]
    head = ["Update all verified items " + g.dot + " " + str(len(eligible)),
            field_line("action", "confirm the list, then update one at a time", style)]
    for r in eligible:
        head.append(field_line("item", "{} {} {} {} {}".format(clean(r.id), g.dot, clean(r.installed),
                                                                  g.arrow, clean(r.shown_available())), style))
    head.append(field_line("safety", "aiup reads each installed version again before it changes anything", style))
    out["__updates:all"] = head
    for r in records:
        if r.status == "newer":
            lines = [
                style.paint("1", clean(r.id)) + " " + g.dot + " update available",
                clean(r.label),
                field_line("installed", clean(r.installed), style),
                field_line("available", style.paint("1;38;5;82", clean(r.shown_available())), style),
            ]
            if not r.available:
                lines.append(field_line("note", PENDING_TEXT, style))
            lines.append(field_line("action", "update" if r.eligible else "manual review before update", style))
            out["__update:" + r.id] = lines
        elif r.status in ("checking", "unavailable"):
            status = ("Could not verify an available update" if r.status == "unavailable"
                      else "Checking for updates")
            out["__updates:status:" + r.id] = [
                field_line("tool", clean(r.id), style),
                field_line("status", status, style),
                field_line("meaning", "This does not mean the tool is broken or up to date.", style),
                field_line("next", "Retry with: aiup check --refresh " + clean(r.id), style),
                field_line("action", "Information only; no update starts from this row.", style),
            ]
    empty = ("Checking installed tools for updates" + g.ellipsis if checking
             else "No updates found in completed checks.")
    out["__updates:status:empty"] = [empty,
                                     field_line("action", "Information only; no update starts from this row.", style)]
    return out


def print_catalog_preview(record: ToolRecord, category_name: str, style: Style, available: str = "") -> str:
    """The text ``aiup preview TOOL`` prints (macOS print_catalog_preview)."""
    lines = []
    for line in tool_preview_lines(record, category_name, style):
        if line == AVAILABLE_SLOT:
            if available:
                lines.append(field_line("available", available, style))
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"
