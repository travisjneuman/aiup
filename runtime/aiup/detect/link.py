"""Cross-source linking, run after every pass (cached rows included).

Sources cache raw rows. Linking runs in every process so catalog edits and
newly available providers take effect without touching the per-source cache:

1. Windows: rows owned by an Uninstall entry (PATH commands, Start Menu
   shortcuts, extras) fold into that entry's row;
2. a desktop entry or shortcut that launches a file another row already
   describes (a PATH command, an AppImage) folds with it: the row with an
   exact owner survives, otherwise the app row survives and keeps the command;
3. winget ids from the last explicit correlation are added as facts;
4. every row is classified (population, catalog tool, identity, guidance).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Set, Tuple

from aiup.detect import files, owners
from aiup.detect.items import InventoryItem, fact

if TYPE_CHECKING:
    from aiup.detect.sources import Batch
    from aiup.engine.context import Context

# Sources whose rows can be folded into an Uninstall entry on Windows.
_ARP_FOLDABLE = ("path", "startmenu", "extras")
# Sources whose rows launch a file named by the "target" fact.
_LAUNCHERS = ("desktop", "startmenu")


def _with_fact(item: InventoryItem, name: str, value: str) -> InventoryItem:
    if not value or fact(item, name):
        return item
    return replace(item, facts=item.facts + ((name, value),))


def absorb(cover: InventoryItem, other: InventoryItem) -> InventoryItem:
    """``cover`` with ``other``'s paths, copies and command added."""
    paths = list(cover.paths)
    for path in other.paths:
        if path not in paths:
            paths.append(path)
    copies = list(cover.copies)
    seen = {files.norm(c.resolved) for c in copies}
    for copy in other.copies:
        if files.norm(copy.resolved) not in seen:
            seen.add(files.norm(copy.resolved))
            copies.append(copy)
    merged = replace(
        cover, paths=tuple(paths), copies=tuple(copies), version=cover.version or other.version,
        docs=cover.docs or other.docs, self_updates=cover.self_updates or other.self_updates,
        stale=cover.stale or other.stale,
        facts=cover.facts + tuple(p for p in other.facts if p[0] in ("resolved", "appimage") and not fact(cover, p[0])),
    )
    if other.kind == "command":
        merged = _with_fact(merged, "command", other.name)
    return _with_fact(merged, "also", other.id)


def _owner_rank(item: InventoryItem) -> int:
    """2 for an exact owner, 1 for any owner, 0 for none."""
    if item.owner is None:
        return 0
    return 2 if item.owner.confidence == "exact" else 1


class _Rows:
    """Every row of a pass by id, so folds can drop and replace rows."""

    def __init__(self, batch: "Batch") -> None:
        self.order: List[Tuple[str, str]] = []
        self.rows: Dict[str, InventoryItem] = {}
        for source, items in batch.items.items():
            for item in items:
                if item.id in self.rows:
                    continue
                self.order.append((source, item.id))
                self.rows[item.id] = item

    def fold(self, cover_id: str, other_id: str) -> None:
        cover = self.rows.get(cover_id)
        other = self.rows.get(other_id)
        if cover is None or other is None or cover_id == other_id:
            return
        self.rows[cover_id] = absorb(cover, other)
        del self.rows[other_id]

    def by_source(self) -> Dict[str, Tuple[InventoryItem, ...]]:
        out: Dict[str, List[InventoryItem]] = {}
        for source, item_id in self.order:
            item = self.rows.get(item_id)
            if item is not None:
                out.setdefault(source, []).append(item)
        return {source: tuple(items) for source, items in out.items()}


def _fold_arp(rows: _Rows) -> None:
    for source, item_id in list(rows.order):
        item = rows.rows.get(item_id)
        if item is None or source not in _ARP_FOLDABLE or item.owner is None or item.owner.manager != "arp":
            continue
        if item.owner.package in rows.rows:
            rows.fold(item.owner.package, item_id)


def _files_index(rows: _Rows) -> Dict[str, str]:
    """Real file -> id of the row that names it (PATH commands, AppImages and other files)."""
    out: Dict[str, str] = {}
    for source, item_id in rows.order:
        item = rows.rows.get(item_id)
        if item is None or source in _LAUNCHERS:
            continue
        for name in ("resolved", "target"):
            value = fact(item, name)
            if value:
                out.setdefault(files.norm(value), item_id)
        for copy in item.copies:
            out.setdefault(files.norm(copy.resolved), item_id)
    return out


def _fold_launchers(rows: _Rows) -> None:
    index = _files_index(rows)
    for source, item_id in list(rows.order):
        if source not in _LAUNCHERS:
            continue
        launcher = rows.rows.get(item_id)
        target = fact(launcher, "target") if launcher is not None else ""
        if launcher is None or not target:
            continue
        other_id = index.get(files.norm(target))
        other = rows.rows.get(other_id) if other_id else None
        if other is None or other_id is None:
            continue
        if _owner_rank(other) > _owner_rank(launcher):
            rows.fold(other_id, item_id)
        else:
            rows.fold(item_id, other_id)
            for key, value in list(index.items()):
                if value == other_id:
                    index[key] = item_id


def _winget_ids(ctx: "Context") -> Mapping[str, str]:
    try:
        from aiup.detect import ondemand
    except ImportError:
        return {}
    return ondemand.cached_winget_ids(ctx)


def _winget_tools(ctx: "Context") -> Dict[str, str]:
    """Lower-case winget id -> catalog id for catalog entries installed by winget."""
    out: Dict[str, str] = {}
    for entry_id, entry in owners.catalog_index(ctx).entries.items():
        for target in entry.targets_for(ctx.os_name):
            if target.channel == "winget":
                out.setdefault(target.package.lower(), entry_id)
    return out


def link(ctx: "Context", batch: "Batch") -> None:
    """Fold and classify a pass in place."""
    rows = _Rows(batch)
    if files.is_windows(ctx):
        _fold_arp(rows)
    _fold_launchers(rows)
    winget_ids = _winget_ids(ctx) if files.is_windows(ctx) else {}
    winget_tools = _winget_tools(ctx) if winget_ids else {}
    for item_id in list(rows.rows):
        item = rows.rows[item_id]
        winget_id = winget_ids.get(item_id, "")
        if winget_id:
            item = _with_fact(item, "winget_id", winget_id)
            tool = winget_tools.get(winget_id.lower(), "")
            if tool and item.population == "detected":
                # winget already manages it: the catalog row shows it.
                item = replace(item, tool=tool, population="managed", identity=item.identity or tool)
        rows.rows[item_id] = owners.classify(ctx, item)
    batch.items = rows.by_source()


def all_items(batch: "Batch") -> List[InventoryItem]:
    out: List[InventoryItem] = []
    seen: Set[str] = set()
    for items in batch.items.values():
        for item in items:
            if item.id not in seen:
                seen.add(item.id)
                out.append(item)
    return out


def find(batch: "Batch", item_id: str) -> Optional[InventoryItem]:
    for item in all_items(batch):
        if item.id == item_id:
            return item
    return None


__all__ = ["absorb", "all_items", "find", "link"]
