"""Bun global packages (channel ``bun``, design doc section 6.3).

Keep-policy updates only, like pnpm: an existing bun global package is
updated with ``bun add -g pkg@latest``; bun is never picked for a new install.
Versions are read from bun's global folder
(``${BUN_INSTALL:-~/.bun}/install/global``), with ``bun pm ls -g`` as the
fallback.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, Optional, Tuple

from aiup.engine.cache import read_json
from aiup.engine.net import clean_version
from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers.script import (
    ALL_OSES, batch_args_safe, empty_action, env_dir, home, path_inside, read_command, real_path, which,
)

if TYPE_CHECKING:
    from aiup.engine.context import Context

_JSON_MAX = 1024 * 1024
_LS_LINE = re.compile(r"^[\s│├└─|`+\\-]*((?:@[^@\s/]+/)?[^@\s]+)@(\S+)\s*$")
_SELF = frozenset({"bun", "bunx", "bun.exe", "bunx.exe"})
NO_NEW_INSTALLS = "aiup does not make new bun installs; new npm tools go into aiup's own npm folder."


def bun_home(ctx: "Context") -> Path:
    """``BUN_INSTALL`` or ``~/.bun``."""
    return env_dir(ctx, "BUN_INSTALL", home(ctx) / ".bun")


def global_dir(ctx: "Context") -> Path:
    """Bun's global project folder."""
    return bun_home(ctx) / "install" / "global"


def _version_from_folder(ctx: "Context", package: str) -> Optional[str]:
    data = read_json(global_dir(ctx).joinpath("node_modules", *package.split("/"), "package.json"), _JSON_MAX)
    return clean_version(data.get("version")) if isinstance(data, dict) else None


def explicit_packages(ctx: "Context") -> Tuple[str, ...]:
    """Packages installed on request (the global project's ``dependencies``)."""
    data = read_json(global_dir(ctx) / "package.json", _JSON_MAX)
    deps = data.get("dependencies") if isinstance(data, dict) else None
    return tuple(sorted(str(name) for name in deps)) if isinstance(deps, dict) else ()


def parse_pm_ls(text: str) -> Dict[str, str]:
    """``name -> version`` from ``bun pm ls -g`` tree lines (``├── name@1.2.3``)."""
    found: Dict[str, str] = {}
    for line in text.splitlines():
        match = _LS_LINE.match(line)
        if match:
            found[match.group(1)] = clean_version(match.group(2))
    return found


class BunProvider(Provider):
    """Existing bun global packages."""

    name = "bun"
    oses = ALL_OSES
    scope = "user"
    lane = "npm"
    exclusive = False
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        return self._bun(ctx) is not None

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        version = self._version(ctx, target.package)
        if version is None:
            return None
        path = global_dir(ctx).joinpath("node_modules", *target.package.split("/"))
        return Installed(version, str(path), "user", self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        version = ctx.net.npm_latest(target.package, timeout)
        return Latest(version, "registry") if version else Latest("", "registry", "the npm registry did not answer")

    def install(self, ctx: "Context", target: Target) -> Action:
        return empty_action(target, "install", NO_NEW_INSTALLS)

    def update(self, ctx: "Context", target: Target) -> Action:
        if self._version(ctx, target.package) is None:
            return empty_action(target, "update", NO_NEW_INSTALLS)
        return self._run(ctx, target, "update", ("add", "-g", target.package + "@latest"))

    def remove(self, ctx: "Context", target: Target) -> Action:
        if self._version(ctx, target.package) is None:
            return empty_action(target, "remove", "Nothing to remove: " + target.package + " is not a bun global package.")
        return self._run(ctx, target, "remove", ("remove", "-g", target.package))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        if os.path.basename(path).lower() in _SELF:
            return None
        root = real_path(str(global_dir(ctx) / "node_modules"))
        resolved = real_path(path)
        if not path_inside(resolved, root) or os.path.normcase(resolved) == os.path.normcase(root):
            return None
        parts = Path(os.path.relpath(resolved, root)).parts
        name = parts[0] + "/" + parts[1] if parts[0].startswith("@") and len(parts) > 1 else parts[0]
        return Ownership(self.name, name, "exact")

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        records = []
        for name in explicit_packages(ctx):
            version = _version_from_folder(ctx, name) or ""
            path = str(global_dir(ctx).joinpath("node_modules", *name.split("/")))
            records.append(PackageRecord(self.name, name, version, "user", True, (path,)))
        return tuple(records)

    def _bun(self, ctx: "Context") -> Optional[str]:
        return which(ctx, "bun") or which(ctx, "bun", str(bun_home(ctx) / "bin"))

    def _version(self, ctx: "Context", package: str) -> Optional[str]:
        version = _version_from_folder(ctx, package)
        if version is not None:
            return version
        bun = self._bun(ctx)
        if not bun:
            return None
        return parse_pm_ls(read_command(ctx, (bun, "pm", "ls", "-g")) or "").get(package)

    def _run(self, ctx: "Context", target: Target, op: str, args: Tuple[str, ...]) -> Action:
        bun = self._bun(ctx)
        if not bun:
            return empty_action(target, op, "bun is not on PATH.")
        if not batch_args_safe(bun, args):
            return empty_action(target, op, "Refusing to pass these arguments to a batch file.")
        step = Step(argv=(bun,) + args, label="bun " + " ".join(args))
        return Action(tool=target.package, op=op, channel=self.name, steps=(step,))
