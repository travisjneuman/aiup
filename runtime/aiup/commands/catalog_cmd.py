"""aiup catalog [--json|--markdown] [--platform linux|windows|all]
(macOS: print_catalog_definition).

Definition export only: no scan, no state, no network. The CLI passes no
context for this command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from aiup.catalog.export import render
from aiup.commands import _common
from aiup.errors import EXIT_OK, AiupError

if TYPE_CHECKING:
    from aiup.cli import Args
    from aiup.engine.context import Context


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Write the catalog definition to stdout."""
    if args.catalog is None:
        raise AiupError("aiup catalog could not read the catalog")
    out = _common.stdout()
    out.write(render(args.catalog, args.catalog_format, args.platform))
    out.flush()
    return EXIT_OK
