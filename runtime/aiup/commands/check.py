"""aiup check [tools...] and aiup group check NAME (macOS: cmd_check, group-check)."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from aiup.commands import _common
from aiup.engine.check import run_check
from aiup.engine.prefs import IdRules, group_tools, load_preferences
from aiup.errors import AiupError

if TYPE_CHECKING:
    from aiup.cli import Args
    from aiup.engine.context import Context


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Compare installed and latest versions. Changes nothing; 0 when the check ran."""
    ctx, catalog = _common.need(args, ctx)
    tools: List[str] = list(args.words)
    if args.invoked == "group":
        prefs = load_preferences(ctx.dirs, IdRules(set(catalog.ids())))
        tools = group_tools(prefs, args.words[0])
        if not tools:
            raise AiupError("Group is empty")
    return run_check(ctx, catalog, tools, show_all=args.show_unchanged)
