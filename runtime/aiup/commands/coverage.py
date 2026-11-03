"""aiup coverage [--all] (macOS: cmd_coverage).

Supported versus present tools per category, then detected software aiup
has no reviewed updater for. The macOS "Recognized media apps" section is
not shown here: those manual-update rows describe Mac apps only. Nor is
the "require explicit adoption" count: copies on channels aiup cannot
update are not read here, so the count would always be zero.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from aiup.commands import _common
from aiup.errors import EXIT_OK

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.cli import Args
    from aiup.engine.context import Context

GAP_LIMIT = 12


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Print the coverage report."""
    ctx, catalog = _common.need(args, ctx)
    out = _common.stdout()
    show_all = bool(args.all_rows)
    copies = _common.installed_copies(ctx, catalog)
    offered = list(catalog.available_on(ctx.os_name))
    lines: List[str] = [_common.ink("\naiup · coverage", "141", out)]
    for category in catalog.tool_categories():
        members = [entry for entry in offered if entry.category == category.id]
        if not members:
            continue
        present = sum(1 for entry in members if entry.id in copies)
        lines.append("  {:18} {:3} present / {:3} supported".format(category.id, present, len(members)))

    lines.append("\n" + _common.ink("{} catalog tools present".format(len(copies)), "81", out))
    if show_all:
        for entry in offered:
            found = copies.get(entry.id)
            if not found:
                continue
            target, _ = found[0]
            lines.append("  {:22} Managed update contract · {} · {}".format(
                entry.id, target.channel, target.package or "official installer"))

    lines.append("\n" + _common.ink("Coverage gaps on this computer · candidates for reviewed adapters", "220", out))
    gaps = [item for item in _common.detected_items(ctx)
            if str(getattr(item, "population", "detected") or "detected") == "detected"]
    shown = gaps if show_all else gaps[:GAP_LIMIT]
    for item in shown:
        name = _common.clean(getattr(item, "name", "") or getattr(item, "id", ""))
        source = _common.clean(getattr(item, "source", "") or "unknown")
        lines.append("  {} · {} · detected only; updater not reviewed".format(name, source))
    if not gaps:
        lines.append("  None found.")
    if not show_all and len(gaps) > GAP_LIMIT:
        lines.append("  … {} more · aiup coverage --all or aiup inventory".format(len(gaps) - GAP_LIMIT))

    packages = _package_count(ctx, catalog)
    lines.append("\n  {} installed packages have explicit picker actions.".format(packages))
    lines.append("  Default updates cover installed catalog tools. Packages update from the picker; "
                 "detected-only software remains inspect-only.")
    out.write("\n".join(lines) + "\n")
    out.flush()
    return EXIT_OK


def _package_count(ctx: "Context", catalog: "Catalog") -> int:
    from aiup.commands import listing

    try:
        return len(listing.scan_packages(ctx, catalog))
    except (OSError, ValueError):
        return 0
