"""aiup welcome (macOS: cmd_welcome).

The macOS guide's cleanup card (Homebrew removed-app records) is left out:
``settings cleanup`` has no effect on Linux and Windows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

from aiup.commands import _common
from aiup.errors import EXIT_OK

if TYPE_CHECKING:
    from aiup.cli import Args
    from aiup.engine.context import Context


def guide(os_name: str) -> List[Tuple[str, str]]:
    """The welcome cards for this system."""
    # Matches engine.plan.EXTRAS_MANAGERS: the package extras a plain run updates.
    extras = {"darwin": "the Homebrew packages you installed",
              "linux": "the Homebrew packages you installed",
              "windows": "the Scoop apps you installed"}.get(os_name, "")
    first = "AIUP updates supported installed tools" + (" and " + extras if extras else "") + "."
    if os_name in ("linux", "windows"):
        first += " Run aiup system for your other package managers."
    return [
        ("Welcome to aiup", first + " It does not install the entire catalog."),
        ("1 · Look before changing anything",
         "aiup plan shows intended actions; aiup attention brings problems and next steps together."),
        ("2 · Run maintenance",
         "aiup updates installed tools. Downloads may be needed and app updaters may ask running apps "
         "to close. Save your work first."),
        ("3 · Browse and recover",
         "aiup list browses tools. aiup resume retries unfinished work after interruption. aiup history "
         "and aiup cleanup history show saved results."),
        ("Display and preferences",
         "Use --plain to turn off colors, --show-unchanged for complete results, and aiup settings to "
         "review preferences. Status words remain readable without color."),
        ("What aiup manages",
         "aiup manages catalog tools; detected software is only listed. aiup owners shows ownership and "
         "paths, and aiup coverage shows what aiup supports. Finding two copies never makes aiup remove one."),
    ]


def print_guide(ctx: "Context") -> None:
    """Print the welcome cards to stdout."""
    _common.cards("getting started", guide(ctx.os_name))


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Show the getting-started guide. Changes nothing."""
    ctx, _ = _common.need(args, ctx)
    print_guide(ctx)
    return EXIT_OK
