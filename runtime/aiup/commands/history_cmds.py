"""aiup history [TOOL], aiup logs [TOOL], aiup cleanup history
(macOS: run_history history|logs|cleanup).

``logs`` goes through the pager on a terminal, as macOS does. ``cleanup``
takes only ``history`` here; the CLI refuses the macOS cleanup actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from aiup.commands import _common
from aiup.engine.history import print_cleanup_history, print_history, print_logs

if TYPE_CHECKING:
    from aiup.cli import Args
    from aiup.engine.context import Context


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Show saved runs, a run log, or recorded cleanups."""
    ctx, _ = _common.need(args, ctx)
    _common.stdout()
    tool = _tool(args)
    if args.command == "logs":
        return _common.paged(ctx, lambda: print_logs(ctx, tool))
    if args.command == "cleanup":
        return print_cleanup_history(ctx)
    return print_history(ctx, tool)


def _tool(args: "Args") -> str:
    """The catalog id for a typed name; other names stay as typed."""
    if not args.words:
        return ""
    word = args.words[0]
    catalog = args.catalog
    return (catalog.resolve(word) if catalog is not None else None) or word
