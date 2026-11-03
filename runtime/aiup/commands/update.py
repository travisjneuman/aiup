"""aiup, full, core, only, npm-update, resume, retry and group run
(macOS: cmd_update_installed, main_update, run_history resume|retry, group-run).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Sequence

from aiup.commands import _common
from aiup.engine.history import tool_names, tools_to_rerun
from aiup.engine.prefs import IdRules, edit_preferences, group_tools, load_preferences, mark_welcomed
from aiup.engine.run import RunRequest, run as run_update
from aiup.errors import EXIT_OK, AiupError
from aiup.platform import term

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.cli import Args
    from aiup.engine.context import Context

NOTHING_TO_RERUN = "No unfinished or failed tools in saved runs."


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Every update run goes through engine.run with the tools this form names."""
    ctx, catalog = _common.need(args, ctx)
    form = args.subcommand
    if args.invoked == "group":
        tools = _group(ctx, catalog, args.words[0])
        return _run(args, ctx, catalog, tools, explicit=False)
    if form in ("resume", "retry"):
        pairs = tools_to_rerun(ctx, form)
        if not pairs:
            _common.stdout().write(NOTHING_TO_RERUN + "\n")
            return EXIT_OK
        # retry may install a missing tool (macOS NO_INSTALL=0); resume never does.
        return _run(args, ctx, catalog, tool_names(pairs), explicit=not args.no_install)
    if form in ("only", "npm-update"):
        return _run(args, ctx, catalog, _resolve(catalog, args.words), explicit=not args.no_install)
    _welcome_first(args, ctx, catalog)
    # macOS installed_update_tools plus the package extras: only what is found
    # here, read once while planning, so missing tools never show as skipped rows.
    return _run(args, ctx, catalog, (), explicit=False, installed_only=True)


def _run(args: "Args", ctx: "Context", catalog: "Catalog", tools: Sequence[str], explicit: bool,
         installed_only: bool = False) -> int:
    request = RunRequest(tools=tuple(tools), op="update", explicit=explicit,
                         show_unchanged=args.show_unchanged, installed_only=installed_only)
    return run_update(ctx, catalog, request)


def _resolve(catalog: "Catalog", words: Sequence[str]) -> List[str]:
    """Catalog ids for typed names and aliases, in order, without repeats.

    Package ids (``pkg:<manager>:<name>``, from the picker) pass through; the
    plan updates those on this system's package extras managers.
    """
    out: List[str] = []
    for word in words:
        if word.startswith("det:"):
            raise AiupError("aiup only updates catalog tools and packages, not detected items: " + word)
        tool = word if word.startswith("pkg:") else catalog.resolve(word)
        if tool is None:
            raise AiupError("Unknown tool: " + word)
        if tool not in out:
            out.append(tool)
    return out


def _group(ctx: "Context", catalog: "Catalog", name: str) -> List[str]:
    prefs = load_preferences(ctx.dirs, IdRules(set(catalog.ids())))
    tools = group_tools(prefs, name)
    if not tools:
        raise AiupError("Group is empty")
    return tools


def _welcome_first(args: "Args", ctx: "Context", catalog: "Catalog") -> None:
    """The first plain run on a terminal shows the welcome guide once (macOS)."""
    if args.json or not term.is_tty(_common.stdout()):
        return
    ids = IdRules(set(catalog.ids()))
    try:
        if load_preferences(ctx.dirs, ids).welcomed:
            return
    except AiupError:
        return
    from aiup.commands.welcome import print_guide

    print_guide(ctx)
    if ctx.dry_run:
        return
    try:
        edit_preferences(ctx.dirs, ids, mark_welcomed)
    except AiupError:
        pass
