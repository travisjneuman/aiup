"""Flatpak apps, in the user and the system installation. Design doc 6.3 and 7.1.

- Targets are ``app.id`` or ``remote:app.id``; the remote defaults to flathub.
- An installed app is updated in the installation it lives in, with
  ``--user`` or ``--system``. System changes go through polkit, not sudo.
- New installs go to the user installation when the remote is configured
  there, else to the system installation when it is configured there. aiup
  never adds a remote, so a remote configured nowhere means unavailable.
- ``--noninteractive`` is passed only without a terminal; a polkit prompt
  that cannot be answered then fails, and the engine reports it as deferred.
- Many apps publish no version number. Those rows carry an empty version.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, FrozenSet, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Tuple

from aiup.model import PENDING_UPDATE_NOTE, Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers._linux import INVENTORY_MAX_BYTES, Memo, is_linux, mtime_of, run_c, user_step, which

if TYPE_CHECKING:
    from aiup.engine.context import Context

DEFAULT_REMOTE = "flathub"
INSTALLATIONS = ("user", "system")
SYSTEM_ROOT = "/var/lib/flatpak"
MEMO_TTL = 300.0
QUERY_TIMEOUT = 20.0
_COLUMNS = re.compile(r"\t| {2,}")
_MEMO = Memo()


class FlatpakApp(NamedTuple):
    """One installed app."""

    app_id: str
    version: str
    installation: str   # "user" | "system" (or a custom installation name)
    origin: str


def user_root(ctx: "Context") -> str:
    """The user installation: ``$XDG_DATA_HOME/flatpak`` or ``~/.local/share/flatpak``."""
    env = getattr(ctx, "env", os.environ)
    data = env.get("XDG_DATA_HOME", "")
    if not data or not os.path.isabs(data):
        data = str(Path.home() / ".local" / "share")
    return os.path.join(data, "flatpak")


def split_target(target: Target) -> Tuple[str, str]:
    """``remote:app.id`` -> (remote, app id). The remote defaults to flathub."""
    remote, sep, app_id = target.package.partition(":")
    if not sep:
        return DEFAULT_REMOTE, target.package
    return remote, app_id


def split_columns(line: str) -> List[str]:
    """Columns of one ``flatpak --columns`` row (tabs when piped, padded spaces otherwise)."""
    return [part.strip() for part in _COLUMNS.split(line.rstrip("\n"))]


def _scope_flag(installation: str) -> str:
    """``--user`` or ``--system`` for an installation name."""
    return "--user" if installation == "user" else "--system"


def installed_apps(ctx: "Context") -> Tuple[FlatpakApp, ...]:
    """Every installed app in every installation, in one call."""

    def produce() -> Tuple[FlatpakApp, ...]:
        result = run_c(ctx, ("flatpak", "list", "--app", "--columns=application,version,installation,origin"),
                       timeout=QUERY_TIMEOUT, max_bytes=INVENTORY_MAX_BYTES)
        if result.code != 0:
            return ()
        apps: List[FlatpakApp] = []
        for line in result.out.splitlines():
            parts = split_columns(line)
            if len(parts) == 3:
                # An empty version column can collapse into the padding.
                parts = [parts[0], ""] + parts[1:]
            if len(parts) >= 4 and "." in parts[0]:
                apps.append(FlatpakApp(parts[0], parts[1], parts[2], parts[3]))
        return tuple(apps)

    stamp = "{}:{}".format(mtime_of(os.path.join(user_root(ctx), "app")), mtime_of(os.path.join(SYSTEM_ROOT, "app")))
    return _MEMO.get("list:" + stamp, MEMO_TTL, produce)


def find_app(ctx: "Context", app_id: str) -> Optional[FlatpakApp]:
    """The installed copy of ``app_id``, user installation first."""
    matches = [app for app in installed_apps(ctx) if app.app_id == app_id]
    matches.sort(key=lambda app: 0 if app.installation == "user" else 1)
    return matches[0] if matches else None


def remotes(ctx: "Context", installation: str) -> FrozenSet[str]:
    """Remote names configured in one installation."""

    def produce() -> FrozenSet[str]:
        result = run_c(ctx, ("flatpak", "remotes", _scope_flag(installation), "--columns=name"))
        if result.code != 0:
            return frozenset()
        return frozenset(split_columns(line)[0] for line in result.out.splitlines() if line.strip())

    return _MEMO.get("remotes:" + installation, MEMO_TTL, produce)


def install_installation(ctx: "Context", remote: str) -> Optional[str]:
    """Where a new install goes: "user", "system", or None when the remote is not configured."""
    for installation in INSTALLATIONS:
        if remote in remotes(ctx, installation):
            return installation
    return None


def parse_remote_info(text: str) -> Tuple[str, str]:
    """``flatpak remote-info`` text: (version, commit)."""
    version = commit = ""
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        if key == "Version":
            version = value.strip()
        elif key == "Commit":
            commit = value.strip()
    return version, commit


def pending_updates(ctx: "Context", installation: str) -> Optional[Dict[str, str]]:
    """{app id: new version} with an update pending, from cached remote data. None on failure."""

    def produce() -> Optional[Dict[str, str]]:
        argv = ("flatpak", "remote-ls", _scope_flag(installation), "--updates", "--app", "--cached",
                "--columns=application,version")
        result = run_c(ctx, argv, timeout=QUERY_TIMEOUT, max_bytes=INVENTORY_MAX_BYTES)
        if result.code != 0:
            return None
        found: Dict[str, str] = {}
        for line in result.out.splitlines():
            parts = split_columns(line)
            if parts and "." in parts[0]:
                found[parts[0]] = parts[1] if len(parts) > 1 else ""
        return found

    return _MEMO.get("updates:" + installation, MEMO_TTL, produce)


def _flatpak_argv(ctx: "Context", words: Sequence[str]) -> List[str]:
    """flatpak argv with ``-y``, plus ``--noninteractive`` only without a terminal."""
    argv: List[str] = ["flatpak"] + list(words) + ["-y"]
    if not ctx.interactive:
        argv.append("--noninteractive")
    return argv


def _step(ctx: "Context", installation: str, words: Sequence[str], label: str) -> Step:
    """A flatpak step: as the user, polkit for the system installation."""
    privilege = "none" if installation == "user" else "polkit"
    return user_step(_flatpak_argv(ctx, words), label, interactive=bool(ctx.interactive), privilege=privilege)


class FlatpakProvider(Provider):
    """Flatpak apps (user and system installations)."""

    name = "flatpak"
    oses = frozenset({"linux"})
    scope = "mixed"
    lane = "flatpak"
    exclusive = False
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        """True with flatpak on PATH."""
        return is_linux(ctx) and which(ctx, "flatpak") is not None

    def can_provide(self, ctx: "Context", target: Target) -> bool:
        """True when the target's remote is configured in one of the installations."""
        remote, _ = split_target(target)
        return self.available(ctx) and install_installation(ctx, remote) is not None

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """The installed app (user installation first), or None. The version may be empty."""
        _, app_id = split_target(target)
        app = find_app(ctx, app_id)
        if app is None:
            return None
        scope = "user" if app.installation == "user" else "system"
        return Installed(version=app.version, path=None, scope=scope, channel=self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """Version on the remote, from cached remote data first."""
        remote, app_id = split_target(target)
        app = find_app(ctx, app_id)
        installation = app.installation if app is not None else install_installation(ctx, remote)
        if installation is None:
            return Latest("", self.name, "the flatpak remote {} is not configured".format(remote))
        if app is not None:
            remote = app.origin or remote
            updates = pending_updates(ctx, installation)
            if updates is not None and updates.get(app_id):
                return Latest(updates[app_id], self.name)
            if updates is not None and app_id in updates:
                return Latest("", self.name, PENDING_UPDATE_NOTE, pending=True)
            if updates is not None and app_id not in updates and app.version:
                return Latest(app.version, self.name)
        version = self._remote_version(ctx, installation, remote, app_id, timeout)
        if version is None:
            return Latest("", self.name, "{} is not on the flatpak remote {}".format(app_id, remote))
        if not version:
            return Latest("", self.name, "this app publishes no version number")
        return Latest(version, self.name)

    def _remote_version(self, ctx: "Context", installation: str, remote: str, app_id: str,
                        timeout: float) -> Optional[str]:
        """``flatpak remote-info`` version: cached data, then the network. None when not found."""
        for cached in (True, False):
            argv: List[str] = ["flatpak", "remote-info", _scope_flag(installation)]
            if cached:
                argv.append("--cached")
            argv.extend([remote, app_id])
            result = run_c(ctx, argv, timeout=max(timeout, 3.0))
            if result.code == 0:
                return parse_remote_info(result.out)[0]
        return None

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Apps with an update pending in either installation."""
        found: Dict[str, Latest] = {}
        for installation in INSTALLATIONS:
            for app_id, version in (pending_updates(ctx, installation) or {}).items():
                if version:
                    found.setdefault(app_id, Latest(version, self.name))
                else:
                    found.setdefault(app_id, Latest("", self.name, PENDING_UPDATE_NOTE, pending=True))
        return found

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Every installed app. Runtimes are left out: they are dependencies."""
        rows: List[PackageRecord] = []
        for app in installed_apps(ctx):
            scope = "user" if app.installation == "user" else "system"
            rows.append(PackageRecord(manager=self.name, name=app.app_id, version=app.version, scope=scope,
                                      explicit=True, paths=self._export_paths(ctx, app)))
        return tuple(rows)

    def _export_paths(self, ctx: "Context", app: FlatpakApp) -> Tuple[str, ...]:
        """The app's launcher in its installation's ``exports/bin``, when present."""
        root = user_root(ctx) if app.installation == "user" else SYSTEM_ROOT
        path = os.path.join(root, "exports", "bin", app.app_id)
        return (path,) if os.path.exists(path) else ()

    def install(self, ctx: "Context", target: Target) -> Action:
        """``flatpak install --user REMOTE APP`` (or ``--system`` when only the system has the remote)."""
        remote, app_id = split_target(target)
        installation = install_installation(ctx, remote)
        if installation is None:
            note = "The flatpak remote {} is not configured, and aiup does not add remotes.".format(remote)
            return Action(tool=app_id, op="install", channel=self.name, steps=(), note=note)
        step = _step(ctx, installation, ("install", _scope_flag(installation), remote, app_id),
                     "flatpak install {} {}".format(_scope_flag(installation), app_id))
        return Action(tool=app_id, op="install", channel=self.name, steps=(step,))

    def update(self, ctx: "Context", target: Target) -> Action:
        """``flatpak update --user|--system APP`` in the installation that has it."""
        remote, app_id = split_target(target)
        app = find_app(ctx, app_id)
        installation = app.installation if app is not None else (install_installation(ctx, remote) or "user")
        step = _step(ctx, installation, ("update", _scope_flag(installation), app_id),
                     "flatpak update {} {}".format(_scope_flag(installation), app_id))
        return Action(tool=app_id, op="update", channel=self.name, steps=(step,))

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``flatpak uninstall --user|--system APP``. App data in ~/.var/app is kept."""
        _, app_id = split_target(target)
        app = find_app(ctx, app_id)
        installation = app.installation if app is not None else "user"
        step = _step(ctx, installation, ("uninstall", _scope_flag(installation), app_id),
                     "flatpak uninstall {} {}".format(_scope_flag(installation), app_id))
        return Action(tool=app_id, op="remove", channel=self.name, steps=(step,))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """Launchers in ``exports/bin`` and files below an app folder."""
        roots = (user_root(ctx), SYSTEM_ROOT)
        for candidate in (path, os.path.realpath(path)):
            for root in roots:
                app_id = _app_under(candidate, root)
                if app_id:
                    return Ownership(manager=self.name, package=app_id, confidence="exact")
        return None

    def system_upgrade(self, ctx: "Context") -> Optional[Action]:
        """``flatpak update -y`` for both installations (system part through polkit)."""
        if not self.available(ctx):
            return None
        step = _step(ctx, "system", ("update",), "flatpak update")
        return Action(tool="system", op="update", channel=self.name, steps=(step,),
                      note="This runs flatpak update for the user and system installations.")

    def forget(self) -> None:
        """Drop cached reads after a step. An update leaves the app folder's mtime alone."""
        _MEMO.clear()


def _app_under(path: str, root: str) -> str:
    """The app id when ``path`` is ``<root>/exports/bin/<id>`` or below ``<root>/app/<id>``."""
    prefix = root.rstrip("/") + "/"
    if not path.startswith(prefix):
        return ""
    parts = path[len(prefix):].split("/")
    if len(parts) == 3 and parts[0] == "exports" and parts[1] == "bin":
        return parts[2]
    if len(parts) >= 2 and parts[0] == "app" and "." in parts[1]:
        return parts[1]
    return ""
