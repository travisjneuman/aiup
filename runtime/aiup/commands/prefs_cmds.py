"""aiup preferences, exclude, include, hold, unhold, group set/remove, settings
(macOS: the ``preferences`` helper and the settings branch of main).

Edits print "Preferences saved."; with --dry-run they print the change as
macOS does ("DRY-RUN: preferences exclude TOOL") and write nothing. ``group
run`` and ``group check`` go to the update and check modules.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from aiup.commands import _common
from aiup.engine import prefs as prefs_engine
from aiup.engine.prefs import IdRules, Preferences, edit_preferences, load_preferences
from aiup.errors import EXIT_OK, UsageError

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.cli import Args
    from aiup.engine.context import Context

Change = Callable[[Preferences], None]


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Show or change preferences."""
    ctx, catalog = _common.need(args, ctx)
    ids = IdRules(set(catalog.ids()))
    command = args.command
    words = list(args.words)
    if command == "preferences":
        prefs = load_preferences(ctx.dirs, ids)
        out = _common.stdout()
        out.write(json.dumps(prefs.to_json(), indent=2) + "\n")
        out.flush()
        return EXIT_OK
    if command == "settings" and not args.subcommand:
        _show_settings(ctx, ids)
        return EXIT_OK
    action, shown, change = _edit(args, ctx, catalog, ids, words)
    if ctx.dry_run:
        out = _common.stdout()
        out.write("DRY-RUN: preferences " + " ".join([action] + shown) + "\n")
        out.flush()
        return EXIT_OK
    edit_preferences(ctx.dirs, ids, change)
    out = _common.stdout()
    out.write("Preferences saved.\n")
    out.flush()
    return EXIT_OK


def _edit(args: "Args", ctx: "Context", catalog: "Catalog", ids: IdRules,
          words: List[str]) -> Tuple[str, List[str], Change]:
    """(macOS action name, its arguments, the change) for one edit command."""
    command = args.command
    if command in ("exclude", "include", "unhold"):
        tool = _canonical(catalog, words[0])
        edit = {"exclude": prefs_engine.exclude, "include": prefs_engine.include,
                "unhold": prefs_engine.unhold}[command]
        return command, [tool], lambda p: edit(p, ids, tool)
    if command == "hold":
        tool, until = _canonical(catalog, words[0]), words[1]
        return "hold", [tool, until], lambda p: prefs_engine.hold(p, ids, tool, until)
    if command == "group":
        if args.subcommand == "set":
            name = words[0] if words else ""
            tools = [_canonical(catalog, word) for word in words[1:]]
            return "group-set", [name] + tools, lambda p: prefs_engine.set_group(p, ids, name, tools)
        if args.subcommand == "remove":
            name = words[0] if words else ""
            return "group-remove", [name], lambda p: prefs_engine.remove_group(p, name)
        raise UsageError("expected: aiup group set NAME TOOLS… | run NAME | check NAME | remove NAME")
    if command == "settings":
        key, value = args.subcommand, words[0]
        return key, [value], lambda p: prefs_engine.set_setting(p, key, value, ctx.os_name)
    raise UsageError("aiup " + command + " is not a preferences command")


def _canonical(catalog: "Catalog", word: str) -> str:
    """A catalog alias becomes its id; anything else (pkg:<manager>:<name>) stays as typed."""
    return catalog.resolve(word) or word


def _show_settings(ctx: "Context", ids: IdRules) -> None:
    """macOS ``aiup settings`` cards, with the system and AUR settings added."""
    prefs = load_preferences(ctx.dirs, ids)
    cards = [
        ("Cleanup mode · " + prefs.cleanup,
         "Change with: aiup settings cleanup auto|review. It is stored so exports stay portable; "
         "it has no effect on this system."),
        ("System package managers · " + prefs.system,
         "Change with: aiup settings system report|ask|auto. report: a plain run lists system package updates "
         "and changes nothing. ask: a plain run asks first in a terminal. auto: a plain run applies them. "
         "aiup system runs a full system upgrade."),
    ]
    if ctx.os_name == "linux":
        cards.append(("AUR packages · " + prefs.aur,
                      "Change with: aiup settings aur review|trust. review: the AUR helper shows each build "
                      "script before it builds. trust: updates of AUR packages you already have skip those "
                      "prompts. New AUR installs always ask."))
    cards.append(("Tool exclusions, holds and groups",
                  "View all values: aiup preferences. Exclude a package with its pkg:<manager>:<name> ID."))
    _common.cards("settings", cards)
