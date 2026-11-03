"""aiup attention, owners, duplicates (macOS: cmd_overview).

Cards built from local inventory and the latest saved run. Discovered
commands are never executed and nothing is removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

from aiup.commands import _common
from aiup.engine.history import latest_rows
from aiup.errors import EXIT_OK

if TYPE_CHECKING:
    from aiup.cli import Args
    from aiup.engine.context import Context

DEFAULT_GUIDANCE = "Maintain through the original installer or app updater; AIUP has no reviewed generic updater."
ALWAYS_CHECKED = ("node", "npm", "npx", "python3", "uv", "codex")
NEEDS_REVIEW = ("failed", "unverified", "pending", "deferred", "cancelled", "downgraded")
RESUMABLE = ("failed", "pending", "deferred", "cancelled")
LAUNCHER_LIMIT = 65536
PATH_PREFIX = "det:path:"

Card = Tuple[str, str]


@dataclass(frozen=True)
class Item:
    """One detected item, as the cards show it."""

    id: str
    name: str
    owner: str
    path: str
    guidance: str


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Show one overview: ``attention``, ``owners`` or ``duplicates``."""
    ctx, _ = _common.need(args, ctx)
    view = args.command
    items = _items(ctx)
    if view == "owners":
        _common.cards("owners", _owners(items))
        return EXIT_OK
    duplicates = _duplicates(ctx, items)
    if view == "duplicates":
        _common.cards("duplicates", _duplicate_cards(items, duplicates))
        return EXIT_OK
    _common.cards("attention", _attention(ctx, items, duplicates))
    return EXIT_OK


def _items(ctx: "Context") -> List[Item]:
    out: List[Item] = []
    for raw in _common.detected_items(ctx):
        ident = str(getattr(raw, "id", "") or "")
        if not ident:
            continue
        paths = tuple(getattr(raw, "paths", ()) or ())
        source = str(getattr(raw, "source", "") or "")
        out.append(Item(
            id=ident,
            name=str(getattr(raw, "name", "") or ident),
            owner=_common.owner_text(getattr(raw, "owner", None), source),
            path=str(paths[0]) if paths else "",
            guidance=str(getattr(raw, "guidance", "") or "") or DEFAULT_GUIDANCE,
        ))
    return out


def _owners(items: List[Item]) -> List[Card]:
    cards: List[Card] = [("Installation ownership · local evidence",
                          "These observations describe current files; they do not authorize changing managers. "
                          "App receipts can outlive apps.")]
    cards.extend((item.name + " · " + item.owner, item.path + " · " + item.guidance) for item in items)
    return cards


def _duplicates(ctx: "Context", items: List[Item]) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """Command names with more than one distinct executable on PATH."""
    names = {item.id[len(PATH_PREFIX):] for item in items if item.id.startswith(PATH_PREFIX)}
    names.update(ALWAYS_CHECKED)
    out: List[Tuple[str, List[Tuple[str, str]]]] = []
    for name in sorted(names):
        if not name or "/" in name or "\\" in name:
            continue
        found = _common.path_copies(ctx, name)
        if len(found) > 1:
            out.append((name, found))
    return out


def _launchers(items: List[Item]) -> List[Tuple[str, str]]:
    """Small text files among the detected paths (scripts that may name a copy directly)."""
    out: List[Tuple[str, str]] = []
    for item in items:
        if not item.path:
            continue
        candidate = Path(item.path)
        try:
            if not candidate.is_file() or candidate.stat().st_size > LAUNCHER_LIMIT:
                continue
            with open(candidate, "rb") as handle:
                raw = handle.read(LAUNCHER_LIMIT + 1)
            if b"\x00" in raw:
                continue
            out.append((item.id, raw.decode("utf-8")))
        except (OSError, UnicodeError):
            continue
    return out


def _duplicate_cards(items: List[Item], duplicates: List[Tuple[str, List[Tuple[str, str]]]]) -> List[Card]:
    cards: List[Card] = [("Review copies · no automatic removal",
                          "The first executable in PATH is used by this shell. Direct paths and other apps can "
                          "still use another copy; a duplicate is not proof it is unused.")]
    launchers = _launchers(items) if duplicates else []
    for name, paths in duplicates:
        others = paths[1:]
        cards.append((name + " · active: " + paths[0][0],
                      "Other copies: " + "; ".join(p + " → " + t for p, t in others)))
        users = [ident for ident, text in launchers if any(p in text or t in text for p, t in others)]
        cards.append(("Next step",
                      "Review aiup owners before removing a copy. Direct path references in "
                      + str(len(launchers)) + " small text launchers: " + (", ".join(users[:8]) or "none found")
                      + ". Other apps and project dependencies are not proven unused."))
    if not duplicates:
        cards.append(("No distinct executable copies found",
                      "Aliases pointing at the same file count as one installation."))
    return cards


def _attention(ctx: "Context", items: List[Item], duplicates: List[Tuple[str, List[Tuple[str, str]]]]) -> List[Card]:
    cards: List[Card] = []
    try:
        rows = latest_rows(ctx)
    except (OSError, ValueError):
        rows = []
    for row in rows:
        result = str(row.get("result", "") or "")
        if result not in NEEDS_REVIEW and not row.get("warning"):
            continue
        tool = str(row.get("tool", "") or "")
        note = str(row.get("note", "") or "")
        if not note and result == "downgraded":
            note = ("Version went from " + str(row.get("before", "")) + " to " + str(row.get("after", ""))
                    + "; check that nothing you use needs the newer one")
        tail = "; use aiup resume when the run is no longer active." if result in RESUMABLE else ""
        cards.append((tool + " · " + (result or "needs review"), note + " · aiup logs " + tool + tail))
    if duplicates:
        cards.append((str(len(duplicates)) + " commands have multiple installations",
                      "Review active paths and other copies: aiup duplicates. Nothing is removed automatically."))
    unowned = [item for item in items if item.id.startswith(PATH_PREFIX)
               and (item.owner in ("PATH executable", "path", "unknown", "Unknown") or "no reviewed" in item.guidance)]
    if unowned:
        cards.append((str(len(unowned)) + " commands need an ownership review",
                      "aiup owners explains known evidence; aiup coverage --all shows support gaps."))
    if not cards:
        cards.append(("No recorded issues need attention",
                      "This is based on local inventory and the latest saved run. aiup check can verify "
                      "available updates."))
    return cards
