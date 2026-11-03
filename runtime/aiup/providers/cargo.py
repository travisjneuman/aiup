"""Cargo-installed crates (channel ``cargo``, design doc section 6.3).

Reads ``.crates2.json`` in the cargo install root, takes latest versions from
the crates.io API, and installs with ``cargo install --locked``. When
``cargo-binstall`` is on PATH it is tried first (prebuilt release binaries,
the third-party quick-install mirror turned off), with ``cargo install`` as
the fallback.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, NamedTuple, Optional, Tuple

from aiup.engine.cache import read_json
from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers.script import (
    ALL_OSES, empty_action, env_of, home, is_windows, path_inside, path_setup_step, which,
)

if TYPE_CHECKING:
    from aiup.engine.context import Context

_KEY = re.compile(r"^(\S+) (\S+) \((.+)\)$")
_CRATES2_MAX = 8 * 1024 * 1024


class Crate(NamedTuple):
    """One crate in ``.crates2.json``."""

    name: str
    version: str
    source: str
    bins: Tuple[str, ...]

    @property
    def from_registry(self) -> bool:
        """True for crates.io installs (not git or path)."""
        return self.source.startswith(("registry+", "sparse+"))


def install_root(ctx: "Context") -> Path:
    """``CARGO_INSTALL_ROOT``, else ``CARGO_HOME``, else ``~/.cargo``."""
    for name in ("CARGO_INSTALL_ROOT", "CARGO_HOME"):
        value = env_of(ctx).get(name, "")
        if value and os.path.isabs(value):
            return Path(value)
    return home(ctx) / ".cargo"


def installed_crates(ctx: "Context") -> Dict[str, Crate]:
    """Crates cargo installed, keyed by name."""
    data = read_json(install_root(ctx) / ".crates2.json", _CRATES2_MAX)
    installs = data.get("installs") if isinstance(data, dict) else None
    crates: Dict[str, Crate] = {}
    if not isinstance(installs, dict):
        return crates
    for key, value in installs.items():
        match = _KEY.match(str(key))
        if not match:
            continue
        bins = value.get("bins") if isinstance(value, dict) else None
        names = tuple(str(b) for b in bins) if isinstance(bins, list) else ()
        crates[match.group(1)] = Crate(match.group(1), match.group(2), match.group(3), names)
    return crates


def _bin_path(ctx: "Context", name: str) -> str:
    suffix = "" if name.endswith(".exe") or not is_windows(ctx) else ".exe"
    return str(install_root(ctx) / "bin" / (name + suffix))


class CargoProvider(Provider):
    """Crates installed with ``cargo install``."""

    name = "cargo"
    oses = ALL_OSES
    scope = "user"
    lane = "rust"
    exclusive = False
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        return self._cargo(ctx) is not None

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        crate = installed_crates(ctx).get(target.package)
        if crate is None:
            return None
        path = _bin_path(ctx, crate.bins[0]) if crate.bins else None
        return Installed(crate.version, path, "user", self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        version = ctx.net.crates_latest(target.package, timeout)
        return Latest(version, "crates.io") if version else Latest("", "crates.io", "crates.io did not answer")

    def install(self, ctx: "Context", target: Target) -> Action:
        return self._install(ctx, target, "install")

    def update(self, ctx: "Context", target: Target) -> Action:
        crate = installed_crates(ctx).get(target.package)
        if crate is not None and not crate.from_registry:
            return empty_action(target, "update", target.package + " was installed from " + crate.source
                                + ", not crates.io. aiup leaves it alone.")
        return self._install(ctx, target, "update")

    def remove(self, ctx: "Context", target: Target) -> Action:
        cargo = self._cargo(ctx)
        if not cargo:
            return empty_action(target, "remove", "cargo is not on PATH.")
        step = Step(argv=(cargo, "uninstall", target.package), label="cargo uninstall " + target.package)
        return Action(tool=target.package, op="remove", channel=self.name, steps=(step,))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        bin_dir = str(install_root(ctx) / "bin")
        if not path_inside(path, bin_dir):
            return None
        wanted = os.path.normcase(os.path.normpath(path))
        for crate in installed_crates(ctx).values():
            if any(os.path.normcase(os.path.normpath(_bin_path(ctx, b))) == wanted for b in crate.bins):
                return Ownership(self.name, crate.name, "exact")
        return None

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        return tuple(PackageRecord(self.name, c.name, c.version, "user", True,
                                   tuple(_bin_path(ctx, b) for b in c.bins))
                     for c in sorted(installed_crates(ctx).values()))

    def _cargo(self, ctx: "Context") -> Optional[str]:
        return which(ctx, "cargo") or which(ctx, "cargo", str(install_root(ctx) / "bin"))

    def _install(self, ctx: "Context", target: Target, op: str) -> Action:
        cargo = self._cargo(ctx)
        if not cargo:
            return empty_action(target, op, "cargo is not on PATH.")
        steps: List[Step] = []
        binstall = which(ctx, "cargo-binstall") or which(ctx, "cargo-binstall", str(install_root(ctx) / "bin"))
        if binstall:
            steps.append(Step(
                argv=(binstall, "--no-confirm", "--locked", "--disable-strategies", "quick-install", target.package),
                label="cargo binstall " + target.package, on_fail="next",
            ))
        steps.append(Step(argv=(cargo, "install", "--locked", target.package),
                          label="cargo install --locked " + target.package))
        setup = path_setup_step(ctx, str(install_root(ctx) / "bin"))
        if setup is not None:
            steps.append(setup)
        return Action(tool=target.package, op=op, channel=self.name, steps=tuple(steps))
