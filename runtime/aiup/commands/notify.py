"""aiup notify [--always] (macOS: cmd_notify, standard_path_setup).

Checks for updates and shows a desktop notification when some are ready. It
installs nothing. The list it last told you about is kept in
``notify-last.txt`` in the state folder; the next run notifies again only
when that list changes, unless ``--always`` is given.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

from aiup.commands import _common
from aiup.engine.check import check_items, update_rows
from aiup.errors import EXIT_OK, AiupError
from aiup.paths import home_dir, local_bin, npm_bin

if TYPE_CHECKING:
    from aiup.cli import Args
    from aiup.engine.context import Context

LAST_FILE = "notify-last.txt"
_VERSION = re.compile(r"\d+\.\d+[^\s]*")


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Check, print one line, and notify when the set of ready updates changed."""
    ctx, catalog = _common.need(args, ctx)
    _widen_path(ctx)
    try:
        items = check_items(ctx, catalog, ())
    except (AiupError, OSError) as exc:
        sys.stderr.write("aiup: " + _common.clean(str(exc)) + "\n")
        return 1
    ready: List[Tuple[str, str, str]] = sorted(
        (row.tool, _version(row.before), _version(row.after)) for row in update_rows(items))
    last = ctx.dirs.state / LAST_FILE
    out = _common.stdout()
    if not ready:
        out.write("aiup: everything is up to date.\n")
        out.flush()
        _forget(last)
        return EXIT_OK
    key = " ".join(tool + "=" + new for tool, _, new in ready)
    names = [tool for tool, _, _ in ready]
    count = str(len(ready)) + (" update" if len(ready) == 1 else " updates") + " ready"
    tail = "Run aiup to install " + ("it." if len(ready) == 1 else "them.")
    shown = ", ".join(names[:3]) + (" and " + str(len(names) - 3) + " more" if len(names) > 3 else "")
    body = shown + ". " + tail
    line = "aiup: " + count + ": " + ", ".join(t + " " + o + " -> " + n for t, o, n in ready) + ". " + tail
    out.write(_common.clean(line) + "\n")
    out.flush()
    if not args.always and _remembered(last) == key:
        return EXIT_OK
    # Versions come from tool output: no control characters reach the notifier.
    if not ctx.platform.notify("aiup: " + count, _common.clean(body)):
        sys.stderr.write("aiup: could not show a notification (no notification service answered)\n")
        return EXIT_OK
    _remember(last, key)
    return EXIT_OK


def _version(text: str) -> str:
    match = _VERSION.search(text or "")
    return match.group(0) if match else (text or "").strip()


def _remembered(last: Path) -> str:
    """The key saved by the last notification, or "" (a symbolic link is ignored)."""
    try:
        if last.is_symlink() or not last.is_file():
            return ""
        with open(last, "r", encoding="utf-8") as handle:
            return handle.read(65536).strip()
    except (OSError, UnicodeError):
        return ""


def _remember(last: Path, key: str) -> None:
    try:
        if last.is_symlink():
            return
        last.parent.mkdir(parents=True, exist_ok=True)
        with open(last, "w", encoding="utf-8") as handle:
            handle.write(key + "\n")
    except OSError:
        pass


def _forget(last: Path) -> None:
    try:
        if last.is_file() and not last.is_symlink():
            last.unlink()
    except OSError:
        pass


def _widen_path(ctx: "Context") -> None:
    """Scheduled jobs start with a short PATH; add the usual tool folders that exist (section 9.6)."""
    env = ctx.env
    home = home_dir(ctx.os_name, env)
    folders: List[Path] = []
    if ctx.os_name == "windows":
        local = env.get("LOCALAPPDATA", "")
        if local:
            folders.append(Path(local) / "Programs" / "aiup" / "bin")
        folders.append(home / ".local" / "bin")
        folders.append(local_bin(ctx.os_name, env))
        folders.append(npm_bin(ctx.os_name, env))
        if local:
            folders.append(Path(local) / "Microsoft" / "WinGet" / "Links")
        scoop = env.get("SCOOP", "")
        folders.append((Path(scoop) if scoop else home / "scoop") / "shims")
    else:
        folders.append(local_bin(ctx.os_name, env))
        folders.append(npm_bin(ctx.os_name, env))
        folders.append(home / ".cargo" / "bin")
        gobin = env.get("GOBIN", "")
        gopath = env.get("GOPATH", "").split(os.pathsep)[0] if env.get("GOPATH") else ""
        folders.append(Path(gobin) if gobin else (Path(gopath) / "bin" if gopath else home / "go" / "bin"))
        folders.append(Path("/home/linuxbrew/.linuxbrew/bin"))
        folders.append(home / ".linuxbrew" / "bin")
    current = os.environ.get("PATH", "")
    have = {os.path.normcase(entry) for entry in current.split(os.pathsep) if entry}
    added: List[str] = []
    for folder in folders:
        text = str(folder)
        key = os.path.normcase(text)
        if key in have or not folder.is_absolute() or not folder.is_dir():
            continue
        have.add(key)
        added.append(text)
    if not added:
        return
    widened = os.pathsep.join(added + ([current] if current else []))
    os.environ["PATH"] = widened
    if env is not os.environ:
        try:
            env["PATH"] = widened  # type: ignore[index]
        except TypeError:
            pass
