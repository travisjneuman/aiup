"""pnpm global packages (channel ``pnpm``, design doc section 6.3).

Keep-policy updates only: aiup updates a tool that is already a pnpm global
package with ``pnpm add -g pkg@latest`` and never picks pnpm for a new
install (new npm tools go into aiup's npm prefix).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, Iterable, Mapping, NamedTuple, Optional, Tuple

from aiup.engine.net import clean_version
from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers.script import (
    ALL_OSES, batch_args_safe, empty_action, path_inside, real_path, which,
)

if TYPE_CHECKING:
    from aiup.engine.context import Context

_LIST_MAX = 8 * 1024 * 1024
_LIST_TIMEOUT = 30.0
_TTL = 60.0
NO_NEW_INSTALLS = "aiup does not make new pnpm installs; new npm tools go into aiup's own npm folder."


class Package(NamedTuple):
    """One pnpm global package."""

    name: str
    version: str
    path: str


_CACHE: Dict[str, Tuple[float, Dict[str, Package], Dict[str, str]]] = {}
_LOCK = threading.Lock()
# pnpm 11 refuses global commands (ls -g too) when its global bin folder is not on PATH.
_BIN_NOT_ON_PATH = re.compile(r'global bin directory "([^"]+)" is not in PATH')


def parse_ls(data: object) -> Dict[str, Package]:
    """Packages from ``pnpm ls -g --json`` (a list of projects with ``dependencies``)."""
    projects = data if isinstance(data, list) else [data]
    found: Dict[str, Package] = {}
    for project in projects:
        deps = project.get("dependencies") if isinstance(project, dict) else None
        if not isinstance(deps, dict):
            continue
        for name, info in deps.items():
            if not isinstance(info, dict):
                continue
            path = info.get("path")
            found[str(name)] = Package(str(name), clean_version(info.get("version")),
                                       path if isinstance(path, str) else "")
    return found


def _list(ctx: "Context", pnpm: str, env: Optional[Mapping[str, str]]) -> Any:
    """One ``pnpm ls -g --json`` read: the result, or None when it could not start."""
    try:
        return ctx.run_read((pnpm, "ls", "-g", "--json"), _LIST_TIMEOUT, _LIST_MAX, env=env)
    except (OSError, ValueError):
        return None


def _path_env(ctx: "Context", result: Any) -> Dict[str, str]:
    """PATH with pnpm's global bin folder in front, when pnpm refused because it was missing."""
    text = str(getattr(result, "stderr", "") or "") + "\n" + str(getattr(result, "stdout", "") or "")
    match = _BIN_NOT_ON_PATH.search(text)
    if match is None or not os.path.isabs(match.group(1)):
        return {}
    current = ctx.env.get("PATH", os.environ.get("PATH", ""))
    return {"PATH": match.group(1) + (os.pathsep + current if current else "")}


def _read_globals(ctx: "Context", pnpm: str) -> Tuple[Dict[str, Package], Dict[str, str]]:
    """The global packages and the environment pnpm needs for global commands."""
    env: Dict[str, str] = {}
    result = _list(ctx, pnpm, None)
    if result is not None and not getattr(result, "ok", False):
        env = _path_env(ctx, result)
        if env:
            result = _list(ctx, pnpm, env)
    out = getattr(result, "stdout", "") if result is not None and getattr(result, "ok", False) else ""
    try:
        packages = parse_ls(json.loads(out)) if isinstance(out, str) and out else {}
    except ValueError:
        packages = {}
    return packages, env


def _globals(ctx: "Context") -> Tuple[Dict[str, Package], Dict[str, str]]:
    """``_read_globals``, remembered for a minute."""
    pnpm = which(ctx, "pnpm")
    if not pnpm:
        return {}, {}
    with _LOCK:
        cached = _CACHE.get(pnpm)
        if cached and time.monotonic() - cached[0] < _TTL:
            return cached[1], cached[2]
    packages, env = _read_globals(ctx, pnpm)
    with _LOCK:
        _CACHE[pnpm] = (time.monotonic(), packages, env)
    return packages, env


def global_packages(ctx: "Context") -> Dict[str, Package]:
    """pnpm's global packages, remembered for a minute. Empty when pnpm cannot list them."""
    return _globals(ctx)[0]


def _forget() -> None:
    """Drop the remembered list; the engine calls this after every step that ran."""
    with _LOCK:
        _CACHE.clear()


class PnpmProvider(Provider):
    """Existing pnpm global packages."""

    name = "pnpm"
    oses = ALL_OSES
    scope = "user"
    lane = "npm"
    exclusive = False
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        return which(ctx, "pnpm") is not None

    def forget(self) -> None:
        _forget()

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        package = global_packages(ctx).get(target.package)
        if package is None:
            return None
        return Installed(package.version, package.path or None, "user", self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        version = ctx.net.npm_latest(target.package, timeout)
        return Latest(version, "registry") if version else Latest("", "registry", "the npm registry did not answer")

    def install(self, ctx: "Context", target: Target) -> Action:
        return empty_action(target, "install", NO_NEW_INSTALLS)

    def update(self, ctx: "Context", target: Target) -> Action:
        if target.package not in global_packages(ctx):
            return empty_action(target, "update", NO_NEW_INSTALLS)
        return self._run(ctx, target, "update", ("add", "-g", target.package + "@latest"))

    def remove(self, ctx: "Context", target: Target) -> Action:
        if target.package not in global_packages(ctx):
            return empty_action(target, "remove", "Nothing to remove: " + target.package + " is not a pnpm global package.")
        return self._run(ctx, target, "remove", ("remove", "-g", target.package))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        resolved = real_path(path)
        for package in global_packages(ctx).values():
            if package.path and path_inside(resolved, real_path(package.path)):
                return Ownership(self.name, package.name, "exact")
        return None

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        return tuple(PackageRecord(self.name, p.name, p.version, "user", True, (p.path,) if p.path else ())
                     for p in sorted(global_packages(ctx).values()))

    def _run(self, ctx: "Context", target: Target, op: str, args: Tuple[str, ...]) -> Action:
        pnpm = which(ctx, "pnpm")
        if not pnpm:
            return empty_action(target, op, "pnpm is not on PATH.")
        if not batch_args_safe(pnpm, args):
            return empty_action(target, op, "Refusing to pass these arguments to pnpm.cmd.")
        step = Step(argv=(pnpm,) + args, label="pnpm " + " ".join(args), env=_globals(ctx)[1])
        return Action(tool=target.package, op=op, channel=self.name, steps=(step,))
