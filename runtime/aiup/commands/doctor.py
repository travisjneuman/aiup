"""aiup doctor [--details] (macOS: cmd_diagnostics, print_doctor).

The short form lists each present catalog tool with its manager and location,
flags several copies on PATH and broken links, and repeats the setup warnings
of the latest run. ``--details`` adds the full inventory plus what this system
needs: Python, fzf, PATH setup, package managers and rights (sudo, AUR helper
and root on Linux; elevation, execution policy, code page and VT on Windows).
Changes nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, TextIO, Tuple

from aiup.commands import _common
from aiup.engine import host
from aiup.engine.channels import channel_label
from aiup.engine.history import print_warnings
from aiup.engine.prefs import IdRules, load_preferences, policy_reason
from aiup.engine.report import category_color
from aiup.errors import EXIT_OK
from aiup.paths import local_bin, npm_bin, npm_prefix
from aiup.version import AIUP_VERSION

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.cli import Args
    from aiup.engine.channels import Copy
    from aiup.engine.context import Context

Copies = Dict[str, Tuple["Copy", ...]]


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Installation diagnostics."""
    ctx, catalog = _common.need(args, ctx)
    ctx.say("  Looking for tools on this computer…")
    copies = _common.installed_copies(ctx, catalog)
    if args.details:
        return _details(ctx, catalog, copies)
    return _summary(ctx, catalog, copies)


def _extra_dirs(ctx: "Context") -> List[str]:
    """Folders aiup installs commands into, searched after PATH."""
    return [str(npm_bin(ctx.os_name, ctx.env)), str(local_bin(ctx.os_name, ctx.env))]


def _summary(ctx: "Context", catalog: "Catalog", copies: Copies) -> int:
    out = _common.stdout()
    prefs = load_preferences(ctx.dirs, IdRules(set(catalog.ids())))
    extra = _extra_dirs(ctx)
    out.write("\naiup · installation diagnostics\n\n")
    for tool, found in copies.items():
        entry = catalog.get(tool)
        target, installed = found[0]
        method = channel_label(target.channel)
        location = installed.path or "n/a"
        name = "{:<20}".format(tool)
        if entry is not None and _common.color_on(out):
            name = "\033[" + category_color(entry.category) + "m" + name + "\033[0m"
        out.write("{} {} · {}\n".format(name, method, location))
        if len({t.channel for t, _ in found}) > 1:
            others = ", ".join(channel_label(t.channel) for t, _ in found[1:])
            out.write("  ! Also installed with {}; aiup channel {} shows which one aiup updates.\n".format(
                others, tool))
        reason = policy_reason(prefs, tool)
        if reason:
            out.write("  " + reason + "\n")
        for command in (entry.commands if entry is not None else ())[:1]:
            out.write(_path_report(ctx, command, extra))
    out.write("\nSetup warnings from the latest run:\n")
    out.flush()
    print_warnings(ctx)
    out.write("No profiles or packages changed. Full inventory: aiup doctor --details\n")
    out.flush()
    return EXIT_OK


def _path_report(ctx: "Context", command: str, extra: List[str]) -> str:
    """macOS PYDIAG: several real copies on PATH, and broken links."""
    lines: List[str] = []
    found = _common.path_copies(ctx, command, extra)
    if len(found) > 1:
        lines.append("  ! Multiple executable installations; PATH selects " + found[0][0])
        lines.extend("    shadowed: " + path for path, _ in found[1:])
        lines.append("    Review aiup explain before choosing one manager or changing PATH.")
    for path in _common.broken_links(ctx, command, extra):
        lines.append("  ! Broken executable link: " + path + "; review its owner before repair.")
    return "".join(line + "\n" for line in lines)


# ----- --details --------------------------------------------------------------------------


def _details(ctx: "Context", catalog: "Catalog", copies: Copies) -> int:
    out = _common.stdout()
    available = [entry.id for entry in catalog.available_on(ctx.os_name)]
    node_path = ctx.platform.which("node") or ""
    npm_path = ctx.platform.which("npm") or ""
    lines = [
        "aiup version: " + AIUP_VERSION,
        "Catalog: " + " ".join(available),
        "Present: " + " ".join(copies),
        "Python: {} · {}".format(sys.version.split()[0], sys.executable or "unknown"),
        "Node path: " + (node_path or "not found"),
        "Node version: " + ((_common.read_version(ctx, [node_path, "--version"]) or "unknown")
                            if node_path else "not found"),
        "npm path: " + (npm_path or "not found"),
        "npm version: " + ((_common.read_version(ctx, [npm_path, "--version"]) or "unknown")
                           if npm_path else "not found"),
        "AIUP npm prefix: " + str(npm_prefix(ctx.os_name, ctx.env)),
        "Local bin: " + str(local_bin(ctx.os_name, ctx.env)),
    ]
    lines.extend(_fzf_lines(ctx))
    lines.extend(_manager_lines(ctx))
    if ctx.os_name == "linux":
        lines.extend(_linux_lines(ctx))
    elif ctx.os_name == "windows":
        lines.extend(_windows_lines(ctx))
    lines.append("")
    lines.append("PATH setup:")
    lines.extend("  " + line for line in _path_setup(ctx))
    _emit(out, lines)

    rows: List[Tuple[str, str, str, str]] = []
    for tool in available:
        found = copies.get(tool, ())
        if found:
            target, installed = found[0]
            rows.append((tool, "present", channel_label(target.channel), installed.version or "unknown"))
        else:
            rows.append((tool, "missing", "n/a", "n/a"))
    lines = ["", "=== Status summary ===", "{:<12} {:<8} {:<18} {}".format("tool", "status", "method", "version")]
    lines.extend("{:<12} {:<8} {:<18} {}".format(*row) for row in rows)
    lines.append("")
    lines.append("=== Detailed doctor output ===")
    extra = _extra_dirs(ctx)
    for tool, found in copies.items():
        entry = catalog.get(tool)
        target, installed = found[0]
        defaults = entry.targets_for(ctx.os_name) if entry is not None else ()
        lines.append("")
        lines.append("[{}] present".format(tool))
        lines.append("  Preferred method: " + (channel_label(defaults[0].channel) if defaults else "n/a"))
        lines.append("  Detected method: " + channel_label(target.channel))
        lines.append("  Version: " + (installed.version or "unknown"))
        lines.append("  Location: " + (installed.path or "n/a"))
        lines.append("  Scope: " + (installed.scope or "unknown"))
        command = entry.commands[0] if entry is not None and entry.commands else ""
        on_path = _common.path_copies(ctx, command, ()) if command else []
        lines.append("  Command path: " + (on_path[0][0] if on_path else "n/a"))
        lines.append("  Resolved path: " + (on_path[0][1] if on_path else "n/a"))
        all_copies = _common.path_copies(ctx, command, extra) if command else []
        lines.append("  Duplicate installs detected: " + ("yes" if len(all_copies) > 1 or len(found) > 1 else "no"))
        for other_target, other in found[1:]:
            lines.append("  Other copy: {} · {}".format(channel_label(other_target.channel), other.path or "n/a"))
    _emit(out, lines)
    return EXIT_OK


def _emit(out: TextIO, lines: List[str]) -> None:
    out.write("".join(_common.clean(line) + "\n" for line in lines))
    out.flush()


def _fzf_lines(ctx: "Context") -> List[str]:
    path = ctx.platform.which("fzf") or ""
    if not path:
        return ["fzf: not found (aiup list needs it)"]
    text = _common.read_version(ctx, [path, "--version"])
    try:
        from aiup.tui.picker import FZF_MINIMUM, FZF_MINIMUM_TEXT, parse_fzf_version
    except ImportError:
        return ["fzf: {} · {}".format(path, text or "unknown version")]
    version = parse_fzf_version(text)
    if version is None:
        verdict = "version unreadable"
    elif version < FZF_MINIMUM:
        verdict = "too old; aiup list needs " + FZF_MINIMUM_TEXT + " or newer"
    else:
        verdict = "ok"
    return ["fzf: {} · {} · {}".format(path, text or "unknown version", verdict)]


def _manager_lines(ctx: "Context") -> List[str]:
    try:
        names = [provider.name for provider in ctx.providers()]
    except (OSError, ValueError):
        names = []
    lines = ["Package managers: " + (", ".join(channel_label(name) for name in names) or "none found")]
    lines.extend(_unusable_lines(ctx, names))
    return lines


def _unusable_lines(ctx: "Context", usable: List[str]) -> List[str]:
    """Managers whose command is on PATH but that cannot be used here, with the provider's reason.

    winget over SSH on Windows Server is the usual case: the command exists
    but cannot start for this session.
    """
    lines: List[str] = []
    for provider in host.all_providers():
        if provider.name in usable or not provider.supports(ctx.os_name):
            continue
        try:
            if not ctx.platform.which(provider.name):
                continue
            reason = provider.unavailable_reason(ctx)
        except (OSError, ValueError, NotImplementedError):
            continue
        if reason:
            lines.append("  {}: found but not usable here: {}".format(channel_label(provider.name), reason))
    return lines


def _linux_lines(ctx: "Context") -> List[str]:
    from aiup.engine.privilege import ROOT_REFUSED

    distro = ctx.distro
    name = distro.name or " ".join(part for part in (distro.id, distro.version_id) if part) or "unknown"
    lines = ["Distro: " + name]
    helper = ""
    if ctx.platform.which("pacman"):
        for candidate in ("paru", "yay"):
            if ctx.platform.which(candidate):
                helper = candidate
                break
        lines.append("AUR helper: " + (helper or "none found") + " · AUR setting: " + ctx.settings.aur)
    sudo = ctx.platform.which("sudo") or ""
    lines.append("sudo: " + (sudo or "not found; system package managers cannot run"))
    if host.is_root():
        lines.append("Running as root: " + ("allowed by AIUP_ALLOW_ROOT" if ctx.config.allow_root else ROOT_REFUSED))
    return lines


def _windows_lines(ctx: "Context") -> List[str]:
    from aiup.platform import term

    elevated = host.is_elevated(ctx.platform)
    lines = ["Elevated terminal: " + ("yes" if elevated else "no")]
    lines.append("Execution policy: " + (_execution_policy(ctx) or "unknown"))
    page = term.original_output_codepage()
    lines.append("Console code page: " + (str(page) if page else "no console"))
    caps = term.caps()
    lines.append("Terminal colors (VT): " + ("on" if caps.vt else "off"))
    return lines


def _execution_policy(ctx: "Context") -> str:
    for shell in ("powershell", "pwsh"):
        path = ctx.platform.which(shell)
        if not path:
            continue
        found = _common.read_version(ctx, [path, "-NoProfile", "-NonInteractive", "-Command", "Get-ExecutionPolicy"])
        if found:
            return found
    return ""


def _path_setup(ctx: "Context") -> List[str]:
    """``aiup_launcher.py setup-path --check`` for the folder that holds the aiup command."""
    launcher = ctx.config.launcher_path
    python = ctx.config.python or sys.executable
    shim = ctx.platform.which("aiup") or ""
    if shim:
        folder = str(Path(shim).parent)
    elif ctx.os_name == "windows":
        return ["the aiup command is not on PATH in this shell"]
    else:
        folder = str(local_bin(ctx.os_name, ctx.env))
    if not launcher or not python:
        return ["unknown: no installed launcher recorded (AIUP_LAUNCHER_PATH)"]
    try:
        result = ctx.run_read([python, "-I", "-B", launcher, "setup-path", "--check", folder],
                              timeout=10.0, max_bytes=64 * 1024)
    except (OSError, ValueError) as exc:
        return ["unknown: " + str(exc)]
    text = (result.stdout or "").strip()
    if result.returncode != 0 or not text:
        detail = (result.stderr or "").strip().splitlines()
        return ["unknown: " + (detail[0] if detail else "the launcher check did not run")]
    return [_common.clean(line) for line in text.splitlines()[:40]]
