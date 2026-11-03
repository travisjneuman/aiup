"""aiup docs [--print] TOOL, also ``home`` and ``open`` (macOS: cmd_docs).

Opens the tool's docs in the browser, or prints the URL with --print.
Packages (pkg:...) and detected items (det:...) open their docs when known,
else a web search the user asked for on purpose.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Tuple

from aiup.commands import _common
from aiup.errors import EXIT_FAILED, EXIT_OK, AiupError

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.cli import Args
    from aiup.engine.context import Context


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Open or print one docs URL."""
    ctx, catalog = _common.need(args, ctx)
    word = args.words[0]
    if word.startswith(("det:", "pkg:")):
        url, kind = _item_url(ctx, catalog, word)
    else:
        tool = catalog.resolve(word)
        entry = catalog.get(tool) if tool else None
        if entry is None:
            raise AiupError("Unknown tool: " + word)
        url = entry.docs
        if not url:
            raise AiupError("No docs URL for " + entry.id)
        kind = "GitHub" if url.startswith("https://github.com/") else "website"
    if args.print_only:
        out = _common.stdout()
        out.write(url + "\n")
        out.flush()
        return EXIT_OK
    if not ctx.platform.open_url(url):
        ctx.say("aiup: could not open a browser; the address is " + url)
        return EXIT_FAILED
    ctx.say("Opened {}: {}".format(kind, url))
    return EXIT_OK


def _item_url(ctx: "Context", catalog: "Catalog", item_id: str) -> Tuple[str, str]:
    """(URL, kind) for a package or detected item."""
    from aiup.commands import listing
    from aiup.tui.preview import item_url

    if item_id.startswith("pkg:"):
        records = listing.scan_packages(ctx, catalog)
    else:
        records = listing.scan_detected(ctx, cheap_only=False)
    for record in records:
        if record.id == item_id:
            url = item_url(record, ctx.os_name)
            # macOS: a package's page is a "website"; detected items say "guidance/search".
            known = bool(record.docs) and item_id.startswith("pkg:")
            return url, ("website" if known else "guidance/search")
    raise AiupError("Unknown item: " + item_id + "; aiup inventory lists what was found")
