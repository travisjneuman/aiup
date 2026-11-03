"""Vendor self-updaters (channel ``vendor``, design doc sections 6.3 and 6.6).

Port of the macOS ``update_claude`` pattern: run the tool's own updater
(``claude update``), and when that fails, run the official install script
(``on_fail="next"``). Catalog cells look like ``script:URL;vendor:CMD``; the
loader turns them into ``Target(channel="vendor", update_command=CMD,
install_script=URL)``.

Latest versions come from the same release sources macOS ``live_source_spec``
uses (Claude's release channel, Grok's channel, Amp and Droid version files,
the Cursor installer, npm and PyPI). A tool with no known source reports its
latest as unverified.

This module also finds the old versions some installers keep beside the
active one (Claude Code and Cursor Agent ``versions`` folders, Antigravity
``agy.*.old``) and describes a cleanup action for them, as macOS
``old_tool_versions`` does. Copies in use, the active copy, and anything
changed in the last 30 minutes are kept.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional, Set, Tuple

from aiup.engine.cache import read_json
from aiup.engine.net import clean_version
from aiup.model import Action, Installed, Latest, Ownership, Step, Target
from aiup.providers.base import Provider
from aiup.providers.script import (
    ALL_OSES, aiup_config, batch_args_safe, catalog_entry, empty_action, env_dir, env_of, fetch_text, find_command, first_line,
    home, installed_by_commands, is_windows, local_bin, numeric_part, path_inside, python_executable,
    read_command, real_path, remove_file_step, script_refused_note, script_step,
)

if TYPE_CHECKING:
    from aiup.engine.context import Context

# Installer URL prefix -> the command it installs (macOS *_INSTALL_URL values).
_SCRIPT_COMMANDS: Tuple[Tuple[str, str], ...] = (
    ("https://claude.ai/install.", "claude"),
    ("https://cursor.com/install", "cursor-agent"),
    ("https://antigravity.google/cli/install", "agy"),
    ("https://x.ai/cli/install", "grok"),
    ("https://aider.chat/install", "aider"),
    ("https://ampcode.com/install", "amp"),
    ("https://app.factory.ai/cli", "droid"),
    ("https://opencode.ai/", "opencode"),
    ("https://hermes-agent.nousresearch.com/install", "hermes"),
)


class _Source(NamedTuple):
    kind: str          # claude | grok | text | regex | npm | pypi
    arg: str = ""      # URL or package
    pattern: str = ""  # regex kind
    main: bool = False  # compare only the leading numbers


# Command -> release source (macOS live_source_spec).
_SOURCES: Dict[str, _Source] = {
    "claude": _Source("claude"),
    "grok": _Source("grok"),
    "amp": _Source("text", "https://static.ampcode.com/cli/cli-version.txt", main=True),
    "droid": _Source("text", "https://downloads.factory.ai/factory-cli/LATEST"),
    "cursor-agent": _Source("regex", "https://cursor.com/install", r"downloads\.cursor\.com/lab/([^/]+)/", main=True),
    "opencode": _Source("npm", "@opencode/cli"),
    "aider": _Source("pypi", "aider-chat"),
}

# Commands that update themselves once installed (macOS update_antigravity).
_SELF_UPDATING: Dict[str, str] = {
    "agy": "Antigravity CLI updates itself in the background.",
}

_GROK_CHANNEL = re.compile(r"^[a-z0-9_-]{1,32}$")
_CLAUDE_CHANNELS = ("latest", "stable")
_SETTINGS_MAX_BYTES = 1024 * 1024
_SCRIPT_MAX_BYTES = 4 * 1024 * 1024
_RECENT_SECONDS = 30 * 60
_MAPS_MAX_BYTES = 1024 * 1024

# Deletes each argument. On Windows the path is renamed first: a file or
# folder in use cannot be renamed, so it is kept. Never fails the run.
_DELETE_CODE = (
    "import os, shutil, sys\n"
    "for p in sys.argv[1:]:\n"
    "    try:\n"
    "        if os.name == 'nt':\n"
    "            q = p + '.aiup-delete'\n"
    "            os.replace(p, q)\n"
    "            p = q\n"
    "        if os.path.isdir(p) and not os.path.islink(p):\n"
    "            shutil.rmtree(p)\n"
    "        else:\n"
    "            os.remove(p)\n"
    "        print('removed ' + p)\n"
    "    except OSError as e:\n"
    "        print('kept ' + p + ': ' + str(e.strerror or e))\n"
)


# ----- commands and folders -----------------------------------------------------


def command_of(target: Target) -> str:
    """The command a vendor or script target manages, or ""."""
    if target.update_command:
        words = target.update_command.split()
        return words[0] if words else ""
    url = target.install_script or (target.package if target.channel == "script" else "")
    for prefix, command in _SCRIPT_COMMANDS:
        if url.startswith(prefix):
            return command
    return ""


def known_commands(ctx: "Context", target: Target) -> Tuple[str, ...]:
    """Commands to look for when reading the installed version.

    The installers aiup knows come first, then the catalog entry's commands,
    so a script tool missing from ``_SCRIPT_COMMANDS`` is still found.
    """
    names: List[str] = []
    command = command_of(target)
    if command:
        names.append(command)
    for name in _catalog_commands(ctx, target):
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _catalog_commands(ctx: "Context", target: Target) -> Tuple[str, ...]:
    entry = catalog_entry(ctx, target)
    return tuple(entry.commands) if entry is not None else ()


# Folders other managers own. A command found there is the distro's, Nix's,
# Snap's, Flatpak's, Homebrew's or a Windows manager's copy, never one a
# vendor installer put in place, so aiup does not run its updater or count it.
_SYSTEM_ROOTS = ("/usr/bin", "/usr/sbin", "/bin", "/sbin", "/usr/lib", "/usr/libexec", "/usr/share",
                 "/nix/store", "/snap", "/var/lib/snapd", "/var/lib/flatpak")
_MANAGED_PARTS = ("/flatpak/exports/", "/cellar/", "/windowsapps/", "/scoop/", "/chocolatey/", "/winget/")


def vendor_copy(ctx: "Context", path: str) -> bool:
    """False when ``path`` (or the file it links to) sits in another manager's folders."""
    for candidate in (path, real_path(path)):
        if not is_windows(ctx) and any(path_inside(candidate, root) for root in _SYSTEM_ROOTS):
            return False
        lowered = candidate.replace("\\", "/").lower()
        if any(part in lowered for part in _MANAGED_PARTS):
            return False
    return True


def find_vendor_command(ctx: "Context", command: str) -> Optional[str]:
    """``command`` on PATH or in the vendor folders, skipping other managers' copies."""
    if not command:
        return None
    return find_command(ctx, command, vendor_dirs(ctx), lambda path: vendor_copy(ctx, path))


def vendor_dirs(ctx: "Context") -> Tuple[str, ...]:
    """Folders vendor installers put commands in, searched after PATH."""
    dirs: List[Path] = [local_bin(ctx), home(ctx) / ".opencode" / "bin"]
    if is_windows(ctx):
        from aiup.paths import local_appdata

        dirs.append(local_appdata(env_of(ctx)) / "agy" / "bin")
    return tuple(str(d) for d in dirs)


# ----- release sources ----------------------------------------------------------


def release_latest(ctx: "Context", target: Target, timeout: float) -> Latest:
    """The newest release of a vendor tool from its official source."""
    command = command_of(target)
    source = _SOURCES.get(command)
    if source is None:
        return Latest("", "vendor-endpoint", "no release source known for this installer")
    version = _read_source(ctx, source, timeout)
    if source.main:
        version = numeric_part(version)
    if not version:
        return Latest("", "vendor-endpoint", "the release source did not answer")
    return Latest(version, "vendor-endpoint")


def _read_source(ctx: "Context", source: _Source, timeout: float) -> str:
    if source.kind == "claude":
        url = "https://downloads.claude.ai/claude-code-releases/" + _claude_channel(ctx)
        return clean_version(first_line(fetch_text(ctx, url, timeout) or ""))
    if source.kind == "grok":
        return _grok_latest(ctx, timeout)
    if source.kind == "text":
        return clean_version(first_line(fetch_text(ctx, source.arg, timeout) or ""))
    if source.kind == "regex":
        text = fetch_text(ctx, source.arg, timeout, _SCRIPT_MAX_BYTES) or ""
        found = re.search(source.pattern, text)
        return clean_version(found.group(1)) if found else ""
    if source.kind == "npm":
        return str(ctx.net.npm_latest(source.arg, timeout) or "")
    if source.kind == "pypi":
        return str(ctx.net.pypi_latest(source.arg, timeout) or "")
    return ""


def _claude_channel(ctx: "Context") -> str:
    """``autoUpdatesChannel`` from Claude Code settings: latest (default) or stable."""
    base = env_dir(ctx, "CLAUDE_CONFIG_DIR", home(ctx) / ".claude")
    data = read_json(base / "settings.json", _SETTINGS_MAX_BYTES)
    value = data.get("autoUpdatesChannel") if isinstance(data, dict) else None
    return value if value in _CLAUDE_CHANNELS else "latest"


def _grok_latest(ctx: "Context", timeout: float) -> str:
    channel = env_of(ctx).get("GROK_CHANNEL", "")
    if not channel:
        data = read_json(home(ctx) / ".grok" / "settings_cache.json", _SETTINGS_MAX_BYTES)
        value = data.get("release_channel") if isinstance(data, dict) else None
        channel = value if isinstance(value, str) else ""
    if not _GROK_CHANNEL.match(channel or ""):
        channel = "stable"
    for base in ("https://x.ai/cli/", "https://storage.googleapis.com/grok-build-public-artifacts/cli/"):
        version = clean_version(first_line(fetch_text(ctx, base + channel, timeout) or ""))
        if version:
            return version
    return ""


def installed_vendor(ctx: "Context", target: Target, channel: str) -> Optional[Installed]:
    """The installed copy of a vendor or script tool, versions normalized like its source."""
    found = installed_by_commands(ctx, known_commands(ctx, target), channel, vendor_dirs(ctx),
                                  lambda path: vendor_copy(ctx, path))
    source = _SOURCES.get(command_of(target))
    if found is None or source is None or not source.main:
        return found
    return Installed(numeric_part(found.version), found.path, found.scope, found.channel)


# ----- remove -------------------------------------------------------------------


def remove_command_action(ctx: "Context", target: Target, channel: str) -> Action:
    """Delete a vendor command from a user folder (the installers have no uninstall).

    Only a command in ``~/.local/bin`` or another vendor folder is removed.
    Version folders it points at are left for the cleanup pass.
    """
    commands = known_commands(ctx, target)
    command = commands[0] if commands else ""
    found: Optional[str] = None
    for name in commands:
        found = find_vendor_command(ctx, name)
        if found:
            break
    if not found:
        return empty_action(target, "remove", "Nothing to remove: " + (command or target.package) + " was not found.")
    if not any(path_inside(found, d) for d in vendor_dirs(ctx)):
        return empty_action(target, "remove", "Left " + found + " alone: aiup removes vendor commands only from its user folders.")
    step = remove_file_step(ctx, found, "remove " + found)
    return Action(tool=target.package, op="remove", channel=channel, steps=(step,),
                  note="Settings and version folders stay; aiup remove moves user data to the Trash.")


# ----- old versions ---------------------------------------------------------------


def old_tool_versions(ctx: "Context") -> List[str]:
    """Old copies installers keep that are safe to delete now.

    Kept: the active version, anything changed in the last 30 minutes, and
    anything a running process uses. When the active version cannot be
    worked out, the whole folder is kept.
    """
    now = time.time()
    found: List[str] = []
    share = home(ctx) / ".local" / "share"
    for command in ("claude", "cursor-agent"):
        found.extend(_old_in_versions(ctx, command, share / command / "versions", now))
    found.extend(_old_agy(ctx, now))
    if not found:
        return found
    in_use = _paths_in_use(ctx)
    return [path for path in found if not _used(path, in_use)]


def old_versions_action(ctx: "Context", old: Optional[List[str]] = None) -> Optional[Action]:
    """A cleanup action for ``old_tool_versions``, or None when there is nothing to do.

    Runs only when ``AIUP_CLEANUP_CACHES`` is on. The engine runs it after
    updates (macOS ``post_update_cleanup``). A caller that already has the
    list passes it as ``old``, so the process scan runs once.
    """
    if not aiup_config(ctx).cleanup_caches:
        return None
    old = old_tool_versions(ctx) if old is None else old
    if not old:
        return None
    step = Step(argv=(python_executable(ctx), "-I", "-c", _DELETE_CODE) + tuple(old),
                label="remove " + str(len(old)) + " old tool versions", ok_codes=tuple(range(256)))
    return Action(tool="cleanup", op="remove", channel="vendor", steps=(step,))


def _old_in_versions(ctx: "Context", command: str, root: Path, now: float) -> List[str]:
    if not root.is_dir() or root.is_symlink():
        return []
    active = _active_version(ctx, command, root)
    if not active:
        return []
    old: List[str] = []
    for entry in sorted(root.iterdir()):
        if entry.name == active or entry.name.endswith(".aiup-delete"):
            continue
        if not _recent(entry, now):
            old.append(str(entry))
    return old


def _active_version(ctx: "Context", command: str, root: Path) -> str:
    """Name of the entry under ``root`` the command runs, or ""."""
    suffix = ".exe" if is_windows(ctx) else ""
    link = local_bin(ctx) / (command + suffix)
    resolved = real_path(str(link))
    base = real_path(str(root))
    if path_inside(resolved, base) and os.path.normcase(resolved) != os.path.normcase(base):
        return Path(os.path.relpath(resolved, base)).parts[0]
    if not is_windows(ctx) or not link.is_file():
        return ""
    # Windows copies the active build to local_bin, so ask it which one it is.
    out = read_command(ctx, (str(link), "--version"), max_bytes=64 * 1024) or ""
    names = {entry.name for entry in root.iterdir()}
    for word in re.findall(r"[0-9][0-9A-Za-z._+-]*", out):
        if word in names:
            return word
    return ""


def _old_agy(ctx: "Context", now: float) -> List[str]:
    folders = [local_bin(ctx)]
    if is_windows(ctx):
        from aiup.paths import local_appdata

        folders.append(local_appdata(env_of(ctx)) / "agy" / "bin")
    old: List[str] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for entry in sorted(folder.glob("agy.*.old")):
            if entry.is_file() and not _recent(entry, now):
                old.append(str(entry))
    return old


def _recent(path: Path, now: float) -> bool:
    try:
        return now - path.lstat().st_mtime < _RECENT_SECONDS
    except OSError:
        return True


def _used(path: str, in_use: Set[str]) -> bool:
    return any(path_inside(item, path) for item in in_use)


def _paths_in_use(ctx: "Context") -> Set[str]:
    """Executables and mapped files of running processes (Linux ``/proc``).

    Windows needs no list: a running build cannot be renamed, and the delete
    step renames before deleting. Other systems give an empty set.
    """
    used: Set[str] = set()
    proc = Path("/proc")
    if is_windows(ctx) or not proc.is_dir():
        return used
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            used.add(os.readlink(str(entry / "exe")))
        except OSError:
            pass
        used.update(_mapped_files(entry / "maps"))
    return used


def _mapped_files(maps: Path) -> Set[str]:
    try:
        with open(maps, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(_MAPS_MAX_BYTES)
    except OSError:
        return set()
    files: Set[str] = set()
    for line in text.splitlines():
        parts = line.split(None, 5)
        if len(parts) == 6 and parts[5].startswith("/"):
            files.add(parts[5].replace(" (deleted)", ""))
    return files


# ----- provider -----------------------------------------------------------------


class VendorProvider(Provider):
    """Tools that update themselves, with the install script as the fallback."""

    name = "vendor"
    oses = ALL_OSES
    scope = "user"
    lane = "vendor"
    exclusive = False
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        return True

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        return installed_vendor(ctx, target, self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        return release_latest(ctx, target, timeout)

    def install(self, ctx: "Context", target: Target) -> Action:
        return self._script_only(ctx, target, "install")

    def update(self, ctx: "Context", target: Target) -> Action:
        """``CMD`` (for example ``claude update``), then the install script if it fails."""
        steps: List[Step] = []
        command = command_of(target)
        argv = tuple(target.update_command.split())
        exe = find_vendor_command(ctx, command)
        if exe and command in _SELF_UPDATING:
            return empty_action(target, "update", _SELF_UPDATING[command], result="self-updated")
        if exe and argv and batch_args_safe(exe, argv[1:]):
            steps.append(Step(argv=(exe,) + argv[1:], label=target.update_command, on_fail="next"))
        script = script_step(ctx, target.install_script, "run the installer from " + target.install_script) \
            if target.install_script else None
        if script is not None:
            steps.append(script)
        if not steps:
            if target.install_script:
                return empty_action(target, "update", script_refused_note(ctx, target.install_script))
            return empty_action(target, "update", "No updater found for " + (command or target.package) + ".")
        if steps[-1].on_fail == "next":
            steps[-1] = replace(steps[-1], on_fail="stop")
        return Action(tool=target.package, op="update", channel=self.name, steps=tuple(steps))

    def remove(self, ctx: "Context", target: Target) -> Action:
        return remove_command_action(ctx, target, self.name)

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        return None

    def _script_only(self, ctx: "Context", target: Target, op: str) -> Action:
        if not target.install_script:
            return empty_action(target, op, "The catalog lists no installer for " + target.package + ".")
        step = script_step(ctx, target.install_script, "run the installer from " + target.install_script)
        if step is None:
            return empty_action(target, op, script_refused_note(ctx, target.install_script))
        return Action(tool=target.package, op=op, channel=self.name, steps=(step,))
