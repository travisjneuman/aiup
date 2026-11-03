"""pipx applications (channel ``pipx``, design doc section 6.3).

Reads ``pipx list --json`` (one call for every app), takes latest versions
from PyPI, and updates with ``pipx upgrade``. New installs use
``pipx install``; aiup prefers uv for new installs, so this mostly keeps
existing pipx apps current.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import TYPE_CHECKING, Dict, Iterable, List, NamedTuple, Optional, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers.script import (
    ALL_OSES, empty_action, path_inside, path_setup_step, read_command, real_path, which,
)
from aiup.providers.uv import normalize, package_name, pypi_latest

if TYPE_CHECKING:
    from aiup.engine.context import Context

_LIST_MAX = 8 * 1024 * 1024
_LIST_TIMEOUT = 30.0
_TTL = 60.0


class App(NamedTuple):
    """One pipx venv."""

    name: str
    version: str
    paths: Tuple[str, ...]


_CACHE: Dict[str, Tuple[float, Dict[str, App]]] = {}
_LOCK = threading.Lock()


def _app_paths(main: Dict[str, object]) -> Tuple[str, ...]:
    found: List[str] = []
    items = main.get("app_paths")
    for item in items if isinstance(items, list) else ():
        value = item.get("__Path__") if isinstance(item, dict) else item
        if isinstance(value, str) and value:
            found.append(value)
    return tuple(found)


def _parse(data: object) -> Dict[str, App]:
    venvs = data.get("venvs") if isinstance(data, dict) else None
    apps: Dict[str, App] = {}
    if not isinstance(venvs, dict):
        return apps
    for name, venv in venvs.items():
        meta = venv.get("metadata") if isinstance(venv, dict) else None
        main = meta.get("main_package") if isinstance(meta, dict) else None
        if not isinstance(main, dict):
            continue
        version = main.get("package_version")
        apps[normalize(str(name))] = App(str(name), version if isinstance(version, str) else "", _app_paths(main))
    return apps


def list_apps(ctx: "Context") -> Dict[str, App]:
    """Every pipx app keyed by normalized name, remembered for a minute."""
    pipx = which(ctx, "pipx")
    if not pipx:
        return {}
    with _LOCK:
        cached = _CACHE.get(pipx)
        if cached and time.monotonic() - cached[0] < _TTL:
            return cached[1]
    out = read_command(ctx, (pipx, "list", "--json"), timeout=_LIST_TIMEOUT, max_bytes=_LIST_MAX)
    try:
        apps = _parse(json.loads(out)) if out else {}
    except ValueError:
        apps = {}
    with _LOCK:
        _CACHE[pipx] = (time.monotonic(), apps)
    return apps


def _forget() -> None:
    """Drop the remembered list; the engine calls this after every step that ran."""
    with _LOCK:
        _CACHE.clear()


def _environment(ctx: "Context", key: str) -> str:
    """One value from ``pipx environment --value KEY``."""
    pipx = which(ctx, "pipx")
    out = read_command(ctx, (pipx, "environment", "--value", key)) if pipx else None
    value = (out or "").strip()
    return value if value and os.path.isabs(value) else ""


class PipxProvider(Provider):
    """Python applications installed with pipx."""

    name = "pipx"
    oses = ALL_OSES
    scope = "user"
    lane = "python"
    exclusive = False
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        return which(ctx, "pipx") is not None

    def forget(self) -> None:
        _forget()

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        app = list_apps(ctx).get(normalize(package_name(target)))
        if app is None:
            return None
        return Installed(app.version, app.paths[0] if app.paths else None, "user", self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        return pypi_latest(ctx, package_name(target), timeout)

    def install(self, ctx: "Context", target: Target) -> Action:
        pipx = which(ctx, "pipx")
        if not pipx:
            return empty_action(target, "install", "pipx is not on PATH.")
        steps: List[Step] = [Step(argv=(pipx, "install", target.package), label="pipx install " + target.package)]
        bin_dir = _environment(ctx, "PIPX_BIN_DIR")
        setup = path_setup_step(ctx, bin_dir) if bin_dir else None
        if setup is not None:
            steps.append(setup)
        return Action(tool=target.package, op="install", channel=self.name, steps=tuple(steps))

    def update(self, ctx: "Context", target: Target) -> Action:
        pipx = which(ctx, "pipx")
        if not pipx:
            return empty_action(target, "update", "pipx is not on PATH.")
        app = list_apps(ctx).get(normalize(package_name(target)))
        if app is None:
            return self.install(ctx, target)
        step = Step(argv=(pipx, "upgrade", app.name), label="pipx upgrade " + app.name)
        return Action(tool=target.package, op="update", channel=self.name, steps=(step,))

    def remove(self, ctx: "Context", target: Target) -> Action:
        pipx = which(ctx, "pipx")
        app = list_apps(ctx).get(normalize(package_name(target)))
        if not pipx or app is None:
            return empty_action(target, "remove", "Nothing to remove: " + target.package + " is not a pipx app.")
        step = Step(argv=(pipx, "uninstall", app.name), label="pipx uninstall " + app.name)
        return Action(tool=target.package, op="remove", channel=self.name, steps=(step,))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        apps = list_apps(ctx)
        if not apps:
            return None
        wanted = os.path.normcase(os.path.normpath(path))
        for app in apps.values():
            if any(os.path.normcase(os.path.normpath(p)) == wanted for p in app.paths):
                return Ownership(self.name, app.name, "exact")
        venvs = _environment(ctx, "PIPX_LOCAL_VENVS")
        resolved = real_path(path)
        if venvs and path_inside(resolved, real_path(venvs)):
            first = os.path.relpath(resolved, real_path(venvs)).split(os.sep)[0]
            app = apps.get(normalize(first))
            if app is not None:
                return Ownership(self.name, app.name, "exact")
        return None

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        return tuple(PackageRecord(self.name, app.name, app.version, "user", True, app.paths)
                     for app in sorted(list_apps(ctx).values()))
