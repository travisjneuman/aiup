"""The three populations and duplicate findings (design 8.1, research 11).

``inventory(ctx)`` puts everything aiup can see into one of three lists:

- managed: catalog tools, whichever source found them;
- packages: packages a manager installed on request that no catalog tool
  covers (``pkg:<manager>:<name>``), from the providers' own inventories;
- detected: everything else (``det:<source>:<key>``).

Findings name the same tool installed more than once: a copy hidden behind
another on PATH, two managers holding one tool, version drift between
copies, and one Flatpak installed for both the user and the system. Copies
that are meant to sit side by side are never flagged: rustup proxies and
other companions, a link and its target, version manager shims, and Node
globals of a version that is not on PATH.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from aiup.detect import files, link, owners
from aiup.detect.items import Copy, InventoryItem, Owner, fact
from aiup.detect.sources import WORKERS, Batch, run_batch
from aiup.errors import AiupError

if TYPE_CHECKING:
    from aiup.engine.context import Context
    from aiup.model import PackageRecord
    from aiup.providers.base import Provider

_ERRORS = (OSError, ValueError, NotImplementedError, AiupError)
# winget list may contact its sources; Appx needs PowerShell. Neither runs in a cheap pass.
NEVER_IN_SCAN = frozenset(("winget",))
SLOW_INVENTORIES = frozenset(("appx",))
VERSION_MANAGERS = frozenset(("nvm", "fnm", "n", "mise", "asdf", "volta", "proto"))


@dataclass(frozen=True)
class Finding:
    """One duplicate-install observation."""

    kind: str                   # "shadowed" | "duplicate" | "scope-twin"
    identity: str
    message: str
    items: Tuple[str, ...]      # item ids involved
    paths: Tuple[str, ...]      # the copies, the one in use first


@dataclass(frozen=True)
class Inventory:
    managed: Tuple[InventoryItem, ...]
    packages: Tuple[InventoryItem, ...]
    detected: Tuple[InventoryItem, ...]
    findings: Tuple[Finding, ...]
    stale: Tuple[str, ...] = ()               # sources served from an old cache
    errors: Mapping[str, str] = field(default_factory=dict)


# ----- package inventories --------------------------------------------------------------------


def _covered_tools(ctx: "Context") -> Dict[Tuple[str, str], str]:
    out: Dict[Tuple[str, str], str] = {}
    for entry_id, entry in owners.catalog_index(ctx).entries.items():
        for target in entry.targets_for(ctx.os_name):
            out.setdefault((target.channel, target.package), entry_id)
    return out


def _read_inventory(ctx: "Context", provider: "Provider") -> List["PackageRecord"]:
    try:
        if not ctx.provider_available(provider.name):
            return []
        return list(provider.inventory(ctx) or ())
    except _ERRORS:
        return []


def package_items(ctx: "Context", include_slow: bool = False) -> List[InventoryItem]:
    """Explicitly installed packages from every available provider, read in parallel."""
    providers = [p for p in ctx.providers()
                 if p.name not in NEVER_IN_SCAN and (include_slow or p.name not in SLOW_INVENTORIES)]
    if not providers:
        return []
    covered = _covered_tools(ctx)
    out: List[InventoryItem] = []
    seen: Set[str] = set()
    with ThreadPoolExecutor(max_workers=max(1, min(WORKERS, len(providers)))) as pool:
        for provider, records in zip(providers, pool.map(lambda p: _read_inventory(ctx, p), providers)):
            for rec in records:
                manager = rec.manager or provider.name
                row_id = "pkg:" + manager + ":" + rec.name
                if not rec.name or not rec.explicit or row_id in seen:
                    continue
                seen.add(row_id)
                tool = covered.get((manager, rec.name), "")
                out.append(InventoryItem(
                    id=row_id, name=rec.name, version=rec.version or "",
                    population="managed" if tool else "package", source=manager, paths=tuple(rec.paths),
                    owner=Owner(manager=manager, package=rec.name, confidence="exact", evidence="package inventory"),
                    kind="package", identity=tool or owners.identity_for(ctx, rec.name),
                    scope=rec.scope or "user", confidence="exact", evidence="package inventory", tool=tool,
                ))
    return out


# ----- findings ------------------------------------------------------------------------------


def _quiet_copy(ctx: "Context", copy: Copy) -> bool:
    """Copies that are never a problem on their own."""
    if copy.owner is not None and copy.owner.manager in VERSION_MANAGERS and not copy.on_path:
        return True
    if not copy.on_path:
        for _manager, _label, root, _depth in owners.manager_dirs(ctx):
            if files.inside(copy.resolved, str(root)):
                return True
    return False


def _who(copy: Copy) -> str:
    return str(copy.owner) if copy.owner is not None else "an unknown installer"


def command_findings(ctx: "Context", item: InventoryItem) -> List[Finding]:
    """Shadowed and extra copies of one command."""
    if item.kind != "command" or fact(item, "companion") or len(item.copies) < 2:
        return []
    first = item.copies[0]
    out: List[Finding] = []
    for copy in item.copies[1:]:
        if _quiet_copy(ctx, copy):
            continue
        if first.owner is not None and copy.owner is not None and \
                (first.owner.manager, first.owner.package) == (copy.owner.manager, copy.owner.package):
            continue
        drift = ""
        if first.version and copy.version and first.version != copy.version:
            drift = " The versions differ ({} and {}).".format(first.version, copy.version)
        if copy.on_path and first.on_path:
            message = "{0}: the copy from {1} at {2} is used. The copy from {3} at {4} is hidden behind it.{5}".format(
                item.name, _who(first), first.path, _who(copy), copy.path, drift)
            kind = "shadowed"
        else:
            message = "{0}: another copy from {1} is at {2}.{3}".format(item.name, _who(copy), copy.path, drift)
            kind = "duplicate"
        out.append(Finding(kind, item.identity or item.name, message, (item.id,), (first.path, copy.path)))
    return out


def manager_findings(ctx: "Context", items: Sequence[InventoryItem]) -> List[Finding]:
    """One tool held by two managers (PATH copies in use, plus requested packages)."""
    by_identity: Dict[str, Dict[str, List[InventoryItem]]] = {}
    for item in items:
        if not item.identity or item.kind not in ("command", "package") or fact(item, "companion"):
            continue
        if item.kind == "command":
            if not item.copies or not item.copies[0].on_path or item.copies[0].owner is None:
                continue
            manager = item.copies[0].owner.manager
        else:
            manager = item.owner.manager if item.owner is not None else ""
        if not manager or (manager in VERSION_MANAGERS and item.kind == "package"):
            continue
        by_identity.setdefault(item.identity, {}).setdefault(manager, []).append(item)
    out: List[Finding] = []
    for identity, managers in sorted(by_identity.items()):
        if len(managers) < 2:
            continue
        names = sorted(managers)
        involved = [i for group in managers.values() for i in group]
        in_use = next((i for i in involved if i.kind == "command"), None)
        message = "{} is installed by {}.".format(identity, " and ".join(names))
        if in_use is not None and in_use.copies:
            message += " The copy in use is {}.".format(in_use.copies[0].path)
        paths = tuple(dict.fromkeys(p for i in involved for p in i.paths[:1]))
        out.append(Finding("duplicate", identity, message, tuple(i.id for i in involved), paths))
    return out


def scope_findings(items: Sequence[InventoryItem]) -> List[Finding]:
    """The same Flatpak installed for the user and for the system."""
    scopes: Dict[str, Dict[str, InventoryItem]] = {}
    for item in items:
        if item.kind == "package" and item.owner is not None and item.owner.manager == "flatpak":
            scopes.setdefault(item.name, {})[item.scope] = item
    out: List[Finding] = []
    for name, held in sorted(scopes.items()):
        if len(held) < 2:
            continue
        rows = list(held.values())
        out.append(Finding("scope-twin", name, "{} is installed both for you and for the whole system.".format(name),
                           tuple(r.id for r in rows), tuple(p for r in rows for p in r.paths[:1])))
    return out


def findings(ctx: "Context", items: Sequence[InventoryItem]) -> List[Finding]:
    out: List[Finding] = []
    for item in items:
        out.extend(command_findings(ctx, item))
    out.extend(manager_findings(ctx, items))
    out.extend(scope_findings(items))
    return out


# ----- inventory -------------------------------------------------------------------------------


def _batches(ctx: "Context", include_slow: bool) -> List[Batch]:
    out = [run_batch(ctx, "cheap")]
    if include_slow:
        out.append(run_batch(ctx, "slow"))
    return out


def inventory(ctx: "Context", include_slow: bool = False) -> Inventory:
    """Managed, package and detected items plus findings, one parallel pass each."""
    holder: Dict[str, List[InventoryItem]] = {}
    failed: Dict[str, str] = {}

    def read_packages() -> None:
        # An exception here would print a thread traceback over the picker.
        try:
            holder["packages"] = package_items(ctx, include_slow)
        except _ERRORS as exc:
            failed["packages"] = str(exc)[:200] or type(exc).__name__

    thread = threading.Thread(target=read_packages, name="aiup-detect-packages", daemon=True)
    thread.start()
    batches = _batches(ctx, include_slow)
    thread.join()
    packages = holder.get("packages", [])
    detected_rows: List[InventoryItem] = []
    seen: Set[str] = set()
    stale: List[str] = []
    errors: Dict[str, str] = dict(failed)
    for batch in batches:
        stale.extend(batch.stale + batch.timed_out)
        errors.update(batch.errors)
        for rows in batch.items.values():
            for row in rows:
                if row.id not in seen:
                    seen.add(row.id)
                    detected_rows.append(row)
    package_ids = {p.id for p in packages}
    managed = [p for p in packages if p.population == "managed"]
    managed += [r for r in detected_rows if r.population == "managed"]
    listed_packages = [p for p in packages if p.population == "package"]
    # Rows a provider inventory already lists are shown there.
    for row in detected_rows:
        if row.population != "package" or row.owner is None:
            continue
        pkg_id = "pkg:" + row.owner.manager + ":" + row.owner.package
        if pkg_id not in package_ids and row.kind != "command":
            listed_packages.append(row)
    detected = [r for r in detected_rows if r.population == "detected"]
    return Inventory(
        managed=tuple(managed), packages=tuple(listed_packages), detected=tuple(detected),
        findings=tuple(findings(ctx, detected_rows + packages)), stale=tuple(dict.fromkeys(stale)),
        errors=errors,
    )


def find_item(inv: Inventory, item_id: str) -> Optional[InventoryItem]:
    for group in (inv.managed, inv.packages, inv.detected):
        for item in group:
            if item.id == item_id:
                return item
    return None


def detected_item(ctx: "Context", item_id: str) -> Optional[InventoryItem]:
    """One linked detection row by id (``det:<source>:<key>``): the cheap pass, then the slow one.

    Reads no package manager inventory, so it is quick enough for one named item.
    """
    for cost in ("cheap", "slow"):
        found = link.find(run_batch(ctx, cost), item_id)
        if found is not None:
            return found
    return None
