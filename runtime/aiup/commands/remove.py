"""aiup remove [tools...] and aiup uninstall (macOS: cmd_remove_named,
cmd_remove_interactive, remove_user_data_preview, move_tool_user_data_to_trash).

Each named tool is uninstalled with its own manager (engine.run.remove_tools).
Its known user data (catalog/tool-meta.tsv) is listed first, confirmed once,
and then moved to the Trash (Linux) or Recycle Bin (Windows), never deleted.

Package ids (``pkg:<manager>:<name>``) are removed with that manager. Detected
ids (``det:<source>:<key>``) use the action detection ties them to
(``detect.action_for``): the provider that owns them, else the app's own
uninstaller from its Uninstall entry. Neither has user data aiup moves.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

from aiup.catalog.userdata import expand_data_path
from aiup.commands import _common
from aiup.engine.channels import channel_label
from aiup.engine.run import remove_tools, run_actions
from aiup.errors import EXIT_FAILED, EXIT_INTERRUPTED, EXIT_OK, AiupError
from aiup.model import Action, Target
from aiup.platform.base import TrashError

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.cli import Args
    from aiup.engine.context import Context

SIZE_FILE_LIMIT = 200000   # files counted per folder before the size reads as "large"
ITEM_PREFIXES = ("pkg:", "det:")
_DECLINED = -1             # the user data question was answered no: nothing else runs


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Uninstall the named tools, or pick them in the list on a terminal."""
    ctx, catalog = _common.need(args, ctx)
    if not args.words:
        return _pick(args, ctx, catalog)
    items = [word for word in args.words if word.startswith(ITEM_PREFIXES)]
    tools = _resolve(catalog, [word for word in args.words if not word.startswith(ITEM_PREFIXES)])
    code = _remove_tools(ctx, catalog, tools) if tools else EXIT_OK
    if code == _DECLINED:
        return EXIT_FAILED
    if code == EXIT_INTERRUPTED or not items:
        return code
    actions, ok = _item_actions(ctx, list(dict.fromkeys(items)))
    status = run_actions(ctx, actions)
    if status == EXIT_INTERRUPTED:
        return EXIT_INTERRUPTED
    return EXIT_FAILED if status != EXIT_OK or not ok or code != EXIT_OK else EXIT_OK


def _remove_tools(ctx: "Context", catalog: "Catalog", tools: Sequence[str]) -> int:
    """Catalog tools: user data preview and question, the uninstall, then the data move."""
    data = {tool: user_data_paths(ctx, catalog, tool) for tool in tools}
    if any(data.values()):
        _preview(ctx, data)
        if not ctx.dry_run:
            question = "Uninstall {} and move that data to the {}? [y/N] ".format(
                " ".join(tools), _common.trash_name(ctx.os_name))
            if not ctx.interactive or not _common.ask(question):
                ctx.say("Uninstall cancelled; nothing changed")
                return _DECLINED
    code = EXIT_OK
    for tool in tools:
        status = remove_tools(ctx, catalog, [tool])
        if status == EXIT_INTERRUPTED:
            return EXIT_INTERRUPTED
        if status != EXIT_OK:
            # The data stays when the uninstall did not finish.
            code = EXIT_FAILED
            continue
        if not _move_data(ctx, data[tool]):
            code = EXIT_FAILED
    return code


def _item_actions(ctx: "Context", ids: Sequence[str]) -> Tuple[List[Tuple[str, Action]], bool]:
    """(label, remove action) for each package or detected id, and False when one could not be planned."""
    actions: List[Tuple[str, Action]] = []
    ok = True
    for item_id in ids:
        planned = _package_action(ctx, item_id) if item_id.startswith("pkg:") else _detected_action(ctx, item_id)
        if planned is None:
            ok = False
        elif planned[1] is not None:
            actions.append((planned[0], planned[1]))
    return actions, ok


def _package_action(ctx: "Context", item_id: str) -> Optional[Tuple[str, Optional[Action]]]:
    """``pkg:<manager>:<name>``: the manager's remove action; (name, None) when it is not installed."""
    _, manager, name = (item_id.split(":", 2) + ["", ""])[:3]
    shown = _common.clean(name or item_id)
    if not manager or not name:
        ctx.say("  " + _common.clean(item_id) + ": not a package id (pkg:<manager>:<name>)")
        return None
    provider = ctx.provider(manager) if ctx.provider_available(manager) else None
    if provider is None:
        ctx.say("  " + shown + ": " + channel_label(manager) + " is not available here")
        return None
    target = Target(channel=manager, package=name)
    try:
        if provider.installed(ctx, target) is None:
            ctx.say("  " + shown + ": not installed with " + channel_label(manager))
            return shown, None
        return shown, provider.remove(ctx, target)
    except (NotImplementedError, OSError, ValueError) as exc:
        ctx.say("  " + shown + ": could not remove with " + channel_label(manager) + ": "
                + _common.clean(str(exc))[:160])
        return None


def _detected_action(ctx: "Context", item_id: str) -> Optional[Tuple[str, Optional[Action]]]:
    """``det:<source>:<key>``: the action detection ties the item to, or None with the reason shown."""
    from aiup.detect import action_for, detected_item

    item = detected_item(ctx, item_id)
    if item is None:
        ctx.say("  " + _common.clean(item_id) + ": not found on this computer")
        return None
    shown = _common.clean(item.name or item_id)
    try:
        action = action_for(item, "remove", ctx)
    except (NotImplementedError, OSError, ValueError, AiupError) as exc:
        ctx.say("  " + shown + ": could not plan the removal: " + _common.clean(str(exc))[:160])
        return None
    if action is None:
        reason = _common.clean(item.guidance) or "aiup has no verified way to remove it."
        ctx.say("  " + shown + ": not removed. " + reason)
        return None
    return shown, action


def _pick(args: "Args", ctx: "Context", catalog: "Catalog") -> int:
    """macOS cmd_remove_interactive: the picker, once, in remove mode."""
    if not ctx.interactive:
        raise AiupError("aiup remove needs a terminal to pick tools. Name them instead: aiup remove TOOL")
    from aiup.commands import listing
    from aiup.tui.picker import PickerUnavailable

    try:
        return listing.browse(args, ctx, catalog, mode="remove", loop=False)
    except PickerUnavailable as exc:
        ctx.say("aiup: " + exc.message)
        return EXIT_FAILED


def _resolve(catalog: "Catalog", words: Sequence[str]) -> List[str]:
    out: List[str] = []
    for word in words:
        tool = catalog.resolve(word)
        if tool is None:
            raise AiupError("Unknown tool: " + word)
        if tool not in out:
            out.append(tool)
    return out


# ----- user data ----------------------------------------------------------------------


def user_data_paths(ctx: "Context", catalog: "Catalog", tool: str) -> List[Path]:
    """Existing user data paths for one tool; a path inside one already listed is skipped."""
    entry = catalog.get(tool)
    if entry is None:
        return []
    raws = entry.user_data.get(ctx.os_name, ()) if entry.user_data else ()
    found: List[Path] = []
    for raw in raws:
        path = expand_data_path(ctx.os_name, raw, ctx.env)
        if path is None or not (path.exists() or path.is_symlink()):
            continue
        if any(path == seen or _inside(seen, path) for seen in found):
            continue
        found = [seen for seen in found if not _inside(path, seen)]
        found.append(path)
    return found


def _inside(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return child != parent


def _preview(ctx: "Context", data: Dict[str, List[Path]]) -> None:
    out = _common.stdout()
    out.write("Removing also moves this data (settings, sessions, history) to the {}:\n".format(
        _common.trash_name(ctx.os_name)))
    for tool, paths in data.items():
        for path in paths:
            out.write("  {}\t{}\t{}\n".format(tool, _size(path), path))
    where = "the Recycle Bin" if ctx.os_name == "windows" else "the Trash"
    out.write("It stays recoverable from {} until you empty it.\n".format(where))
    out.flush()


def _size(path: Path) -> str:
    """A short size like ``du -sh`` prints ("4.0K", "12M"), without following links."""
    try:
        if path.is_symlink() or path.is_file():
            return _human(path.lstat().st_size)
    except OSError:
        return "?"
    total = 0
    count = 0
    for root, dirs, files in os.walk(str(path), followlinks=False):
        for name in files:
            count += 1
            if count > SIZE_FILE_LIMIT:
                return "large"
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return _human(total)


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "K", "M", "G"):
        if value < 1024 or unit == "G":
            if unit == "B":
                return str(int(value)) + "B"
            return ("{:.1f}{}" if value < 10 else "{:.0f}{}").format(value, unit)
        value /= 1024
    return str(size)


def _move_data(ctx: "Context", paths: Sequence[Path]) -> bool:
    """Move each path to the Trash or Recycle Bin (macOS move_to_trash)."""
    ok = True
    where = _common.trash_name(ctx.os_name)
    for path in paths:
        if not (path.exists() or path.is_symlink()):
            continue
        if ctx.dry_run:
            ctx.say("DRY-RUN: move to {}: {}".format(where, path))
            continue
        try:
            ctx.platform.trash(str(path))
        except (TrashError, OSError) as exc:
            detail = str(exc).strip()
            ctx.say("aiup: Could not move to {}: {}{}".format(where, path, " (" + detail + ")" if detail else ""))
            ok = False
            continue
        ctx.say("Moved to {}: {}".format(where, path))
    return ok
