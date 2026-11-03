"""aiup plan (macOS: cmd_plan).

A read-only check first, so each tool with an update gets its own card with
what's new; the rest are grouped. Nothing is installed or changed.
Steps that need more rights are marked: ``needs sudo`` (Linux), ``may ask
Windows for approval`` and ``needs an elevated terminal`` (Windows).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from aiup.commands import _common
from aiup.engine import host
from aiup.engine.channels import channel_label
from aiup.engine.check import CheckItem, check_items
from aiup.engine.prefs import IdRules, load_preferences, policy_reason
from aiup.engine.privilege import SUDO_PROVIDERS
from aiup.engine.releasenotes import lookup_notes
from aiup.errors import EXIT_OK, AiupError

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.cli import Args
    from aiup.engine.context import Context

GROUPED = ("check and update if needed", "current (self-updated)", "up to date")
Card = Tuple[str, str]


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Print the maintenance plan cards."""
    ctx, catalog = _common.need(args, ctx)
    prefs = load_preferences(ctx.dirs, IdRules(set(catalog.ids())))
    ctx.say("  Reading installed versions…")
    items: List[CheckItem] = []
    checked = True
    try:
        items = check_items(ctx, catalog, ())
    except (OSError, ValueError, AiupError):
        checked = False
    tools = [item.job.tool for item in items] if checked else list(_common.installed_copies(ctx, catalog))
    by_tool: Dict[str, CheckItem] = {item.job.tool: item for item in items}
    ready = [item for item in items if item.row.result == "update"]
    notes = _notes(ctx, catalog, ready)

    cards: List[Card] = []
    if checked:
        count = _common.plural(len(ready), "update")
        cards.append(("Preview only · no packages will change",
                      count + " ready, from a read-only check. Exact download sizes depend on each updater; "
                      "aiup never replaces an open app. Run aiup to install them."))
    else:
        cards.append(("Preview only · no packages will change",
                      "The version check could not run, so this lists what a run would check. Exact download "
                      "sizes depend on each updater; aiup never replaces an open app."))
    for tool in tools:
        cards.append(_card(ctx, catalog, tool, by_tool.get(tool), policy_reason(prefs, tool), notes))
    _common.cards("maintenance plan", _grouped(cards, args.all_rows))
    return EXIT_OK


def _notes(ctx: "Context", catalog: "Catalog", ready: List[CheckItem]) -> Dict[str, str]:
    """tool -> "summary · link" for tools with an update."""
    if not ready:
        return {}
    try:
        found = lookup_notes(ctx, catalog, [(item.row.tool, item.row.after) for item in ready])
    except Exception:  # noqa: BLE001  release notes never fail the plan
        return {}
    out: Dict[str, str] = {}
    for note in found:
        text = _common.clean(note.summary) or "Release notes"
        link = _common.clean(note.link)
        out[note.tool] = text + (" · " + link if link else "")
    return out


def _card(ctx: "Context", catalog: "Catalog", tool: str, item: Optional[CheckItem], policy: str,
          notes: Dict[str, str]) -> Card:
    if policy:
        return (tool + " · leave unchanged", policy)
    mark = _rights_mark(ctx, item)
    suffix = " · " + mark if mark else ""
    if item is not None and item.row.result == "update":
        title = "{} · update {} → {}{}".format(tool, item.row.before, item.row.after, suffix)
        return (title, notes.get(tool, "Release notes were not found."))
    if item is not None and item.row.result in ("current", "self-updated"):
        return (tool + " · up to date", "No newer version found. Nothing to download.")
    return (tool + " · check and update if needed" + suffix,
            _method(ctx, catalog, tool, item) + ". Downloads may be required; save work in desktop apps "
            "before updating.")


def _method(ctx: "Context", catalog: "Catalog", tool: str, item: Optional[CheckItem]) -> str:
    """The channel a run would use, as people know it."""
    channel = item.job.channel if item is not None else ""
    if not channel:
        entry = catalog.get(tool)
        targets = entry.targets_for(ctx.os_name) if entry is not None else ()
        channel = targets[0].channel if targets else ""
    return channel_label(channel) if channel else "Original installation method"


def _rights_mark(ctx: "Context", item: Optional[CheckItem]) -> str:
    """How much a run of this tool's channel may need beyond the user's rights."""
    channel = item.job.channel if item is not None else ""
    if not channel:
        return ""
    if ctx.os_name == "linux" and channel in SUDO_PROVIDERS and not host.is_root():
        return "needs sudo"
    if ctx.os_name == "windows":
        if channel == "choco" and not host.is_elevated(ctx.platform):
            return "needs an elevated terminal"
        if channel == "winget":
            return "may ask Windows for approval"
    return ""


def _grouped(cards: List[Card], show_all: bool) -> List[Card]:
    """Collapse the routine cards into one per kind (macOS cmd_plan's grouping)."""
    if show_all:
        return cards
    out: List[Card] = []
    groups: "OrderedDict[Tuple[str, str], List[str]]" = OrderedDict()
    for title, body in cards:
        name, _, label = title.partition(" · ")
        if label in GROUPED:
            groups.setdefault((label, body), []).append(name)
        else:
            out.append((title, body))
    for (label, body), names in groups.items():
        head = _common.plural(len(names), "tool") + " · " + label
        out.append((head, body + " Examples: " + ", ".join(names[:5]) + "."))
    if groups:
        out.append(("See each tool", "aiup plan --all lists the complete selection."))
    return out
