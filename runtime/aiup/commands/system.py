"""aiup system (Linux and Windows; new, section 7.3).

Runs each available system package manager's full upgrade after one [y/N]
question (none with ``settings system auto``). engine.run.run_system does
the work, including the refusals and the message when no manager is found.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from aiup.commands import _common
from aiup.engine.run import run_system

if TYPE_CHECKING:
    from aiup.cli import Args
    from aiup.engine.context import Context


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Full system upgrade."""
    ctx, _ = _common.need(args, ctx)
    return run_system(ctx)
