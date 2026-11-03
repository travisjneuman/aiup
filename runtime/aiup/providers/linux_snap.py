"""Snap packages through snapd. Design doc 6.3 and 7.3.

- Installed snaps come from ``snap list``, which asks the local snapd.
  Pending refreshes come from ``snap refresh --list``, where snapd asks the
  store. A snap that list leaves out is current, so no ``snap info`` runs.
- Latest versions come from ``snap info``: the version on the channel the
  snap tracks, or ``latest/stable`` for a snap that is not installed.
- install, refresh and remove run with sudo. Removal never passes
  ``--purge``, so snapd keeps its automatic snapshot of the snap's data.
- Base, core and snapd snaps are dependencies, so they are not "explicit".
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, Iterable, List, Mapping, NamedTuple, Optional, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Target
from aiup.providers.base import Provider
from aiup.providers._linux import INVENTORY_MAX_BYTES, Memo, is_linux, run_c, system_step, which

if TYPE_CHECKING:
    from aiup.engine.context import Context

SNAPD_SOCKET = "/run/snapd.socket"
SNAP_BIN = "/snap/bin"
SNAP_MOUNT_ROOTS = ("/snap", "/var/lib/snapd/snap")
DEFAULT_CHANNEL = "latest/stable"
DEPENDENCY_NOTES = frozenset({"base", "core", "snapd"})
MEMO_TTL = 300.0
QUERY_TIMEOUT = 20.0
_MEMO = Memo()


class Snap(NamedTuple):
    """One installed snap."""

    name: str
    version: str
    tracking: str
    notes: Tuple[str, ...]


def parse_list(text: str) -> Dict[str, Snap]:
    """``snap list``: Name Version Rev Tracking Publisher Notes, after a header row."""
    snaps: Dict[str, Snap] = {}
    for index, line in enumerate(text.splitlines()):
        parts = line.split()
        if index == 0 or len(parts) < 4:
            continue
        notes = tuple(parts[5].split(",")) if len(parts) > 5 and parts[5] != "-" else ()
        if "disabled" in notes:
            continue
        snaps[parts[0]] = Snap(parts[0], parts[1], parts[3], notes)
    return snaps


def installed_snaps(ctx: "Context") -> Dict[str, Snap]:
    """Every installed snap, in one call."""

    def produce() -> Dict[str, Snap]:
        result = run_c(ctx, ("snap", "list"), timeout=QUERY_TIMEOUT, max_bytes=INVENTORY_MAX_BYTES)
        return parse_list(result.out) if result.code == 0 else {}

    return _MEMO.get("list", MEMO_TTL, produce)


def parse_refresh_list(text: str) -> Dict[str, str]:
    """``snap refresh --list``: {name: new version}. "All snaps up to date." gives {}."""
    found: Dict[str, str] = {}
    lines = text.splitlines()
    if not lines or not lines[0].startswith("Name"):
        return found
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 2:
            found[parts[0]] = parts[1]
    return found


def _normal_channel(channel: str) -> str:
    """``stable`` -> ``latest/stable``; full names stay as they are."""
    return channel if "/" in channel else "latest/" + channel


def parse_info_channels(text: str) -> Dict[str, str]:
    """The ``channels:`` block of ``snap info``: {track/risk: version}. Closed channels ("^", "--") are skipped."""
    found: Dict[str, str] = {}
    inside = False
    for line in text.splitlines():
        if not line.startswith(" "):
            inside = line.startswith("channels:")
            continue
        if not inside:
            continue
        key, sep, rest = line.strip().partition(":")
        words = rest.split()
        if sep and words and words[0] not in ("^", "--", "↑"):
            found[_normal_channel(key.strip())] = words[0]
    return found


class SnapProvider(Provider):
    """Snaps through snapd."""

    name = "snap"
    oses = frozenset({"linux"})
    scope = "system"
    lane = "system"
    exclusive = True
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        """True with the snap command and a running snapd (its socket exists)."""
        return is_linux(ctx) and which(ctx, "snap") is not None and os.path.exists(SNAPD_SOCKET)

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """The installed snap, or None."""
        snap = installed_snaps(ctx).get(target.package)
        if snap is None:
            return None
        return Installed(version=snap.version, path=None, scope="system", channel=self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """Version on the tracked channel (``latest/stable`` when not installed)."""
        snap = installed_snaps(ctx).get(target.package)
        if snap is not None:
            pending = self._refresh_list(ctx)
            if pending is not None and target.package in pending:
                return pending[target.package]
            if pending is not None and snap.version:
                return Latest(snap.version, self.name)
        channel = _normal_channel(snap.tracking) if snap is not None and snap.tracking != "-" else DEFAULT_CHANNEL
        result = run_c(ctx, ("snap", "info", target.package), timeout=max(timeout, 5.0))
        if result.code != 0:
            if snap is not None:
                return Latest("", self.name, "the snap store could not be reached")
            return Latest("", self.name, "not in the snap store")
        version = parse_info_channels(result.out).get(channel, "")
        if not version:
            return Latest("", self.name, "the channel {} has no release".format(channel))
        return Latest(version, self.name)

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Pending refreshes, in one call."""
        return self._refresh_list(ctx) or {}

    def _refresh_list(self, ctx: "Context") -> Optional[Dict[str, Latest]]:
        """``snap refresh --list`` as {name: Latest}. None when it failed."""

        def produce() -> Optional[Dict[str, Latest]]:
            result = run_c(ctx, ("snap", "refresh", "--list"), timeout=QUERY_TIMEOUT)
            if result.code != 0:
                return None
            text = result.out if result.out.strip() else result.err
            return {name: Latest(version, self.name) for name, version in parse_refresh_list(text).items()}

        return _MEMO.get("refresh-list", MEMO_TTL, produce)

    def forget(self) -> None:
        """Drop cached reads after a step; the memos have no file stamp."""
        _MEMO.clear()

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Every installed snap. Base, core and snapd snaps are marked as dependencies."""
        rows: List[PackageRecord] = []
        for snap in sorted(installed_snaps(ctx).values()):
            explicit = not DEPENDENCY_NOTES.intersection(snap.notes) and snap.name not in DEPENDENCY_NOTES
            rows.append(PackageRecord(manager=self.name, name=snap.name, version=snap.version,
                                      scope="system", explicit=explicit))
        return tuple(rows)

    def install(self, ctx: "Context", target: Target) -> Action:
        """``snap install NAME`` (plus ``--classic`` when the catalog says so)."""
        argv = ("snap", "install", target.package) + tuple(target.flags)
        step = system_step(ctx, argv, " ".join(argv))
        return Action(tool=target.package, op="install", channel=self.name, steps=(step,))

    def update(self, ctx: "Context", target: Target) -> Action:
        """``snap refresh NAME``."""
        step = system_step(ctx, ("snap", "refresh", target.package), "snap refresh " + target.package)
        return Action(tool=target.package, op="update", channel=self.name, steps=(step,))

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``snap remove NAME``, without ``--purge``."""
        step = system_step(ctx, ("snap", "remove", target.package), "snap remove " + target.package)
        return Action(tool=target.package, op="remove", channel=self.name, steps=(step,),
                      note="snapd keeps a snapshot of the snap's data after removal.")

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """``/snap/bin/NAME`` or ``NAME.APP`` launchers, and files under a snap's mount."""
        if os.path.dirname(path) == SNAP_BIN:
            name = os.path.basename(path).split(".", 1)[0]
            if name:
                return Ownership(manager=self.name, package=name, confidence="exact")
        real = os.path.realpath(path)
        for root in SNAP_MOUNT_ROOTS:
            prefix = root + "/"
            if real.startswith(prefix):
                name = real[len(prefix):].split("/", 1)[0]
                if name and name != "bin" and name in installed_snaps(ctx):
                    return Ownership(manager=self.name, package=name, confidence="exact")
        return None

    def system_upgrade(self, ctx: "Context") -> Optional[Action]:
        """``snap refresh`` for every snap."""
        if not self.available(ctx):
            return None
        step = system_step(ctx, ("snap", "refresh"), "snap refresh")
        return Action(tool="system", op="update", channel=self.name, steps=(step,),
                      note="This runs sudo snap refresh.")
