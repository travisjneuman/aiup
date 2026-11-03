"""aiup channel [TOOL [CHANNEL|default]] and aiup channel --policy [P]
(macOS: cmd_channel, cmd_channel_policy).

Lists tools with more than one install channel, shows one tool's channels
with the latest release on each, stores a pick or the policy. Picks and the
policy take effect on the next run; nothing is installed here.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Dict, List, Optional

from aiup.commands import _common
from aiup.engine.channels import (
    find_copies, load_choices, policy_names, policy_summary, resolution_map, resolve, set_pick, set_policy,
)
from aiup.engine.latest import read_latest
from aiup.errors import EXIT_OK, AiupError, UsageError

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.cli import Args
    from aiup.engine.context import Context
    from aiup.model import CatalogEntry, Target


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Show or change install channels."""
    ctx, catalog = _common.need(args, ctx)
    if args.policy is not None:
        return _policy(ctx, args.policy)
    words = list(args.words)
    if not words:
        return _list(ctx, catalog)
    tool = catalog.resolve(words[0])
    entry = catalog.get(tool) if tool else None
    if entry is None or not entry.available_on(ctx.os_name):
        raise AiupError("Unknown tool: " + words[0])
    channels = _channels(entry, ctx.os_name)
    if len(channels) < 2:
        choices = load_choices(ctx)
        now = resolve(entry, ctx.os_name, choices.policy, choices.picks, ctx)
        name = now.active.channel if now.active is not None else (channels[0] if channels else "none")
        _say("{} installs from one channel: {}".format(entry.id, name))
        return EXIT_OK
    if len(words) == 1:
        return _detail(ctx, entry)
    try:
        line = set_pick(ctx, entry, words[1])
    except ValueError as exc:
        raise AiupError(str(exc)) from exc
    if not (ctx.dry_run and words[1] == "default"):
        _say(line)
    return EXIT_OK


def _say(text: str) -> None:
    out = _common.stdout()
    out.write(text + "\n")
    out.flush()


def _channels(entry: "CatalogEntry", os_name: str) -> List[str]:
    """Channel names in default order, each once."""
    names: List[str] = []
    for target in entry.targets_for(os_name):
        if target.channel not in names:
            names.append(target.channel)
    return names


def _policy_choices(ctx: "Context") -> str:
    return "|".join(policy_names(ctx))


def _policy(ctx: "Context", policy: str) -> int:
    if not policy:
        current = load_choices(ctx).policy
        _say("Channel policy · " + policy_summary(current))
        _say("Change with: aiup channel --policy {}. A pick made with aiup channel TOOL always wins.".format(
            _policy_choices(ctx)))
        return EXIT_OK
    try:
        line = set_policy(ctx, policy)
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    if not ctx.dry_run:
        _say(line)
    return EXIT_OK


def _list(ctx: "Context", catalog: "Catalog") -> int:
    choices = load_choices(ctx)
    entries = [entry for entry in catalog.available_on(ctx.os_name) if len(_channels(entry, ctx.os_name)) > 1]
    resolutions = resolution_map(ctx, entries, choices)
    lines = ["Channel policy · " + policy_summary(choices.policy),
             "Tools with more than one install channel (in use first, + marks your picks):"]
    for entry in entries:
        res = resolutions.get(entry.id)
        names = _channels(entry, ctx.os_name)
        active = res.active.channel if res is not None and res.active is not None else names[0]
        mark = "+" if entry.id in choices.picks else ""
        others = "".join(" · " + name for name in names if name != active)
        lines.append("  {:<18} {}{}{}".format(entry.id, active, mark, others))
    lines.append("Details and versions: aiup channel TOOL · pick: aiup channel TOOL <channel>|default · "
                 "policy: aiup channel --policy " + _policy_choices(ctx))
    _say("\n".join(lines))
    return EXIT_OK


def _detail(ctx: "Context", entry: "CatalogEntry") -> int:
    choices = load_choices(ctx)
    copies = find_copies(entry, ctx)
    res = resolve(entry, ctx.os_name, choices.policy, choices.picks, ctx, copies=copies)
    active = res.active.channel if res.active is not None else ""
    targets: List["Target"] = []
    seen = set()
    for target in entry.targets_for(ctx.os_name):
        if target.channel not in seen:
            seen.add(target.channel)
            targets.append(target)
    installed: Dict[str, str] = {t.channel: (i.version or "") for t, i in copies}
    ctx.say("  Reading the latest release on each channel…")

    def latest(target: "Target") -> str:
        provider = ctx.provider(target.channel)
        if provider is None or not ctx.provider_available(target.channel):
            return "not available here"
        try:
            found = read_latest(ctx, provider, target, entry.id, installed.get(target.channel, ""))
        except (OSError, ValueError, NotImplementedError, AiupError):
            return "unknown"
        return found.version or "unknown"

    with ThreadPoolExecutor(max_workers=max(1, min(len(targets), 4))) as pool:
        versions = list(pool.map(latest, targets))
    lines = ["{} install channels (* in use, latest release on each):".format(entry.id)]
    for target, version in zip(targets, versions):
        mark = "*" if target.channel == active else " "
        shown = target.package or "official installer"
        lines.append("{} {:<7} {:<34} {}".format(mark, target.channel, _common.clean(shown), _common.clean(version)))
    lines.append("In use because: " + res.reason)
    lines.append("Pick with: aiup channel {0} <channel>, then aiup only {0}".format(entry.id))
    _say("\n".join(lines))
    return EXIT_OK
