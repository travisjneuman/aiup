"""aiup explain TOOL (macOS: cmd_explain).

Detection, manager, location, version and next action for one catalog tool.
Linux adds the distro and whether sudo would be needed; Windows adds the
install scope and whether elevation would be needed. Changes nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, TextIO, Tuple

from aiup.commands import _common
from aiup.engine import host
from aiup.engine.channels import channel_label
from aiup.engine.check import check_items
from aiup.engine.privilege import SUDO_PROVIDERS
from aiup.engine.report import category_color
from aiup.errors import EXIT_FAILED, EXIT_OK

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.cli import Args
    from aiup.engine.check import CheckItem
    from aiup.engine.context import Context

NOT_MANAGED = (
    "{} is not in the managed catalog.\n"
    "aiup inventory --refresh shows detected-only apps, installed packages, and PATH commands.\n"
    "Project-local dependencies, temporary npx downloads, and agent skills are not global installed tools.\n"
)


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Explain one tool."""
    ctx, catalog = _common.need(args, ctx)
    word = args.words[0]
    out = _common.stdout()
    if word.startswith(("det:", "pkg:")):
        return _explain_item(ctx, catalog, word, out)
    tool = catalog.resolve(word)
    if tool is None:
        out.write(NOT_MANAGED.format(_common.clean(word)))
        return EXIT_FAILED
    items = check_items(ctx, catalog, [tool])
    if not items:
        out.write(NOT_MANAGED.format(tool))
        return EXIT_FAILED
    _print_tool(ctx, catalog, items[0], out)
    return EXIT_OK


def _print_tool(ctx: "Context", catalog: "Catalog", item: "CheckItem", out: TextIO) -> None:
    job, row = item.job, item.row
    entry = job.entry
    tool = job.tool
    label = entry.label if entry is not None and entry.label else tool
    shown = job.installed
    if shown is None and job.resolution is not None and job.resolution.installed:
        shown = job.resolution.installed[0][1]
    channel = shown.channel if shown is not None else job.channel
    target = job.target
    if shown is not None and job.resolution is not None:
        for copy_target, copy in job.resolution.installed:
            if copy is shown:
                target = copy_target
    state = "installed" if shown is not None else "not installed"
    if entry is not None and not entry.available_on(ctx.os_name):
        state = "not offered on this system"
    fields: List[Tuple[str, str]] = [
        ("State", state),
        ("Version", (shown.version or "unknown") if shown is not None else "not installed"),
        ("Manager", channel_label(channel) if channel else "none found"),
        ("Location", (shown.path or "") if shown is not None and shown.path else "not found"),
    ]
    if target is not None and target.package:
        fields.append((_package_label(target.channel), target.package))
    fields.extend(_system_fields(ctx, channel, shown.scope if shown is not None else ""))
    result = "current (self-updated)" if row.result == "self-updated" else row.result
    fields.append(("Next action", result))
    fields.append(("Reason", _common.clean(row.note)))
    fields.append(("Docs", entry.docs if entry is not None else ""))
    code = category_color(entry.category) if entry is not None else ""
    head = _common.ink(label, code, out) if code else label
    lines = ["", head]
    lines.extend("  {:<12} {}".format(key, _common.clean(value)) for key, value in fields)
    if row.result == "skipped":
        lines.append("")
        lines.append("  aiup only {} offers an explicit manager switch.".format(tool))
    lines.append("")
    lines.append("  Recent run details: aiup history {0} · aiup logs {0}".format(tool))
    out.write("\n".join(lines) + "\n")
    out.flush()


def _package_label(channel: str) -> str:
    if channel in ("vendor", "script"):
        return "Installer"
    return channel_label(channel) + " package"


def _system_fields(ctx: "Context", channel: str, scope: str) -> List[Tuple[str, str]]:
    """Linux: distro and sudo. Windows: install scope and elevation."""
    if ctx.os_name == "linux":
        distro = ctx.distro
        name = distro.name or " ".join(part for part in (distro.id, distro.version_id) if part) or "Linux"
        if channel in SUDO_PROVIDERS and not host.is_root():
            sudo = "yes · " + channel_label(channel) + " changes need sudo"
        else:
            sudo = "no"
        return [("Distro", name), ("Sudo needed", sudo)]
    if ctx.os_name == "windows":
        where = {"machine": "machine (all users)", "system": "machine (all users)", "user": "user"}
        elevated = host.is_elevated(ctx.platform)
        if channel == "choco":
            need = "no · this terminal is elevated" if elevated else "yes · run from an elevated terminal"
        elif channel == "winget":
            need = "maybe · Windows may ask for approval"
        else:
            need = "no"
        return [("Scope", where.get(scope, scope or "unknown")), ("Elevation", need)]
    return []


def _explain_item(ctx: "Context", catalog: "Catalog", item_id: str, out: TextIO) -> int:
    """Detected items and packages: what was found and where (no actions)."""
    from aiup.commands import listing

    if item_id.startswith("pkg:"):
        records = listing.scan_packages(ctx, catalog)
    else:
        records = listing.scan_detected(ctx, cheap_only=False)
    for record in records:
        if record.id != item_id:
            continue
        lines = ["", _common.clean(record.name)]
        fields = [("Version", record.version or "unknown"), ("Found via", record.source),
                  ("Location", record.path or "not found"), ("Owner", record.owner or "unknown")]
        lines.extend("  {:<12} {}".format(key, _common.clean(value)) for key, value in fields)
        lines.append("")
        if item_id.startswith("pkg:"):
            lines.append("  Installed with " + channel_label(record.source) + "; it is not a catalog tool.")
        else:
            lines.append("  Detected only: aiup lists it and does not change it.")
        out.write("\n".join(lines) + "\n")
        out.flush()
        return EXIT_OK
    out.write(NOT_MANAGED.format(_common.clean(item_id)))
    return EXIT_FAILED
