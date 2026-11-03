"""Channel resolution, the channel policy and the special-tool hooks (design doc 6.5, 6.6).

Which channel a tool uses, in this order:

1. A pick in channels.tsv always wins (macOS ``channels_load``).
2. A manager policy (``system`` or a manager name) uses that manager wherever
   it has the tool, and moves copies from other channels to it.
3. ``keep`` updates each copy where it is and never moves one. New installs
   use the newest order.
4. ``newest`` uses the first channel in the section 5.4 order that this
   computer has. A copy on a user-level channel aiup can reinstall from
   (npm, uv, pipx, vendor, script) moves to it, and the old copy is removed
   after the new one works. A copy that came from a system or other package
   manager stays where it is; ``aiup channel TOOL CHANNEL`` moves it.

Copies are removed automatically only when they are user-scope. A system copy
is never removed by a plain run; the note says so.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, Tuple

from aiup.errors import AiupError
from aiup.model import CatalogEntry, Installed, Target
from aiup.versions import version_is_greater

from aiup.engine import host
from aiup.engine.cache import atomic_write_text, read_text_bounded
from aiup.engine.latest import read_latest
from aiup.engine.prefs import ChannelChoices, load_channels, policies_for, write_channel

if TYPE_CHECKING:
    from aiup.engine.context import Context

Copy = Tuple[Target, Installed]

# Channels a plain newest-policy run may move a copy away from.
MOVABLE_CHANNELS = frozenset({"npm", "uv", "pipx", "vendor", "script"})

# Channels whose root-owned copies a distro package may have put there.
DISTRO_SHADOWED_CHANNELS = frozenset({"npm"})

# Linux distro managers in the order the ``system`` policy tries them.
LINUX_SYSTEM_MANAGERS = ("pacman", "aur", "apt", "dnf", "zypper")

CHANNEL_LABELS: Mapping[str, str] = {
    "pacman": "pacman", "aur": "AUR", "apt": "apt", "dnf": "dnf", "zypper": "zypper",
    "flatpak": "Flatpak", "snap": "Snap", "nix": "Nix", "brew": "Homebrew",
    "winget": "winget", "scoop": "Scoop", "choco": "Chocolatey", "appx": "Microsoft Store",
    "npm": "npm", "pnpm": "pnpm", "bun": "bun", "uv": "uv", "pipx": "pipx",
    "cargo": "cargo", "go": "go", "vendor": "official installer", "script": "install script",
}

_METHOD = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")


def channel_label(channel: str) -> str:
    """A channel's name as people know it."""
    return CHANNEL_LABELS.get(channel, channel)


# ----- special-tool hooks (section 6.6) ------------------------------------------


@dataclass(frozen=True)
class Hook:
    """Per-tool rules the general channel rule cannot express."""

    retire_first: bool = False   # remove old copies before installing on the new channel
    move_note: str = ""          # one line shown when the tool moves channel


# Keep this table small. Each entry names the macOS function it follows.
HOOKS: Mapping[str, Hook] = {
    # update_claude: removes the npm and Homebrew copies, then runs the native
    # installer, so the old ``claude`` command never shadows the new one.
    "claude": Hook(retire_first=True),
    # update_opencode: OpenCode 1.x and 2 cannot share the opencode command;
    # the vendor says to remove package-managed copies before the v2 installer.
    "opencode": Hook(
        retire_first=True,
        move_note="Config carries over; 1.x plugins need porting (https://opencode.ai/v2/docs/migrate-v1/)",
    ),
}


def hook_for(tool: str) -> Hook:
    """The hook for a tool, or the default (no special rule)."""
    return HOOKS.get(tool, Hook())


# ----- resolution ----------------------------------------------------------------


@dataclass(frozen=True)
class Resolution:
    """Where one tool installs and updates from (section 6.5)."""

    active: Optional[Target]          # channel this run uses
    installed: Tuple[Copy, ...]       # every copy found, any channel
    reason: str                       # shown by aiup channel TOOL
    picked: bool                      # True when the user picked it
    retire: Tuple[Copy, ...] = ()     # copies to remove once the active one works
    kept_note: str = ""               # copies left in place, and why

    def copy_on(self, channel: str) -> Optional[Installed]:
        """The copy installed on ``channel``, or None."""
        for target, installed in self.installed:
            if target.channel == channel:
                return installed
        return None

    @property
    def moving(self) -> bool:
        """True when the tool is installed, but not on the active channel."""
        return (self.active is not None and bool(self.installed)
                and self.copy_on(self.active.channel) is None)


def usable_targets(entry: CatalogEntry, ctx: "Context") -> Tuple[Target, ...]:
    """The entry's targets for this OS whose manager is present here, in 5.4 order."""
    return tuple(t for t in entry.targets_for(ctx.os_name) if ctx.provider_available(t.channel))


def find_copies(entry: CatalogEntry, ctx: "Context") -> Tuple[Copy, ...]:
    """Every installed copy of the tool, one per channel, in target order."""
    found: List[Copy] = []
    seen = set()
    for target in usable_targets(entry, ctx):
        if target.channel in seen:
            continue
        provider = ctx.provider(target.channel)
        if provider is None:
            continue
        try:
            installed = provider.installed(ctx, target)
        except Exception:  # noqa: BLE001  a provider bug reads as "not installed", never a crash
            installed = None
        if installed is not None:
            found.append((target, installed))
            seen.add(target.channel)
    return tuple(_hand_to_system(entry, ctx, found))


def _hand_to_system(entry: CatalogEntry, ctx: "Context", found: List[Copy]) -> List[Copy]:
    """Give a distro-packaged copy to its package manager.

    An AUR or repository package that installs into ``/usr/lib/node_modules``
    looks like a system npm copy. When pacman, apt, dnf or zypper owns the
    file, the copy belongs to that manager, so aiup never runs npm against it.
    """
    if ctx.os_name != "linux":
        return found
    paths = [i.path for t, i in found if _distro_candidate(t, i) and i.path]
    if not paths:
        return found
    from aiup.detect.owners import SYSTEM_MANAGERS, system_owners

    try:
        owners = system_owners(ctx, paths)
    except Exception:  # noqa: BLE001  an owner query failure leaves the copy as it was
        owners = {}
    if not owners:
        return found
    channels = {t.channel for t, _ in found}
    out: List[Copy] = []
    for target, installed in found:
        owner = owners.get(installed.path or "") if _distro_candidate(target, installed) else None
        if owner is None or owner.manager not in SYSTEM_MANAGERS or not owner.package:
            out.append((target, installed))
            continue
        if owner.manager in channels:
            continue  # that manager's copy is already listed
        system_target = next((t for t in entry.targets_for(ctx.os_name)
                              if t.channel == owner.manager and t.package == owner.package),
                             Target(owner.manager, owner.package))
        out.append((system_target, _system_installed(ctx, system_target, installed)))
        channels.add(owner.manager)
    return out


def _distro_candidate(target: Target, installed: Installed) -> bool:
    return target.channel in DISTRO_SHADOWED_CHANNELS and installed.scope != "user"


def _system_installed(ctx: "Context", target: Target, fallback: Installed) -> Installed:
    """The manager's own record of the copy, or the npm reading relabeled."""
    provider = ctx.provider(target.channel) if ctx.provider_available(target.channel) else None
    if provider is not None:
        try:
            own = provider.installed(ctx, target)
        except Exception:  # noqa: BLE001  a provider bug falls back to the npm reading
            own = None
        if own is not None:
            return Installed(own.version, own.path or fallback.path, own.scope, own.channel)
    return Installed(fallback.version, fallback.path, "system", target.channel)


def resolve(entry: CatalogEntry, os_name: str, policy: str, picks: Mapping[str, str],
            ctx: "Context", copies: Optional[Tuple[Copy, ...]] = None) -> Resolution:
    """Which channel this run uses for ``entry`` and which copies it retires."""
    targets = usable_targets(entry, ctx)
    found = find_copies(entry, ctx) if copies is None else copies
    pick = picks.get(entry.id, "")
    if pick:
        return _picked(entry, pick, policy, entry.targets_for(os_name), targets, found)
    if policy not in ("newest", "keep"):
        managed = _manager_policy(entry, policy, os_name, targets, found)
        if managed is not None:
            return managed
    if policy == "keep" and found:
        return _keep(found)
    return _newest(entry, targets, found)


def _picked(entry: CatalogEntry, pick: str, policy: str, all_targets: Sequence[Target],
            targets: Sequence[Target], found: Tuple[Copy, ...]) -> Resolution:
    reason = "You picked it (aiup channel {} default follows the {} policy again).".format(entry.id, policy)
    active = next((t for t in targets if t.channel == pick), None)
    if active is None:
        if any(t.channel == pick for t in all_targets):
            reason += " " + channel_label(pick) + " is not available on this computer."
        else:
            reason += " This OS has no " + pick + " channel for it."
        return Resolution(None, found, reason, True)
    retire, kept = _split_others(active.channel, found)
    return Resolution(active, found, reason, True, retire, kept)


def _manager_policy(entry: CatalogEntry, policy: str, os_name: str, targets: Sequence[Target],
                    found: Tuple[Copy, ...]) -> Optional[Resolution]:
    if policy == "system":
        names: Tuple[str, ...] = LINUX_SYSTEM_MANAGERS if os_name == "linux" else ("winget",)
    else:
        names = (policy,)
    # Prefer a manager that already has the tool, then the first one offering it.
    installed_channels = [t.channel for t, _ in found]
    active = next((t for t in targets if t.channel in names and t.channel in installed_channels), None)
    if active is None:
        active = next((t for t in targets if t.channel in names), None)
    if active is None:
        return None
    retire, kept = _split_others(active.channel, found)
    return Resolution(active, found, "The {} policy.".format(policy), False, retire, kept)


def _keep(found: Tuple[Copy, ...]) -> Resolution:
    target = found[0][0]
    if len(found) == 1:
        reason = "The keep policy: the only copy here is on this channel."
    else:
        reason = "The keep policy: aiup updates the copy on {} and leaves the others.".format(
            channel_label(target.channel))
    return Resolution(target, found, reason, False)


def _newest(entry: CatalogEntry, targets: Sequence[Target], found: Tuple[Copy, ...]) -> Resolution:
    if not targets:
        reason = "No channel for {} is available on this computer.".format(entry.id)
        return Resolution(None, found, reason, False)
    first = targets[0]
    reason = "Its default, the channel that ships its releases first."
    if not found or any(t.channel == first.channel for t, _ in found):
        retire, kept = _split_others(first.channel, found, movable_only=True)
        return Resolution(first, found, reason, False, retire, kept)
    staying = next(((t, i) for t, i in found if not _movable(t, i)), None)
    if staying is not None:
        target = staying[0]
        reason = ("Installed with {}; aiup updates it there. aiup channel {} {} moves it.").format(
            channel_label(target.channel), entry.id, first.channel)
        return Resolution(target, found, reason, False)
    retire, kept = _split_others(first.channel, found, movable_only=True)
    return Resolution(first, found, reason, False, retire, kept)


def _real_file(path: Optional[str]) -> str:
    """The resolved, case-normalized file behind ``path``, or "" when there is none."""
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.realpath(path))
    except (OSError, ValueError):
        return ""


def _movable(target: Target, installed: Installed) -> bool:
    return target.channel in MOVABLE_CHANNELS and installed.scope == "user"


def _split_others(active: str, found: Tuple[Copy, ...],
                  movable_only: bool = False) -> Tuple[Tuple[Copy, ...], str]:
    """Copies on other channels: those aiup removes, and a note for the rest.

    A copy whose file is the active copy's file (aider's install script runs
    ``uv tool install``, so it shows up as a script copy and a uv copy) is the
    same tool, so it is dropped, never retired.
    """
    retire: List[Copy] = []
    kept: List[str] = []
    active_file = next((_real_file(i.path) for t, i in found if t.channel == active), "")
    for target, installed in found:
        if target.channel == active:
            continue
        if active_file and _real_file(installed.path) == active_file:
            continue
        if installed.scope == "user" and (not movable_only or target.channel in MOVABLE_CHANNELS):
            retire.append((target, installed))
        else:
            kept.append(channel_label(target.channel))
    note = ""
    if kept:
        note = "The copy from {} stays; aiup removes only user-level copies by itself.".format(" and ".join(kept))
    return tuple(retire), note


# ----- policy and picks ----------------------------------------------------------


def policy_summary(policy: str) -> str:
    """One line describing a policy (macOS ``channel_policy_summary``)."""
    if policy == "keep":
        return ("keep: each tool updates from the channel it is installed from, and nothing moves. "
                "New installs use the default.")
    if policy == "newest":
        return "newest: each tool installs and updates from the channel that ships its releases first."
    if policy == "system":
        return "system: tools your system package manager has install and update from it; the rest use their default."
    return "{0}: tools with a {1} channel install and update from {1}; the rest use their default.".format(
        policy, channel_label(policy))


def set_policy(ctx: "Context", policy: str) -> str:
    """``aiup channel --policy P``. Returns the line to print. Raises ValueError for a bad policy."""
    allowed = policies_for(ctx.os_name)
    if policy not in allowed:
        raise ValueError("expected: aiup channel --policy " + "|".join(allowed))
    if not ctx.dry_run:
        write_channel(ctx.dirs, "*", policy)
    line = "Channel policy · " + policy_summary(policy)
    if policy not in ("newest", "keep"):
        line += ("\nYour next aiup run moves those tools to {} and removes each old copy once the new "
                 "one is in place (settings stay). aiup channel lists where each tool goes.").format(
                     channel_label(policy))
    return line


def set_pick(ctx: "Context", entry: CatalogEntry, choice: str) -> str:
    """``aiup channel TOOL CHOICE`` and ``aiup channel TOOL default``.

    Returns the line to print. Raises ValueError when the tool has no such
    channel on this OS.
    """
    tool = entry.id
    choices = load_channels(ctx.dirs, ctx.os_name)
    targets = entry.targets_for(ctx.os_name)
    if choice == "default":
        if not ctx.dry_run:
            write_channel(ctx.dirs, tool, "")
        picks = {k: v for k, v in choices.picks.items() if k != tool}
        now = resolve(entry, ctx.os_name, choices.policy, picks, ctx)
        active = now.active.channel if now.active is not None else "none"
        return "{0} follows the {1} policy again: {2}. Run aiup only {0} to apply it now.".format(
            tool, choices.policy, active)
    if not any(t.channel == choice for t in targets):
        raise ValueError("{0} has no {1} channel; aiup channel {0} lists them".format(tool, choice))
    default = targets[0].channel if targets else ""
    if not ctx.dry_run:
        # Under newest a pick of the default changes nothing, so it is not stored.
        stored = "" if (choice == default and choices.policy == "newest") else choice
        write_channel(ctx.dirs, tool, stored)
    return ("{0} will install and update from {1}. Run aiup only {0} to switch now; the copy from the "
            "old channel is removed after the new one is in place (settings stay).").format(tool, choice)


# ----- install methods (macOS set_state_method) ------------------------------------


def read_method(ctx: "Context", tool: str) -> str:
    """The channel aiup last installed the tool from, or ""."""
    text = read_text_bounded(ctx.dirs.data / "methods" / tool, 256) or ""
    value = text.strip()
    return value if _METHOD.fullmatch(value) else ""


def write_method(ctx: "Context", tool: str, channel: str) -> None:
    """Record the channel a tool was installed from. Never raises."""
    if ctx.dry_run or not _METHOD.fullmatch(channel):
        return
    try:
        atomic_write_text(ctx.dirs.data / "methods" / tool, channel + "\n")
    except (OSError, ValueError, AiupError):
        pass


# ----- "Newer on another channel" ---------------------------------------------------


@dataclass(frozen=True)
class ChannelHint:
    """A tool whose active channel trails another one."""

    tool: str
    other: str
    other_version: str
    active: str
    active_version: str

    def line(self) -> str:
        """``  tool · npm has V, Homebrew has V · aiup channel tool npm``"""
        return "  {} · {} has {}, {} has {} · aiup channel {} {}".format(
            self.tool, channel_label(self.other), self.other_version,
            channel_label(self.active), self.active_version, self.tool, self.other)


def channel_hints(ctx: "Context", items: Sequence[Tuple[CatalogEntry, Resolution, str]],
                  policy: str) -> List[ChannelHint]:
    """Hints for tools whose channel trails another (macOS ``channel_ahead_rows``).

    ``items`` holds (entry, resolution, active latest version). Tools with a
    pick and tools under a manager policy are left out.
    """
    if policy not in ("newest", "keep"):
        return []
    work = [(e, r, v) for e, r, v in items
            if not r.picked and r.active is not None and v and len(usable_targets(e, ctx)) > 1]
    if not work:
        return []
    workers = max(1, min(len(work), ctx.config.check_workers))
    found = host.map_threads(workers, lambda item: _hint(ctx, *item), work)
    return [hint for hint in found if hint is not None]


def _hint(ctx: "Context", entry: CatalogEntry, resolution: Resolution, version: str) -> Optional[ChannelHint]:
    active = resolution.active
    if active is None:
        return None
    best: Optional[Tuple[str, str]] = None
    for target in usable_targets(entry, ctx):
        if target.channel == active.channel:
            continue
        provider = ctx.provider(target.channel)
        if provider is None:
            continue
        other = read_latest(ctx, provider, target, entry.id, "").version
        if other and version_is_greater(other, version) and (best is None or version_is_greater(other, best[1])):
            best = (target.channel, other)
    if best is None:
        return None
    return ChannelHint(entry.id, best[0], best[1], active.channel, version)


def print_channel_hints(ctx: "Context", hints: Sequence[ChannelHint]) -> None:
    """The "Newer on another channel" block (stderr)."""
    if not hints:
        return
    ctx.say("")
    ctx.say("  Newer on another channel")
    for hint in hints:
        ctx.say(hint.line())


def load_choices(ctx: "Context") -> ChannelChoices:
    """channels.tsv for this OS."""
    return load_channels(ctx.dirs, ctx.os_name)


def policy_names(ctx: "Context") -> Tuple[str, ...]:
    """Policies this OS accepts."""
    return policies_for(ctx.os_name)


def retire_label(copies: Sequence[Copy]) -> str:
    """``npm and Homebrew`` for a list of copies."""
    return " and ".join(channel_label(t.channel) for t, _ in copies)


def resolution_map(ctx: "Context", entries: Sequence[CatalogEntry], choices: ChannelChoices) -> Dict[str, Resolution]:
    """Resolve many tools in parallel (installed reads are the slow part)."""
    if not entries:
        return {}
    workers = max(1, min(len(entries), ctx.config.check_workers))
    results = host.map_threads(workers, lambda e: resolve(e, ctx.os_name, choices.policy, choices.picks, ctx),
                               entries)
    return {entry.id: res for entry, res in zip(entries, results)}
