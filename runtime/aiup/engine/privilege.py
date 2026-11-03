"""Privilege decisions for every step (design doc section 7).

Rules this module enforces:

- aiup never stores, pipes or caches a password. sudo always reads it from
  the terminal itself; aiup only keeps the progress line still while it asks.
- sudo is used only for the system package managers (pacman, the AUR helper's
  pacman calls, apt, dnf, zypper, snap) and never on Windows. A user-level
  manager asking for sudo is refused. A ``helper-sudo`` step (paru, yay) runs
  as the user and calls sudo itself; aiup never wraps it, but it follows the
  same rules as a sudo step.
- Outside an explicit action (``only``, ``install``, ``remove``, ``system``,
  the picker), a privileged step follows ``settings system``: ``report`` never
  runs it, ``ask`` needs one yes in a terminal, ``auto`` runs it.
- Without a terminal sudo runs as ``sudo -n``: it works only when sudo needs
  no password, and a password request becomes ``deferred``.
- Windows never elevates silently: a UAC prompt only from a desktop
  terminal, an elevated-only step only when aiup already runs elevated.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Sequence, Tuple

from aiup.model import Step

from aiup.engine import host

if TYPE_CHECKING:
    from aiup.engine.context import Context
    from aiup.providers.base import Provider

SUDO_PROVIDERS = frozenset({"pacman", "aur", "apt", "dnf", "zypper", "snap"})
PRIVILEGED = frozenset({"sudo", "helper-sudo", "polkit", "uac-possible", "elevated-required"})

SUDO_NEEDS_TERMINAL = "needs sudo; run aiup in a terminal"
NEEDS_TERMINAL = "needs a terminal; run aiup in a terminal"
WINDOWS_APPROVAL = "needs Windows approval; run aiup in a desktop terminal"
ROOT_REFUSED = ("aiup runs as your user and uses sudo only for system package managers. "
                "Run it without sudo, or set AIUP_ALLOW_ROOT=1 to run it as root anyway.")
WINDOWS_ELEVATED_NOTE = ("aiup is running elevated. User-level tools install for this account; "
                         "a normal terminal is enough for everyday runs.")

# sudo -n prints one of these when it would have to ask.
_SUDO_PASSWORD_LINES = ("a password is required", "a terminal is required")


@dataclass(frozen=True)
class PrivilegeDecision:
    """Whether a step may run, what goes in front of its argv, and why not."""

    allowed: bool
    wrap: Tuple[str, ...]      # ("sudo",), ("sudo", "-n") or ()
    defer_note: str            # set when allowed is False


def _allow(wrap: Tuple[str, ...] = ()) -> PrivilegeDecision:
    return PrivilegeDecision(True, wrap, "")


def _defer(note: str) -> PrivilegeDecision:
    return PrivilegeDecision(False, (), note)


def report_note(tool: str) -> str:
    """What ``settings system report`` (or no terminal under ``ask``) says."""
    return "update with: aiup system or aiup only " + (tool or "TOOL")


def decide(step: Step, provider: "Provider", op: str, explicit: bool, ctx: "Context",
           tool: str = "") -> PrivilegeDecision:
    """May ``step`` run now, and how (section 7.5).

    ``explicit`` is True for ``only``, ``install``, ``remove``, ``system`` and
    picker actions. ``tool`` only fills in the deferred note.
    """
    if step.privilege == "none":
        if step.interactive and not ctx.interactive:
            return _defer(NEEDS_TERMINAL)
        return _allow()
    if step.privilege not in PRIVILEGED:
        return _defer("refused: unknown privilege " + step.privilege)
    gate = _settings_gate(provider, op, explicit, ctx, tool)
    if gate:
        return _defer(gate)
    if step.privilege == "sudo":
        if step.interactive and not ctx.interactive:
            return _defer(NEEDS_TERMINAL)
        return _sudo(provider, ctx)
    if step.privilege == "helper-sudo":
        return _helper_sudo(step, provider, ctx)
    if step.privilege == "polkit":
        return _allow()
    if step.privilege == "uac-possible":
        if host.is_elevated(ctx.platform) or (ctx.interactive and host.desktop_session(ctx.platform)):
            return _allow()
        return _defer(WINDOWS_APPROVAL)
    # elevated-required
    if host.is_elevated(ctx.platform):
        return _allow()
    return _defer("Run from an elevated terminal: " + " ".join(step.argv))


def _sudo(provider: "Provider", ctx: "Context") -> PrivilegeDecision:
    if ctx.os_name == "windows" or provider.name not in SUDO_PROVIDERS:
        return _defer("refused: " + provider.name + " is not a system package manager, so aiup will not use sudo for it")
    if host.is_root():
        return _allow()  # already root (only with AIUP_ALLOW_ROOT=1)
    if ctx.interactive:
        return _allow(("sudo",))
    return _allow(("sudo", "-n"))


def _helper_sudo(step: Step, provider: "Provider", ctx: "Context") -> PrivilegeDecision:
    """A command that calls sudo itself. Never wrapped; same provider rule as sudo.

    Without a terminal it may run only when it asks for nothing (the AUR
    provider passes ``-n`` to the helper's sudo then); a password request
    becomes deferred in the engine.
    """
    if ctx.os_name == "windows" or provider.name not in SUDO_PROVIDERS:
        return _defer("refused: " + provider.name + " is not a system package manager, so aiup will not use sudo for it")
    if step.interactive and not ctx.interactive:
        return _defer(NEEDS_TERMINAL)
    return _allow()


def _settings_gate(provider: "Provider", op: str, explicit: bool, ctx: "Context", tool: str) -> str:
    """The ``settings system`` rule for plain runs. "" when the step may go ahead.

    A dry run plans the step as if the question were answered yes, unless
    ``settings system report`` says it never runs in a plain run.
    """
    if ctx.dry_run and (explicit or ctx.settings.system != "report"):
        return ""
    if explicit:
        # aiup system, and an update pacman can only do as a full upgrade, need the yes.
        if _asks_when_explicit(provider, op) and ctx.system_approved is not True:
            if ctx.settings.system == "auto":
                return ""
            return NEEDS_TERMINAL if not ctx.interactive else "not approved; nothing changed"
        return ""
    setting = ctx.settings.system
    if setting == "auto":
        return ""
    if setting == "ask" and ctx.interactive and ctx.system_approved is True:
        return ""
    if not provider.targeted_update:
        return provider.name + " updates only as a full system upgrade; run aiup system"
    return report_note(tool)


def needs_question(step: Step, provider: "Provider", op: str, explicit: bool, ctx: "Context") -> bool:
    """True when this step waits for the one ``settings system ask`` question."""
    if step.privilege not in PRIVILEGED or ctx.settings.system == "auto" or not ctx.interactive:
        return False
    if explicit:
        return _asks_when_explicit(provider, op)
    return ctx.settings.system == "ask"


def _asks_when_explicit(provider: "Provider", op: str) -> bool:
    return op == "system" or (op == "update" and not provider.targeted_update)


def ask_system(ctx: "Context", commands: Sequence[str], notes: Sequence[str] = (),
               heading: str = "These steps run with administrator rights:") -> bool:
    """Ask once before system steps run. Records the answer in ``ctx.system_approved``.

    The question and the commands go to stderr; the answer is read from the
    terminal. No terminal, end of input or anything but y/yes means no.
    Ctrl-C at the question records no and is raised again, so the run stops.
    """
    if ctx.system_approved is not None:
        return ctx.system_approved
    if ctx.dry_run:
        return False
    if not ctx.interactive:
        ctx.system_approved = False
        return False
    lines: List[str] = [""]
    for note in notes:
        lines.append("  " + note)
    lines.append("  " + heading)
    for command in commands:
        lines.append("    " + command)
    for line in lines:
        ctx.say(line)
    try:
        sys.stderr.write("  Run them now? [y/N] ")
        sys.stderr.flush()
        answer = sys.stdin.readline()
    except KeyboardInterrupt:
        ctx.system_approved = False
        ctx.say("")
        raise
    except (OSError, ValueError):
        answer = ""
        ctx.say("")
    ctx.system_approved = answer.strip().lower() in ("y", "yes")
    return ctx.system_approved


def confirm_step(ctx: "Context", question: str) -> str:
    """Ask a step's own yes/no question once per run. Returns "yes", "no" or "no-terminal".

    The default is no. A dry run plans the step as if the answer were yes.
    Ctrl-C at the question is raised again, so the run stops.
    """
    if ctx.dry_run:
        return "yes"
    known = ctx.confirmed.get(question)
    if known is not None:
        return "yes" if known else "no"
    if not ctx.interactive:
        return "no-terminal"
    try:
        sys.stderr.write("  " + question + " [y/N] ")
        sys.stderr.flush()
        answer = sys.stdin.readline()
    except KeyboardInterrupt:
        ctx.confirmed[question] = False
        ctx.say("")
        raise
    except (OSError, ValueError):
        answer = ""
        ctx.say("")
    yes = answer.strip().lower() in ("y", "yes")
    ctx.confirmed[question] = yes
    return "yes" if yes else "no"


def shown_command(step: Step, provider: "Provider", ctx: "Context") -> str:
    """How a privileged step is named in the question (``sudo pacman -Syu``)."""
    prefix = "sudo " if step.privilege == "sudo" and not host.is_root() and ctx.os_name != "windows" else ""
    return prefix + " ".join(step.argv)


def sudo_password_refused(wrap: Tuple[str, ...], tail: Sequence[str], helper: bool = False) -> bool:
    """True when ``sudo -n`` failed because it would have asked for a password.

    ``helper`` is True for a ``helper-sudo`` step run without a terminal: the
    helper ran its own ``sudo -n``.
    """
    if wrap[:2] != ("sudo", "-n") and not helper:
        return False
    text = "\n".join(tail).lower()
    return any(line in text for line in _SUDO_PASSWORD_LINES)


def root_refusal(ctx: "Context") -> str:
    """A message when aiup runs as root without AIUP_ALLOW_ROOT=1, else ""."""
    if ctx.os_name != "windows" and host.is_root() and not ctx.config.allow_root:
        return ROOT_REFUSED
    return ""


def elevated_note(ctx: "Context") -> str:
    """The note for a Windows run started elevated, else ""."""
    if ctx.os_name == "windows" and host.is_elevated(ctx.platform):
        return WINDOWS_ELEVATED_NOTE
    return ""


def wrapped_argv(decision: PrivilegeDecision, step: Step) -> Tuple[Tuple[str, ...], Dict[str, str]]:
    """The argv to run and the environment for the child.

    With sudo, the step's variables go after ``env`` inside the sudo command
    line (sudo resets the environment), never through the user's environment.
    """
    if not decision.wrap:
        return tuple(step.argv), dict(step.env)
    pairs = tuple(k + "=" + v for k, v in step.env.items())
    if pairs:
        return decision.wrap + ("env",) + pairs + tuple(step.argv), {}
    return decision.wrap + tuple(step.argv), {}
