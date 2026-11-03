"""Official install scripts (channel ``script``, design doc sections 6.3 and 6.7).

Port of ``run_vendor_installer`` in macos/aiup. The engine downloads the script
named in ``Step.download`` (HTTPS only, redirects only to HTTPS, 2 retries,
300 second limit, a fresh private folder, refused when empty, removed
afterwards) and puts the file path where the argv says ``{file}``. This module
only describes the step:

- Linux and macOS: a fixed ``sh`` dispatcher reads the script's first line and
  runs it with ``bash`` when that line names bash, with ``sh`` when it names
  sh, and refuses anything else. The script path is passed as an argument, so
  nothing from the download ever becomes shell source.
- Windows: ``.ps1`` only, run as ``powershell.exe -NoProfile -NonInteractive
  -ExecutionPolicy Bypass -File <file>``. The bypass applies to that one
  process and the one file aiup just downloaded. aiup never pipes a remote
  string into ``iex``.

Some installers need fixed arguments, listed in ``_SCRIPT_ARGS`` by the exact
installer URL from the catalog. They go after the script path on both
platforms (macOS passes the same flags after ``--`` to
``run_vendor_installer``).

The second half of the module holds small helpers every cross-platform
provider in this package shares (command lookup, bounded reads, text fetches,
version tokens, the Windows batch-file argument rule).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from aiup import paths
from aiup.config import Config, load_config
from aiup.model import Action, Installed, Latest, Ownership, Step, Target
from aiup.providers.base import Provider

if TYPE_CHECKING:
    from aiup.engine.context import Context
    from aiup.model import CatalogEntry

ALL_OSES = frozenset({"linux", "windows", "darwin"})

# Placeholder the engine replaces with the downloaded script's path.
FILE_PLACEHOLDER = "{file}"

# Read limits for the small commands these providers start.
READ_TIMEOUT = 10.0
READ_MAX_BYTES = 1024 * 1024

# cmd.exe interprets these in a batch file's arguments (CVE-2024-27980 class).
# platform/proc.resolve_argv refuses them too; checking here lets a provider
# explain the refusal at plan time instead of failing during the run.
_BATCH_UNSAFE = frozenset('"%&|<>^!\r\n')

_VERSION_TOKEN = re.compile(r"(?<![0-9A-Za-z.])v?(\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.+-]*)?)")
_NUMERIC_PART = re.compile(r"\d+(?:\.\d+)*")

# Fixed arguments for some installers, keyed by the exact installer URL in the
# catalog (catalog/platforms.tsv). The script cell grammar has no argument
# field, so they live here, next to the step that runs the script. A new key
# must match the catalog URL character for character.
# - Hermes: its installers download Chromium unless told not to. aiup never
#   installs a browser runtime, so they get the vendor's opt-out flag, which
#   Hermes records so "hermes update" keeps it. "hermes pm install chromium"
#   adds the browser back.
_SCRIPT_ARGS: Mapping[str, Tuple[str, ...]] = {
    "https://hermes-agent.nousresearch.com/install.sh": ("--skip-browser",),
    "https://hermes-agent.nousresearch.com/install.ps1": ("-SkipBrowser",),
}

# Fixed dispatcher for Linux and macOS install scripts. "$1" is the downloaded
# file; any further arguments are the installer's own (``_SCRIPT_ARGS``) and
# are passed on unchanged. Only exact bash and sh first lines are accepted.
_SH_DISPATCH = (
    'line=$(head -n 1 -- "$1")\n'
    "cr=$(printf '\\r')\n"
    'line=${line%"$cr"}\n'
    'case "$line" in\n'
    "  '#!/bin/bash'|'#!/bin/bash '*|'#!/usr/bin/bash'|'#!/usr/bin/bash '*|"
    "'#!/usr/bin/env bash'|'#!/usr/bin/env bash '*) exec bash -- \"$@\" ;;\n"
    "  '#!/bin/sh'|'#!/bin/sh '*|'#!/usr/bin/sh'|'#!/usr/bin/sh '*|"
    "'#!/usr/bin/env sh'|'#!/usr/bin/env sh '*) exec sh -- \"$@\" ;;\n"
    "esac\n"
    "echo 'aiup: refusing an installer whose first line names neither bash nor sh' >&2\n"
    "exit 1\n"
)


# ----- shared helpers ---------------------------------------------------------


def os_name(ctx: "Context") -> str:
    """``linux``, ``windows`` or ``darwin`` for the running platform."""
    name = getattr(ctx, "os_name", "") or getattr(ctx.platform, "name", "") or ""
    if name:
        return str(name)
    if sys.platform == "win32":
        return "windows"
    return "darwin" if sys.platform == "darwin" else "linux"


def env_of(ctx: "Context") -> Mapping[str, str]:
    """The environment this run reads paths from (``ctx.env``, else ``os.environ``)."""
    value = getattr(ctx, "env", None)
    return value if isinstance(value, Mapping) else os.environ


def env_dir(ctx: "Context", name: str, fallback: Path) -> Path:
    """An absolute folder from an environment variable, else ``fallback``."""
    value = env_of(ctx).get(name, "")
    return Path(value) if value and os.path.isabs(value) else fallback


def is_windows(ctx: "Context") -> bool:
    """True on Windows."""
    return os_name(ctx) == "windows"


def which(ctx: "Context", command: str, path: Optional[str] = None) -> Optional[str]:
    """Absolute path of ``command`` on PATH (PATHEXT on Windows), or None."""
    try:
        return ctx.platform.which(command, path)
    except (OSError, ValueError):
        return None


def read_command(ctx: "Context", argv: Sequence[str], timeout: float = READ_TIMEOUT,
                 max_bytes: int = READ_MAX_BYTES, env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Run a read-only command and return its stdout, or None when it failed.

    Goes through ``ctx.run_read`` (no terminal, stdin closed, never sudo,
    output capped). ``env`` is passed only when given, for the few reads that
    need a different PATH.
    """
    try:
        result: Any = ctx.run_read(argv, timeout, max_bytes, env=env or None)
    except (OSError, ValueError):
        return None
    if not getattr(result, "ok", False):
        return None
    out = getattr(result, "stdout", "")
    return out if isinstance(out, str) else None


def fetch_text(ctx: "Context", url: str, timeout: float, max_bytes: int = READ_MAX_BYTES) -> Optional[str]:
    """GET an HTTPS text document through ``ctx.net``; None on any failure."""
    if not url.startswith("https://"):
        return None
    try:
        result = ctx.net.fetch(url, max_bytes=max_bytes, timeout=timeout)
    except Exception:  # noqa: BLE001  Net.fetch never raises; this guards a stand-in net
        return None
    if not getattr(result, "ok", False):
        return None
    return result.text()


def first_line(text: str) -> str:
    """The first non-blank line, stripped."""
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def version_token(text: str) -> str:
    """The first version-looking token in ``--version`` output, without a leading v."""
    for line in text.splitlines():
        found = _VERSION_TOKEN.search(line)
        if found:
            return found.group(1)
    return ""


def numeric_part(version: str) -> str:
    """Leading dotted numbers of a version (for builds tagged with commit hashes)."""
    found = _NUMERIC_PART.match(version.strip().lstrip("v"))
    return found.group(0) if found else ""


def batch_args_safe(executable: str, args: Iterable[str]) -> bool:
    """False when a Windows batch file would get characters cmd.exe interprets."""
    if not executable.lower().endswith((".cmd", ".bat")):
        return True
    return not any(ch in _BATCH_UNSAFE for arg in args for ch in arg)


def real_path(path: str) -> str:
    """``os.path.realpath`` that never raises."""
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return path


def path_inside(path: str, root: str) -> bool:
    """True when ``path`` is ``root`` or below it (case-insensitive on Windows)."""
    if not path or not root:
        return False
    a = os.path.normcase(os.path.normpath(path))
    b = os.path.normcase(os.path.normpath(root))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def aiup_config(ctx: "Context") -> Config:
    """The run's ``Config`` (from the context when it carries one)."""
    for name in ("config", "settings"):
        value = getattr(ctx, name, None)
        if isinstance(value, Config):
            return value
    return load_config()


def home(ctx: "Context") -> Path:
    """The user's home folder."""
    return paths.home_dir(os_name(ctx), env_of(ctx))


def local_bin(ctx: "Context") -> Path:
    """``AIUP_LOCAL_BIN`` or ``~/.local/bin``."""
    return paths.local_bin(os_name(ctx), env_of(ctx))


def python_executable(ctx: Optional["Context"] = None) -> str:
    """The interpreter running aiup (``AIUP_PYTHON`` when the shim set it)."""
    value = aiup_config(ctx).python if ctx is not None else os.environ.get("AIUP_PYTHON", "")
    return value if value and os.path.isabs(value) else sys.executable


def remove_file_step(ctx: "Context", path: str, label: str) -> Step:
    """A step that deletes one file with aiup's own Python.

    Used where a channel has no uninstall command (``go install`` binaries,
    vendor commands in ``~/.local/bin``). The path is an argument, never code.
    """
    code = "import os, sys; p = sys.argv[1]; os.path.lexists(p) and os.remove(p)"
    return Step(argv=(python_executable(ctx), "-I", "-c", code, path), label=label)


def path_setup_step(ctx: "Context", directory: str) -> Optional[Step]:
    """``aiup_launcher.py setup-path DIR`` when DIR is not on PATH yet (section 6.4).

    None when ``AIUP_NO_MODIFY_PATH=1``, when no launcher is known (a
    checkout run), or when the folder is already on PATH. A failure here never
    fails the install, so every exit code is accepted; the launcher prints its
    own reason.
    """
    config = aiup_config(ctx)
    if config.no_modify_path:
        return None
    launcher = config.launcher_path
    if not launcher or not os.path.isabs(launcher):
        return None
    on_path = env_of(ctx).get("PATH", "").split(os.pathsep)
    if any(path_inside(entry, directory) and path_inside(directory, entry) for entry in on_path if entry):
        return None
    return Step(
        argv=(python_executable(ctx), "-I", "-B", launcher, "setup-path", directory),
        label="add " + directory + " to PATH",
        ok_codes=tuple(range(256)),
    )


def installed_by_commands(ctx: "Context", commands: Sequence[str], channel: str,
                          extra_dirs: Sequence[str] = (),
                          accept: Optional[Callable[[str], bool]] = None) -> Optional[Installed]:
    """Find the first of ``commands`` and read its ``--version``.

    For channels whose copies are plain commands (``script``, ``vendor``).
    ``extra_dirs`` are searched after PATH (``~/.local/bin`` is where vendor
    installers put commands even before PATH is set up). ``accept`` can turn
    down a found path (a copy another manager owns).
    """
    for command in commands:
        found = find_command(ctx, command, extra_dirs, accept)
        if not found:
            continue
        out = read_command(ctx, (found, "--version"), timeout=READ_TIMEOUT, max_bytes=64 * 1024)
        return Installed(version=version_token(out or ""), path=found, scope="user", channel=channel)
    return None


def find_command(ctx: "Context", command: str, extra_dirs: Sequence[str] = (),
                 accept: Optional[Callable[[str], bool]] = None) -> Optional[str]:
    """``command`` on PATH, then in ``extra_dirs``; the first path ``accept`` allows."""
    found = which(ctx, command)
    if found and (accept is None or accept(found)):
        return found
    found = _find_in(ctx, command, extra_dirs)
    if found and (accept is None or accept(found)):
        return found
    return None


def _find_in(ctx: "Context", command: str, dirs: Sequence[str]) -> Optional[str]:
    joined = os.pathsep.join(d for d in dirs if d)
    return which(ctx, command, joined) if joined else None


def catalog_entry(ctx: "Context", target: Target) -> Optional["CatalogEntry"]:
    """The catalog entry that lists ``target`` for this OS, or None."""
    catalog = getattr(ctx, "catalog", None)
    if catalog is None:
        return None
    label = os_name(ctx)
    key = (target.channel, target.package)
    for entry in catalog.available_on(label):
        if any((t.channel, t.package) == key for t in entry.targets_for(label)):
            return entry
    return None


def tool_id(ctx: "Context", target: Target) -> str:
    """The catalog id for ``target`` (for commands in notes), else its package."""
    entry = catalog_entry(ctx, target)
    return entry.id if entry is not None else target.package


def empty_action(target: Target, op: str, note: str, result: str = "") -> Action:
    """An action with nothing to run and the reason why. It never counts as done.

    ``result`` is how the engine reports it (skipped, deferred, self-updated,
    failed); "" means failed for an install and skipped otherwise. The engine
    fills in the real tool id; ``tool`` here is the package.
    """
    return Action(tool=target.package, op=op, channel=target.channel, steps=(), note=note, result=result)


# ----- script steps -------------------------------------------------------------


def script_url_ok(os_label: str, url: str) -> bool:
    """HTTPS with a host; on Windows the path must end in ``.ps1`` (section 5.7)."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or any(ord(ch) < 33 for ch in url):
        return False
    return os_label != "windows" or parts.path.lower().endswith(".ps1")


def windows_powershell(ctx: "Context") -> str:
    """Windows PowerShell 5.1 from the system folder, never a PATH lookalike."""
    env = env_of(ctx)
    root = env.get("SystemRoot", "") or env.get("windir", "") or r"C:\Windows"
    candidate = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if os.path.isfile(candidate):
        return candidate
    return which(ctx, "powershell.exe") or candidate


def script_step(ctx: "Context", url: str, label: str, on_fail: str = "stop") -> Optional[Step]:
    """The download-then-run step for one install script, or None when refused.

    The script's own arguments from ``_SCRIPT_ARGS`` follow the file path.
    """
    os_label = os_name(ctx)
    if not script_url_ok(os_label, url):
        return None
    extra = _SCRIPT_ARGS.get(url, ())
    if os_label == "windows":
        argv: Tuple[str, ...] = (
            windows_powershell(ctx), "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", FILE_PLACEHOLDER,
        ) + extra
    else:
        argv = ("sh", "-c", _SH_DISPATCH, "aiup-installer", FILE_PLACEHOLDER) + extra
    return Step(argv=argv, label=label, download=url, timeout=None, on_fail=on_fail)


def script_refused_note(ctx: "Context", url: str) -> str:
    """Why ``script_step`` refused a URL."""
    if is_windows(ctx):
        return "Refusing installer " + url + ": Windows installers must be HTTPS .ps1 scripts."
    return "Refusing installer " + url + ": installers must be HTTPS."


class ScriptProvider(Provider):
    """Tools installed by their official install script, with no separate updater."""

    name = "script"
    oses = ALL_OSES
    scope = "user"
    lane = "vendor"
    exclusive = False
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        if is_windows(ctx):
            return os.path.isfile(windows_powershell(ctx))
        return which(ctx, "sh") is not None

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        # A script target names only a URL. vendor.known_commands maps the
        # installers aiup knows to their commands and adds the catalog
        # entry's commands for the rest.
        from aiup.providers.vendor import installed_vendor

        return installed_vendor(ctx, target, self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        from aiup.providers.vendor import release_latest

        return release_latest(ctx, target, timeout)

    def install(self, ctx: "Context", target: Target) -> Action:
        return self._run_script(ctx, target, "install")

    def update(self, ctx: "Context", target: Target) -> Action:
        return self._run_script(ctx, target, "update")

    def remove(self, ctx: "Context", target: Target) -> Action:
        from aiup.providers.vendor import remove_command_action

        return remove_command_action(ctx, target, self.name)

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        return None

    def _run_script(self, ctx: "Context", target: Target, op: str) -> Action:
        url = target.install_script or target.package
        step = script_step(ctx, url, "run the installer from " + url)
        if step is None:
            return empty_action(target, op, script_refused_note(ctx, url))
        return Action(tool=target.package, op=op, channel=self.name, steps=(step,))
