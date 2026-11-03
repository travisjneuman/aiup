"""Row and header formatting for the picker (macOS: format_catalog_display,
format_category_header, category_meter, format_inventory_display and the
Updates rows of tui_updates_publish).

Everything here is pure: it takes plain records and a :class:`Style` and
returns text. The picker writes that text into the session once, so moving
the cursor or typing never formats a row again.

Widths are measured in terminal cells (:func:`display_width`), so names with
East Asian wide characters or emoji line up with plain ASCII names.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from aiup.model import PENDING_UPDATE_NOTE

# ----- palette ------------------------------------------------------------

# 256-color codes per category, as in macOS catalog_ansi.
CATEGORY_COLORS: Mapping[str, int] = {
    "updates": 82, "infra": 39, "coding-agents": 171, "agent-tools": 177,
    "workspaces": 219, "editors": 111, "terminals": 81, "mcp": 141,
    "sandboxes": 109, "chat": 51, "browsers": 45, "local-apps": 85,
    "voice": 204, "image-gen": 199, "media": 213, "media-tools": 175,
    "automation": 184, "dev-utils": 75, "local-ai": 48, "llm-utils": 208,
    "adapters": 220, "community-agents": 165, "orchestrators": 207,
    "detected": 250, "packages": 214,
}
DEFAULT_COLOR = 250

# Fixed colors from macOS rows and headers.
INSTALLED_MARK = "1;38;2;57;255;20"
ON_DISK_MARK = "1;38;5;214"
ABSENT_MARK = "38;5;240"
ID_INSTALLED = "1;38;5;255"
LABEL_INSTALLED = "38;5;252"
ID_ABSENT = "38;5;246"
LABEL_ABSENT = "38;5;243"
AMBER = "38;5;214"
LIFECYCLE_TAG = "38;5;220"
METER_EMPTY = "38;5;238"
HEADER_EXTRA = "38;5;245"
HINT = "38;5;240"
GREEN = "38;5;82"
DIM = "38;5;245"
FAINT = "38;5;240"
WHITE = "1;38;5;255"
DETECTED_MARK = "38;5;250"
MANUAL_MARK = "1;38;5;220"
MANUAL_TEXT = "38;5;220"
INV_NAME = "38;5;252"
INV_VERSION = "38;5;250"
INV_SOURCE = "38;5;245"
INV_PATH = "38;5;240"

ID_WIDTH = 18          # macOS %-18s
TOP_NAME_WIDTH = 22    # top-level category names
CHILD_NAME_WIDTH = 18  # child category names (packages/<manager>)

UNKNOWN_VERSION = "unknown"   # same word aiup check prints for a pending update (engine/check.py)
PENDING_TEXT = PENDING_UPDATE_NOTE   # the one wording, shared with aiup check and providers

INV_NAME_WIDTH = 24
INV_VERSION_WIDTH = 12
INV_SOURCE_WIDTH = 16
METER_CELLS = 10


def category_color(category: str) -> int:
    """The 256-color code for a category; child ids use their parent's."""
    top = category.split("/", 1)[0]
    return CATEGORY_COLORS.get(category, CATEGORY_COLORS.get(top, DEFAULT_COLOR))


# ----- glyphs -------------------------------------------------------------


@dataclass(frozen=True)
class TuiGlyphs:
    """Every character the picker draws. Unicode and ASCII sets below."""

    installed: str
    on_disk: str
    absent: str
    detected: str
    manual: str
    stripe: str          # category color bar at the start of each row
    expanded: str
    collapsed: str
    meter_full: str
    meter_empty: str     # only differs from meter_full when there is no color
    update: str
    arrow: str
    dot: str
    ellipsis: str
    prompt: str          # after "aiup" in the fzf prompt
    pointer: str         # fzf --pointer
    marker: str          # fzf --marker
    scrollbar: str       # fzf --scrollbar
    border: str          # fzf --border style


UNICODE_TUI = TuiGlyphs(
    installed="●", on_disk="◐", absent="○", detected="◇", manual="◆",
    stripe="▌", expanded="▾", collapsed="▸", meter_full="━", meter_empty="─",
    update="⇡", arrow="→", dot="·", ellipsis="…", prompt="❯",
    pointer="▶", marker="✓", scrollbar="│", border="rounded",
)

ASCII_TUI = TuiGlyphs(
    installed="*", on_disk="~", absent="o", detected="?", manual="!",
    stripe="|", expanded="v", collapsed=">", meter_full="#", meter_empty="-",
    update="^", arrow="->", dot="|", ellipsis="...", prompt=">",
    pointer=">", marker="+", scrollbar="|", border="sharp",
)


def tui_glyphs(unicode: bool) -> TuiGlyphs:
    """The picker glyph set.

    Row marks, the pointer, the meter cell and the border follow
    ``aiup.platform.term`` (its GlyphSet), so ``AIUP_ASCII=1`` and the legacy
    Windows console rule apply here too. The picker-only characters (stripe,
    arrows, ellipsis) come from the matching set above.
    """
    base = UNICODE_TUI if unicode else ASCII_TUI
    try:
        from aiup.platform import term
    except ImportError:
        return base
    shared = term.UNICODE_GLYPHS if unicode else term.ASCII_GLYPHS
    return TuiGlyphs(
        installed=shared.installed, on_disk=shared.on_disk, absent=shared.absent,
        detected=shared.detected, manual=shared.manual, stripe=base.stripe,
        expanded=base.expanded, collapsed=base.collapsed, meter_full=shared.bar,
        meter_empty=base.meter_empty, update=base.update, arrow=base.arrow,
        dot=base.dot, ellipsis=base.ellipsis, prompt=shared.pointer,
        pointer=base.pointer, marker=base.marker, scrollbar=base.scrollbar,
        border=shared.border,
    )


@dataclass(frozen=True)
class Style:
    """Color on or off plus the glyph set. One per session."""

    color: bool
    glyphs: TuiGlyphs

    def sgr(self, code: str) -> str:
        """An SGR escape for ``code`` ("1;38;5;82"), or "" without color."""
        return "\033[" + code + "m" if self.color and code else ""

    def fg(self, color: int, bold: bool = False) -> str:
        """A 256-color foreground escape, or "" without color."""
        return self.sgr(("1;" if bold else "") + "38;5;" + str(color))

    @property
    def reset(self) -> str:
        """The reset escape, or "" without color."""
        return "\033[0m" if self.color else ""

    def paint(self, code: str, text: str) -> str:
        """``text`` wrapped in ``code`` and a reset (plain without color)."""
        if not self.color or not code or not text:
            return text
        return "\033[" + code + "m" + text + "\033[0m"

    def stripe(self, category: str) -> str:
        """The colored bar that starts every row. A space without color."""
        if not self.color:
            return " "
        return self.fg(category_color(category)) + self.glyphs.stripe + self.reset


def make_style(color: bool, unicode: bool) -> Style:
    """A Style from the two terminal decisions."""
    return Style(color=color, glyphs=tui_glyphs(unicode))


# ----- width-safe text ----------------------------------------------------

_ANSI = re.compile(r"\x1b\[[0-9;:?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_ZERO_WIDTH = frozenset("​‌‍⁠﻿")
_VS16 = "️"


def strip_ansi(text: str) -> str:
    """``text`` without SGR and OSC escape sequences."""
    return _ANSI.sub("", text)


def clean(text: object) -> str:
    """Catalog or inventory text made safe for one fzf row.

    Escapes, tabs, line breaks and other control characters become spaces,
    so a label can never add a field, a line or a color to the row.
    """
    return _CONTROL.sub(" ", strip_ansi(str(text or ""))).strip()


def char_width(ch: str) -> int:
    """Terminal cells one code point takes: 0, 1 or 2."""
    code = ord(ch)
    if code < 32 or 0x7F <= code < 0xA0 or ch in _ZERO_WIDTH:
        return 0
    if 0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF:
        return 0  # variation selectors
    if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    if 0x1F000 <= code <= 0x1FAFF:
        return 2  # emoji blocks this Python's Unicode data may predate
    return 1


def display_width(text: str) -> int:
    """Cells ``text`` takes on screen, ignoring escape sequences.

    A narrow character followed by VS16 (emoji presentation, as in the
    category emoji "⚙️") counts as two cells, which is how current terminals
    draw it.
    """
    plain = strip_ansi(text)
    width = 0
    previous = 0
    for ch in plain:
        if ch == _VS16 and previous == 1:
            width += 1
            previous = 2
            continue
        cells = char_width(ch)
        width += cells
        if cells:
            previous = cells
    return width


def truncate(text: str, width: int, ellipsis: str = "…") -> str:
    """Plain ``text`` cut to at most ``width`` cells, ending in ``ellipsis``."""
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    room = width - display_width(ellipsis)
    if room <= 0:
        return ellipsis[:width]
    out: List[str] = []
    used = 0
    previous = 0
    for ch in text:
        # Count VS16 after a narrow character as one more cell, as display_width does.
        cells = 1 if ch == _VS16 and previous == 1 else char_width(ch)
        if used + cells > room:
            if out and ch == _VS16:
                out.pop()   # never leave the base character without its emoji selector
            break
        out.append(ch)
        used += cells
        if cells:
            previous = 2 if ch == _VS16 else cells
    return "".join(out) + ellipsis


def pad(text: str, width: int) -> str:
    """Plain ``text`` padded with spaces to ``width`` cells (never cut)."""
    return text + " " * max(0, width - display_width(text))


def fit(text: str, width: int, ellipsis: str = "…") -> str:
    """Plain ``text`` cut and padded to exactly ``width`` cells."""
    return pad(truncate(text, width, ellipsis), width)


# ----- records ------------------------------------------------------------


@dataclass(frozen=True)
class CategoryInfo:
    """A category as the picker shows it (from catalog/categories.tsv)."""

    id: str
    name: str
    order: int = 0
    emoji: str = ""
    blurb: str = ""


@dataclass(frozen=True)
class ToolRecord:
    """One catalog tool on this computer."""

    id: str
    category: str
    label: str
    state: str                       # "installed" | "on-disk" | "absent"
    lifecycle: str = "active"
    version: str = ""
    docs: str = ""
    aliases: Tuple[str, ...] = ()
    search_extra: str = ""           # package names, commands
    channel: str = ""                # active channel
    installed_channel: str = ""      # channel the found copy came from
    action: str = ""                 # what enter does, for the preview
    notes: Tuple[Tuple[str, str], ...] = ()   # extra preview fields: (name, value)


@dataclass(frozen=True)
class InventoryRecord:
    """One package-manager package or one detected-only item."""

    id: str                          # pkg:<manager>:<name> or det:<source>:<key>
    population: str                  # "package" | "detected"
    name: str
    version: str = ""
    source: str = ""                 # manager (packages) or detection source
    path: str = ""
    manual: bool = False             # needs a manual update step
    owner: str = ""                  # owning manager, when one is known
    docs: str = ""
    guidance: str = ""


@dataclass(frozen=True)
class UpdateRecord:
    """One Updates row: a tool with a newer version, or a status line."""

    id: str
    installed: str
    available: str                   # "" with status "newer": an update waits, version unknown
    status: str                      # "newer" | "current" | "managed" | "checking" | "unavailable"
    eligible: bool = True
    label: str = ""
    lifecycle: str = "active"
    note: str = ""                   # "managed": who updates this copy (Latest.managed)

    def shown_available(self) -> str:
        """The available version to show; "unknown" when the manager names none."""
        return self.available or UNKNOWN_VERSION


@dataclass(frozen=True)
class Row:
    """One fzf row plus what the fast helper needs to search and toggle it."""

    id: str
    category: str                    # the category the row belongs to
    kind: str                        # header | tool | package | detected | update | updates-all | update-status
    text: str                        # display text; headers: collapsed form
    open_text: str = ""              # headers: expanded form
    search: str = ""                 # casefolded search text ("" = not searchable)
    name: str = ""                   # casefolded name for ranking
    aliases: Tuple[str, ...] = ()
    canonical: str = ""              # tool id an Updates row stands for
    parent: str = ""                 # headers of child categories: the parent id

    def to_json(self) -> Dict[str, object]:
        """The compact form stored in the session (keys read by fast.py)."""
        data: Dict[str, object] = {"id": self.id, "cat": self.category, "kind": self.kind, "text": self.text}
        if self.open_text:
            data["open"] = self.open_text
        if self.search:
            data["search"] = self.search
            data["name"] = self.name
        if self.aliases:
            data["aliases"] = list(self.aliases)
        if self.canonical:
            data["canon"] = self.canonical
        if self.parent:
            data["parent"] = self.parent
        return data


# ----- tool rows ----------------------------------------------------------


def row_state_mark(state: str, style: Style) -> str:
    """The colored state mark (macOS row_state_mark)."""
    g = style.glyphs
    if state == "installed":
        return style.paint(INSTALLED_MARK, g.installed)
    if state == "on-disk":
        return style.paint(ON_DISK_MARK, g.on_disk)
    return style.paint(ABSENT_MARK, g.absent)


def format_catalog_display(record: ToolRecord, style: Style) -> str:
    """One tool row: bar, mark, id in 18 cells, label, lifecycle tag, note."""
    present = record.state in ("installed", "on-disk")
    id_code = ID_INSTALLED if present else ID_ABSENT
    label_code = LABEL_INSTALLED if present else LABEL_ABSENT
    parts = [
        style.stripe(record.category), "   ",
        row_state_mark(record.state, style), " ",
        style.paint(id_code, pad(clean(record.id), ID_WIDTH)), " ",
        style.paint(label_code, clean(record.label)),
    ]
    if record.lifecycle and record.lifecycle != "active":
        parts.append("  " + style.paint(LIFECYCLE_TAG, clean(record.lifecycle)))
    if record.state == "on-disk":
        parts.append("  " + style.paint(AMBER, "on disk"))
    return "".join(parts)


def tool_search_text(record: ToolRecord, category_name: str) -> str:
    """What a search matches for a tool: id, label, packages, aliases, category."""
    words = [record.id, record.label, record.search_extra, " ".join(record.aliases), category_name]
    return " ".join(clean(w) for w in words if w).casefold()


def tool_row(record: ToolRecord, style: Style, category_name: str) -> Row:
    """The Row for one catalog tool."""
    return Row(
        id=record.id, category=record.category, kind="tool",
        text=format_catalog_display(record, style),
        search=tool_search_text(record, category_name),
        name=record.id.casefold(),
        aliases=tuple(a.casefold() for a in record.aliases),
    )


# ----- inventory rows -----------------------------------------------------


def format_inventory_display(record: InventoryRecord, style: Style, category: str) -> str:
    """One package or detected row: mark, name, version, source, path.

    Columns are cut with an ellipsis so long names never push the next
    column out of line (macOS let them overflow).
    """
    g = style.glyphs
    ell = g.ellipsis
    if record.population == "package":
        mark = style.paint(INSTALLED_MARK, g.installed) + " "
    elif record.manual:
        mark = style.paint(MANUAL_MARK, g.manual) + " " + style.paint(MANUAL_TEXT, "manual") + " "
    else:
        mark = style.paint(DETECTED_MARK, g.detected) + " "
    name = style.paint(INV_NAME, fit(clean(record.name), INV_NAME_WIDTH, ell))
    version = style.paint(INV_VERSION, fit(clean(record.version) or "unknown", INV_VERSION_WIDTH, ell))
    source = style.paint(INV_SOURCE, fit(clean(record.source), INV_SOURCE_WIDTH, ell))
    path = style.paint(INV_PATH, clean(record.path))
    return style.stripe(category) + "   " + mark + name + " " + version + " " + source + " " + path


def inventory_row(record: InventoryRecord, style: Style, category: str, category_name: str) -> Row:
    """The Row for one package or detected item."""
    text = " ".join(clean(w) for w in (record.name, record.source, record.owner, category_name) if w)
    return Row(
        id=record.id, category=category,
        kind="package" if record.population == "package" else "detected",
        text=format_inventory_display(record, style, category),
        search=text.casefold(), name=clean(record.name).casefold(),
    )


# ----- category headers ---------------------------------------------------


def category_meter(installed: int, absent: int, style: Style, category: str) -> str:
    """Ten cells showing how much of a category is installed (macOS category_meter).

    Any installed tool fills at least one cell; any missing tool leaves at
    least one empty, so the meter never reads 0 or 10 by rounding alone.
    Without color the empty cells use a lighter character instead.
    """
    total = installed + absent
    if total <= 0:
        return ""
    filled = (installed * METER_CELLS + total // 2) // total
    if installed > 0 and filled == 0:
        filled = 1
    if absent > 0 and filled == METER_CELLS:
        filled = METER_CELLS - 1
    g = style.glyphs
    if style.color:
        full = style.paint("38;5;" + str(category_color(category)), g.meter_full * filled)
        empty = style.paint(METER_EMPTY, g.meter_full * (METER_CELLS - filled))
        return full + empty
    return g.meter_full * filled + g.meter_empty * (METER_CELLS - filled)


def installed_summary(installed: int, absent: int) -> str:
    """`all N installed` or `N of T installed`."""
    if absent == 0 and installed > 0:
        return "all {} installed".format(installed)
    return "{} of {} installed".format(installed, installed + absent)


def format_category_header(
    category: CategoryInfo, installed: int, absent: int, style: Style,
    expanded: bool, extra: Optional[str] = None, indent: int = 0, meter: bool = True,
) -> str:
    """A category header row (macOS format_category_header).

    Top level: bold colored name in 22 cells, the meter, then the summary.
    Children (``indent`` > 0) are indented four cells per level with names
    in 18 cells. ``extra`` replaces the installed summary when given.
    """
    g = style.glyphs
    color = category_color(category.id)
    arrow = g.expanded if expanded else g.collapsed
    summary = extra if extra is not None else installed_summary(installed, absent)
    if indent:
        name = style.fg(color) + pad(clean(category.name), CHILD_NAME_WIDTH) + style.reset
        lead = " " * (indent * 4)
    else:
        name = style.fg(color, bold=True) + pad(clean(category.name), TOP_NAME_WIDTH) + style.reset
        lead = ""
    bar = category_meter(installed, absent, style, category.id) if meter else ""
    middle = (bar + " ") if bar else ""
    return (style.stripe(category.id) + " " + lead + style.fg(color) + arrow + style.reset + " "
            + name + " " + middle + style.paint(HEADER_EXTRA, summary))


def header_row(
    category: CategoryInfo, installed: int, absent: int, style: Style,
    extra: Optional[str] = None, parent: str = "", meter: bool = True,
) -> Row:
    """The Row for a category header with its collapsed and expanded forms."""
    indent = 1 if parent else 0
    closed = format_category_header(category, installed, absent, style, False, extra, indent, meter)
    opened = format_category_header(category, installed, absent, style, True, extra, indent, meter)
    return Row(id="__cat:" + category.id, category=category.id, kind="header",
               text=closed, open_text=opened, parent=parent)


def source_summary(records: Sequence[InventoryRecord], dot: str = "·") -> str:
    """Detected header text: `N found · 4 PATH commands · 2 desktop apps`."""
    counts: Dict[str, int] = {}
    for record in records:
        counts[record.source or "other"] = counts.get(record.source or "other", 0) + 1
    parts = ["{} found".format(len(records))]
    for source, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        parts.append("{} {}".format(count, clean(source)))
    return (" " + dot + " ").join(parts)


def packages_summary(count: int) -> str:
    """Packages header text."""
    return "1 package" if count == 1 else "{} packages".format(count)


# ----- Updates rows -------------------------------------------------------


def updates_title(records: Sequence[UpdateRecord], checking: bool, dot: str = "·", ellipsis: str = "…") -> str:
    """The Updates header title (macOS tui_updates_publish wording).

    Managed copies (another updater owns them) are not counted: they are
    neither updates nor failed checks.
    """
    newer = sum(1 for r in records if r.status == "newer")
    pending = sum(1 for r in records if r.status == "checking")
    failed = sum(1 for r in records if r.status == "unavailable")
    sep = " " + dot + " "
    if newer and not pending and not failed:
        return "Updates available" + sep + str(newer)
    if pending and not newer and not failed:
        if checking:
            return "Updates" + sep + "checking" + ellipsis
        return "Updates" + sep + "{} need checking".format(pending)
    if newer or pending or failed:
        parts = ["Updates"]
        if newer:
            parts.append("{} verified".format(newer))
        if pending:
            parts.append("{} checking".format(pending))
        if failed:
            parts.append("{} unavailable to verify".format(failed))
        return sep.join(parts)
    if checking:
        return "Updates" + sep + "checking" + ellipsis
    return "Updates" + sep + "all verified items current"


def updates_header_row(records: Sequence[UpdateRecord], style: Style, checking: bool) -> Row:
    """The Updates header. It has no meter; its title carries the counts."""
    green = style.fg(82)
    title = updates_title(records, checking, style.glyphs.dot, style.glyphs.ellipsis)

    def build(arrow: str) -> str:
        return (style.stripe("updates") + " " + green + arrow + style.reset + " "
                + style.sgr("1") + green + title + style.reset)
    return Row(id="__cat:updates", category="updates", kind="header",
               text=build(style.glyphs.collapsed), open_text=build(style.glyphs.expanded))


def update_rows(records: Sequence[UpdateRecord], style: Style, checking: bool = False) -> List[Row]:
    """Rows inside Updates: update-all, one per newer tool, then status lines.

    A newer tool with no version (the manager says an update waits) shows
    "unknown" as its available version. Managed copies get no row; the
    tool's own preview says who updates them.
    """
    g = style.glyphs
    rows: List[Row] = []
    eligible = [r for r in records if r.status == "newer" and r.eligible]
    newer = [r for r in records if r.status == "newer"]
    if eligible:
        text = ("   " + style.sgr("1") + style.fg(82) + g.update + style.reset + " "
                + "Update all verified items " + g.dot + " " + str(len(eligible)))
        rows.append(Row(id="__updates:all", category="updates", kind="updates-all", text=text))
    for record in newer:
        text = ("   " + style.fg(82) + g.update + " " + style.sgr(WHITE)
                + fit(clean(record.id), ID_WIDTH, g.ellipsis) + style.reset + " "
                + style.paint(DIM, clean(record.installed)) + " " + style.paint(FAINT, g.arrow) + " "
                + style.paint("1;38;5;82", clean(record.shown_available())) + "  "
                + style.paint(DIM, clean(record.label)))
        if not record.eligible:
            text += "  " + style.paint(AMBER, "manual review")
        search = " ".join((record.id, clean(record.label), "update")).casefold()
        rows.append(Row(id="__update:" + record.id, category="updates", kind="update", text=text,
                        search=search, name=record.id.casefold(), canonical=record.id))
    for record in records:
        if record.status not in ("checking", "unavailable"):
            continue
        words = ("Could not check for updates" if record.status == "unavailable"
                 else "Checking for updates" + g.ellipsis)
        text = (style.paint(DIM, g.stripe if style.color else " ") + "   " + style.paint(FAINT, g.dot) + " "
                + style.paint(DIM, fit(clean(record.id), ID_WIDTH, g.ellipsis)) + " "
                + style.paint(FAINT, words))
        rows.append(Row(id="__updates:status:" + record.id, category="updates",
                        kind="update-status", text=text))
    if not rows:
        words = ("Checking installed tools for updates" + g.ellipsis if checking
                 else "No updates found in completed checks.")
        text = "   " + style.paint(DIM, words)
        rows.append(Row(id="__updates:status:empty", category="updates", kind="update-status", text=text))
    return rows


def updates_section(records: Sequence[UpdateRecord], style: Style, checking: bool) -> List[Row]:
    """The whole Updates section: header first, then its rows."""
    return [updates_header_row(records, style, checking)] + update_rows(records, style, checking)


# ----- whole lists --------------------------------------------------------


def sort_tools(records: Iterable[ToolRecord], mode: str) -> List[ToolRecord]:
    """Tools in one category: present ones first, then missing ones.

    ``mode`` "id" sorts each group by id (macOS default); "label" by label.
    """
    def key(record: ToolRecord) -> Tuple[int, str, str]:
        present = 0 if record.state in ("installed", "on-disk") else 1
        primary = clean(record.label).casefold() if mode == "label" else record.id
        return (present, primary, record.id)
    return sorted(records, key=key)


def catalog_rows(
    categories: Sequence[CategoryInfo], tools: Sequence[ToolRecord], style: Style,
    sort_mode: str = "id", installed_only: bool = False,
) -> List[Row]:
    """Headers and tool rows for every catalog category, in display order.

    With ``installed_only`` (``--view installed``) missing tools and empty
    categories are left out.
    """
    by_category: Dict[str, List[ToolRecord]] = {}
    for record in tools:
        by_category.setdefault(record.category, []).append(record)
    rows: List[Row] = []
    for category in sorted(categories, key=lambda c: c.order):
        members = by_category.get(category.id, [])
        n_inst = sum(1 for r in members if r.state in ("installed", "on-disk"))
        n_abs = len(members) - n_inst
        if installed_only:
            members = [r for r in members if r.state != "absent"]
            n_abs = 0
        if not members:
            continue
        rows.append(header_row(category, n_inst, n_abs, style))
        rows.extend(tool_row(r, style, category.name) for r in sort_tools(members, sort_mode))
    return rows


def packages_rows(
    category: CategoryInfo, records: Sequence[InventoryRecord], style: Style,
    manager_names: Optional[Mapping[str, str]] = None,
) -> List[Row]:
    """The packages section: a header, one child header per manager, rows."""
    if not records:
        return []
    names = manager_names or {}
    rows = [header_row(category, len(records), 0, style, extra=packages_summary(len(records)), meter=False)]
    by_manager: Dict[str, List[InventoryRecord]] = {}
    for record in records:
        by_manager.setdefault(record.source or "other", []).append(record)
    for manager in sorted(by_manager):
        members = sorted(by_manager[manager], key=lambda r: clean(r.name).casefold())
        child = CategoryInfo(id=category.id + "/" + manager, name=names.get(manager, manager))
        rows.append(header_row(child, len(members), 0, style, extra=packages_summary(len(members)),
                               parent=category.id, meter=False))
        rows.extend(inventory_row(r, style, child.id, category.name) for r in members)
    return rows


def detected_rows(category: CategoryInfo, records: Sequence[InventoryRecord], style: Style) -> List[Row]:
    """The detected section: one header (source summary) and its rows."""
    if not records:
        return []
    rows = [header_row(category, len(records), 0, style, extra=source_summary(records, style.glyphs.dot), meter=False)]
    ordered = sorted(records, key=lambda r: (clean(r.name).casefold(), r.id))
    rows.extend(inventory_row(r, style, category.id, category.name) for r in ordered)
    return rows
