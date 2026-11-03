"""User-level cache cleanup after an update run (port of macOS ``post_update_cleanup``).

Only user-level caches (npm, uv, pip, the pnpm store) and the old versions
vendor installers leave behind (``providers.vendor.old_versions_action``).
aiup never cleans
system caches (no ``paccache``, no ``apt-get clean``). Each cache is left
alone while its manager is running, so a command in another terminal never
loses files it is using (uv then only prunes unused entries). Nothing runs
with ``AIUP_CLEANUP_CACHES=0``, in a dry run or after Ctrl-C. Output goes to
the run log; the only line on screen is the freed total.
"""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Sequence, Tuple

from aiup.errors import AiupError

from aiup.engine import host
from aiup.engine.cache import Stamp

if TYPE_CHECKING:
    from aiup.engine.context import Context

PNPM_STAMP = "pnpm-store-prune.stamp"
PNPM_EVERY_SECONDS = 86400.0
CLEANUP_TIMEOUT = 600.0
MIN_WORTH_BYTES = 1024 * 1024
_KIB = 1024


@dataclass
class CleanupPlan:
    """What one cleanup will run and which folders it measures."""

    commands: List[Tuple[str, Tuple[str, ...], Optional[str]]]   # (label, argv, cwd)
    measured: List[Path]
    npm_logs: Optional[Path] = None
    pnpm_due: bool = False
    old_versions: bool = False


def enabled(ctx: "Context", interrupted: bool) -> bool:
    """False with AIUP_CLEANUP_CACHES=0, a dry run, or after Ctrl-C."""
    return bool(ctx.config.cleanup_caches) and not ctx.dry_run and not interrupted


def cache_dir(text: str) -> Optional[Path]:
    """A cache folder that is safe to clean, else None (macOS ``cleanup_cache_dir``).

    It must be an absolute, existing, real folder, and not the home folder or
    a filesystem root.
    """
    value = text.strip().splitlines()[0].strip() if text.strip() else ""
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        return None
    try:
        info = os.lstat(str(path))
    except OSError:
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        return None
    resolved = path.resolve()
    if resolved == Path.home().resolve() or resolved == Path(resolved.anchor):
        return None
    return path


def folder_bytes(paths: Sequence[Path]) -> int:
    """Disk use of the folders, without following links. Missing folders count 0."""
    total = 0
    for root in paths:
        total += _walk_bytes(root)
    return total


def _bytes_of(info: os.stat_result) -> int:
    blocks = getattr(info, "st_blocks", None)
    return blocks * 512 if blocks is not None else info.st_size


def _walk_bytes(root: Path) -> int:
    try:
        top = os.lstat(str(root))
    except OSError:
        return 0
    if not stat.S_ISDIR(top.st_mode):
        return _bytes_of(top)
    total = 0
    stack = [str(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        stack.append(entry.path)
                    else:
                        total += _bytes_of(info)
        except OSError:
            continue
    return total


def _read(ctx: "Context", argv: Sequence[str], cwd: Optional[str] = None) -> str:
    result = ctx.run_read(argv, timeout=ctx.provider_timeout(), max_bytes=65536, cwd=cwd)
    return result.stdout if result.ok else ""


def _running(ctx: "Context", names: Sequence[str]) -> bool:
    return host.process_running(ctx.platform, names)


def plan_cleanup(ctx: "Context") -> CleanupPlan:
    """Find the caches this computer has and what to run for each."""
    plan = CleanupPlan(commands=[], measured=[])
    which: Callable[[str], Optional[str]] = lambda name: host.which(ctx.platform, name)
    if which("npm") and not _running(ctx, ("npm", "npx", "npm-cli.js")):
        folder = cache_dir(_read(ctx, ("npm", "config", "get", "cache")))
        if folder is not None:
            plan.measured += [folder / "_cacache", folder / "_logs"]
            plan.commands.append(("npm cache clean", ("npm", "cache", "clean", "--force", "--loglevel=error"), None))
            plan.npm_logs = folder / "_logs"
    if which("uv"):
        folder = cache_dir(_read(ctx, ("uv", "cache", "dir")))
        if folder is not None:
            plan.measured.append(folder)
            if _running(ctx, ("uv", "uvx")):
                plan.commands.append(("uv cache prune", ("uv", "cache", "prune"), None))
            else:
                plan.commands.append(("uv cache clean", ("uv", "cache", "clean"), None))
    pip = which("pip3") or which("pip")
    if pip and not _running(ctx, ("pip", "pip3")):
        folder = cache_dir(_read(ctx, (pip, "cache", "dir")))
        if folder is not None:
            plan.measured.append(folder)
            plan.commands.append(("pip cache purge", (pip, "cache", "purge"), None))
    _add_old_versions(ctx, plan)
    if _pnpm_due(ctx):
        plan.pnpm_due = True
        plan.commands.append(("pnpm store prune", ("pnpm", "store", "prune"), str(Path.home())))
    return plan


def _add_old_versions(ctx: "Context", plan: CleanupPlan) -> None:
    """Old vendor versions (Claude Code, Cursor Agent ...), when the vendor provider has any."""
    try:
        from aiup.providers import vendor

        old = vendor.old_tool_versions(ctx)
        action = vendor.old_versions_action(ctx, old) if old else None
    except (ImportError, OSError, ValueError, NotImplementedError, AiupError):
        return
    if action is None or not action.steps:
        return
    plan.measured.extend(Path(path) for path in old)
    plan.old_versions = True
    for step in action.steps:
        plan.commands.append((step.label, tuple(step.argv), None))


def _pnpm_due(ctx: "Context") -> bool:
    """macOS ``pnpm_store_due``: once a day, never while pnpm runs, only with a store."""
    stamps = Stamp(ctx.dirs.state)
    if not host.which(ctx.platform, "pnpm") or stamps.fresh(PNPM_STAMP, PNPM_EVERY_SECONDS):
        return False
    if _running(ctx, ("pnpm", "pnpm.cjs", "pnpm.js")):
        return False
    # From the home folder, like the prune, so a project's .npmrc in the
    # current folder cannot point the answer at another store.
    if cache_dir(_read(ctx, ("pnpm", "store", "path"), str(Path.home()))) is None:
        # No store yet: note the day so the next runs do not ask pnpm again.
        stamps.touch(PNPM_STAMP)
        return False
    return True


def run_cleanup(ctx: "Context", interrupted: Callable[[], bool]) -> int:
    """Clean the caches and return the bytes freed. Output goes to the log.

    Raises KeyboardInterrupt when Ctrl-C stopped a cleanup command, so the
    caller can mark the run interrupted (exit 130). Other errors are logged.
    """
    if not enabled(ctx, interrupted()) or ctx.log.path is None:
        return 0
    try:
        plan = plan_cleanup(ctx)
    except (OSError, RuntimeError, AiupError):
        return 0
    if not plan.commands:
        return 0
    before = folder_bytes(plan.measured)
    if before <= MIN_WORTH_BYTES and not plan.pnpm_due and not plan.old_versions:
        return 0
    ctx.log.write("========== CLEANUP START ==========")
    for label, argv, cwd in plan.commands:
        if interrupted():
            break
        try:
            stopped = _run(ctx, label, argv, cwd)
        except (OSError, AiupError) as exc:
            ctx.log.write("FAILED: " + label + ": " + str(exc)[:200])
            continue
        if stopped:
            # Ctrl-C: run_step stopped the command and swallowed the interrupt.
            ctx.log.write("========== CLEANUP INTERRUPTED ==========")
            raise KeyboardInterrupt
        if label == "npm cache clean" and plan.npm_logs is not None:
            _drop_npm_logs(plan.npm_logs)
        if label == "pnpm store prune":
            Stamp(ctx.dirs.state).touch(PNPM_STAMP)
    after = folder_bytes(plan.measured)
    freed = max(0, before - after)
    ctx.log.write("========== CLEANUP DONE: freed {} KB ==========".format(freed // _KIB))
    return freed


def _run(ctx: "Context", label: str, argv: Tuple[str, ...], cwd: Optional[str]) -> bool:
    """Run one cleanup command. True when Ctrl-C stopped it."""
    path = ctx.log.path
    if path is None:
        return False
    ctx.log.write("START: " + label)
    result = host.run_step(argv, path, echo=sys.stderr if ctx.verbose else None,
                           timeout=CLEANUP_TIMEOUT, env=None, interactive=False, cancel=None,
                           on_tick=None, grace=5.0, cwd=cwd)
    if result.interrupted:
        ctx.log.write("INTERRUPTED: " + label)
        return True
    ctx.log.write(("DONE: " if result.ok() else "FAILED: ") + label)
    return False


def _drop_npm_logs(folder: Path) -> None:
    """npm keeps its debug logs after ``cache clean``; remove the ``*.log`` files."""
    try:
        if folder.is_symlink() or not folder.is_dir():
            return
        for item in folder.iterdir():
            if item.suffix == ".log" and item.is_file() and not item.is_symlink():
                item.unlink()
    except OSError:
        pass


def freed_line(freed: int) -> str:
    """``  Freed 120 MB of caches and old versions ...`` or "" below 1 MB."""
    kib = freed // _KIB
    if kib < 1024:
        return ""
    size = "{:.1f} GB".format(kib / 1048576) if kib >= 1048576 else "{} MB".format(kib // 1024)
    return "  Freed " + size + " of caches and old versions · AIUP_CLEANUP_CACHES=0 keeps them"
