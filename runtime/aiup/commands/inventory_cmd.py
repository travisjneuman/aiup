"""aiup inventory [--plain|--refresh] (macOS: print_inventory_definition).

Detected-only software from this system's detection sources, as JSON (the
macOS shape) or a plain table. ``--refresh`` reads every source again.
Nothing found here is run.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Dict, List, Optional

from aiup.commands import _common
from aiup.errors import EXIT_OK

if TYPE_CHECKING:
    from aiup.cli import Args
    from aiup.engine.context import Context


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Print the inventory."""
    ctx, _ = _common.need(args, ctx)
    items = _records(ctx)
    out = _common.stdout()
    if args.inventory_mode == "plain":
        lines = ["{:<26} {:<12} {:<18} {}".format("item", "version", "found via", "location")]
        for item in sorted(items, key=lambda i: (str(i["label"]), str(i["id"]))):
            lines.append("{:<26} {:<12} {:<18} {}".format(item["label"], item["version"], item["source"],
                                                         item["path"]))
        out.write("\n".join(lines) + "\n")
    else:
        out.write(json.dumps({"name": "aiup", "items": items}, indent=2, ensure_ascii=False) + "\n")
    out.flush()
    return EXIT_OK


def _records(ctx: "Context") -> List[Dict[str, object]]:
    from aiup.tui.preview import search_url
    from aiup.tui.rows import InventoryRecord

    out: List[Dict[str, object]] = []
    seen = set()
    for raw in _common.detected_items(ctx):
        if str(getattr(raw, "population", "detected") or "detected") != "detected":
            continue
        source = _common.clean(getattr(raw, "source", "") or "")
        key = _common.clean(getattr(raw, "id", "") or getattr(raw, "name", ""))
        if not key:
            continue
        item_id = key if key.startswith("det:") else "det:" + source + ":" + key
        if item_id in seen:
            continue
        seen.add(item_id)
        name = _common.clean(getattr(raw, "name", "") or key)
        version = _common.clean(getattr(raw, "version", "") or "") or "unknown"
        paths = tuple(getattr(raw, "paths", ()) or ())
        path = _common.clean(paths[0]) if paths else ""
        manual = bool(getattr(raw, "manual", False))
        record = InventoryRecord(id=item_id, population="detected", name=name, version=version,
                                 source=source, path=path)
        owner = getattr(raw, "owner", None)
        guidance = _common.clean(getattr(raw, "guidance", "") or "")
        docs = _common.clean(getattr(raw, "docs", "") or "")
        description = _common.clean(getattr(raw, "description", "") or "")
        out.append({
            "category": "detected",
            "state": "detected",
            "id": item_id,
            "label": name,
            "version": version,
            "source": source,
            "path": path,
            "search": search_url(record, ctx.os_name),
            "management": "manual" if manual else "detected-only",
            "category_hint": None,
            "update_guidance": guidance or None,
            "docs": docs or None,
            "owner": _common.owner_text(owner) if owner else None,
            "description": description or None,
        })
    return out
