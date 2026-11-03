"""Inventory items: what detection found, where it lives, and who owns it.

``InventoryItem`` carries the section 8.2 fields first, then the extra fields
from the research record (identity, scope, evidence, confidence and so on),
all with defaults so a source only fills in what it knows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

from aiup.model import Ownership

POPULATIONS = ("managed", "package", "detected")
# How sure detection is about an item's owner. Only "exact" and "strong"
# items get one-key update and remove.
CONFIDENCES = ("exact", "strong", "heuristic")
ACTIONABLE = frozenset(("exact", "strong"))

SCHEMA = 1


@dataclass(frozen=True)
class Owner(Ownership):
    """An :class:`Ownership` that prints as its owner's name.

    ``label`` names owners that are not provider channels ("Claude Code
    installer", "mise", "Programs and Features"). ``evidence`` says why
    detection believes it ("pacman -Qo", "package.json ancestry").
    """

    label: str = ""
    evidence: str = ""

    def __str__(self) -> str:
        return self.label or self.manager


@dataclass(frozen=True)
class Copy:
    """One file that answers to an item's name, in PATH order."""

    path: str
    resolved: str
    owner: Optional[Owner] = None
    version: str = ""
    on_path: bool = True


@dataclass(frozen=True)
class InventoryItem:
    """One thing found on this computer (design section 8.2)."""

    id: str                          # catalog id, pkg:<manager>:<name>, or det:<source>:<key>
    name: str
    version: str
    population: str                  # "managed" | "package" | "detected"
    source: str                      # detection source name
    paths: Tuple[str, ...]
    owner: Optional[Owner]
    kind: str = "command"            # command, app, uninstall-entry, runtime, model, image, integration, extension, distro
    identity: str = ""               # canonical tool identity for duplicate grouping
    scope: str = "user"              # "user" | "system" | "container"
    confidence: str = "heuristic"    # "exact" | "strong" | "heuristic"
    evidence: str = ""
    tool: str = ""                   # catalog id when the item matches a catalog entry
    manual: bool = False             # aiup has no update step for it; see guidance
    self_updates: bool = False
    needs_admin: bool = False
    docs: str = ""
    guidance: str = ""
    description: str = ""
    copies: Tuple[Copy, ...] = ()
    remove_argv: Tuple[str, ...] = ()        # registry entries: the uninstaller, parsed
    quiet_remove_argv: Tuple[str, ...] = ()
    stale: bool = False              # served from an old cache after the source timed out
    facts: Tuple[Tuple[str, str], ...] = ()  # source details: install folder, publisher, key


def det_id(source: str, key: str) -> str:
    """``det:<source>:<key>``."""
    return "det:" + source + ":" + key


def fact(item: InventoryItem, name: str) -> str:
    """One value from ``item.facts``, or ""."""
    for key, value in item.facts:
        if key == name:
            return value
    return ""


# ----- JSON (per-source cache files) -------------------------------------------


def _owner_json(owner: Optional[Ownership]) -> Optional[Dict[str, str]]:
    if owner is None:
        return None
    return {
        "manager": owner.manager, "package": owner.package, "confidence": owner.confidence,
        "label": str(getattr(owner, "label", "") or ""),
        "evidence": str(getattr(owner, "evidence", "") or ""),
    }


def _owner_from(data: object) -> Optional[Owner]:
    if not isinstance(data, dict):
        return None
    manager = data.get("manager")
    package = data.get("package")
    if not isinstance(manager, str) or not isinstance(package, str) or not manager:
        return None
    return Owner(
        manager=manager, package=package, confidence=_text(data, "confidence") or "prefix",
        label=_text(data, "label"), evidence=_text(data, "evidence"),
    )


def _text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else ""


def _strings(value: object) -> Tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(v for v in value if isinstance(v, str))


def item_to_json(item: InventoryItem) -> Dict[str, object]:
    """A JSON-safe dict for the cache."""
    return {
        "id": item.id, "name": item.name, "version": item.version,
        "population": item.population, "source": item.source, "paths": list(item.paths),
        "owner": _owner_json(item.owner), "kind": item.kind, "identity": item.identity,
        "scope": item.scope, "confidence": item.confidence, "evidence": item.evidence,
        "tool": item.tool, "manual": item.manual, "self_updates": item.self_updates,
        "needs_admin": item.needs_admin, "docs": item.docs, "guidance": item.guidance,
        "description": item.description,
        "copies": [
            {"path": c.path, "resolved": c.resolved, "owner": _owner_json(c.owner),
             "version": c.version, "on_path": c.on_path}
            for c in item.copies
        ],
        "remove_argv": list(item.remove_argv), "quiet_remove_argv": list(item.quiet_remove_argv),
        "facts": [[k, v] for k, v in item.facts],
    }


def item_from_json(data: object) -> Optional[InventoryItem]:
    """The item a cache row describes, or None when the row is damaged."""
    if not isinstance(data, dict):
        return None
    item_id = _text(data, "id")
    name = _text(data, "name")
    population = _text(data, "population")
    if not item_id or not name or population not in POPULATIONS:
        return None
    copies: List[Copy] = []
    raw_copies = data.get("copies")
    for raw in raw_copies if isinstance(raw_copies, list) else ():
        if isinstance(raw, dict) and _text(raw, "path"):
            copies.append(Copy(
                path=_text(raw, "path"), resolved=_text(raw, "resolved") or _text(raw, "path"),
                owner=_owner_from(raw.get("owner")), version=_text(raw, "version"),
                on_path=bool(raw.get("on_path", True)),
            ))
    facts: List[Tuple[str, str]] = []
    raw_facts = data.get("facts")
    for pair in raw_facts if isinstance(raw_facts, list) else ():
        if isinstance(pair, list) and len(pair) == 2 and all(isinstance(p, str) for p in pair):
            facts.append((pair[0], pair[1]))
    confidence = _text(data, "confidence")
    return InventoryItem(
        id=item_id, name=name, version=_text(data, "version"), population=population,
        source=_text(data, "source"), paths=_strings(data.get("paths")),
        owner=_owner_from(data.get("owner")), kind=_text(data, "kind") or "command",
        identity=_text(data, "identity"), scope=_text(data, "scope") or "user",
        confidence=confidence if confidence in CONFIDENCES else "heuristic",
        evidence=_text(data, "evidence"), tool=_text(data, "tool"),
        manual=bool(data.get("manual", False)), self_updates=bool(data.get("self_updates", False)),
        needs_admin=bool(data.get("needs_admin", False)), docs=_text(data, "docs"),
        guidance=_text(data, "guidance"), description=_text(data, "description"),
        copies=tuple(copies), remove_argv=_strings(data.get("remove_argv")),
        quiet_remove_argv=_strings(data.get("quiet_remove_argv")), facts=tuple(facts),
    )
