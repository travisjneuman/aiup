"""AUR packages through an AUR helper (paru, then yay). Design doc 6.3 and 7.2.

- Installed AUR packages are pacman's foreign packages (``pacman -Qm``).
- Latest versions come from the AUR RPC v5 ``info`` call, many packages per
  request, over HTTPS through ``ctx.net``.
- The helper always runs as the user, never under sudo. It calls sudo itself
  for the pacman part, so its steps use privilege ``helper-sudo``: the engine
  applies the sudo rules (``settings system``, explicit actions) without
  wrapping the command. aiup never runs makepkg.
- ``settings aur review`` (the default): every helper step needs the terminal,
  so the user can read the PKGBUILD. ``settings aur trust``: updates of AUR
  packages that are already installed skip the review prompts. New AUR
  installs always stay interactive.
- Removal is plain ``pacman -Rs``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlencode

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers._linux import Memo, fetch_json, setting, system_step, user_step
from aiup.providers.linux_pacman import (
    aur_helper, foreign_names, local_packages, lock_note, owners_of, pacman_present,
)

if TYPE_CHECKING:
    from aiup.engine.context import Context

AUR_RPC = "https://aur.archlinux.org/rpc/v5/info"
RPC_BATCH = 100                     # names per request; keeps the URL well under 8 KiB
RPC_MAX_BYTES = 4 * 1024 * 1024
RPC_TTL = 900.0
VCS_SUFFIXES = ("-git", "-hg", "-svn", "-bzr", "-darcs", "-fossil", "-cvs")
_MEMO = Memo()


def is_vcs(name: str) -> bool:
    """True for VCS packages, whose AUR version does not follow upstream commits."""
    return name.endswith(VCS_SUFFIXES)


def _rpc_url(names: Sequence[str]) -> str:
    """One RPC ``info`` URL for ``names``."""
    return AUR_RPC + "?" + urlencode([("arg[]", name) for name in names])


def _parse_rpc(data: object) -> Optional[Dict[str, str]]:
    """{Name: Version} from an RPC answer, or None when it is not a valid answer."""
    if not isinstance(data, dict) or data.get("type") == "error":
        return None
    results = data.get("results")
    if not isinstance(results, list):
        return None
    found: Dict[str, str] = {}
    for item in results:
        if isinstance(item, dict):
            name, version = item.get("Name"), item.get("Version")
            if isinstance(name, str) and isinstance(version, str) and version:
                found[name] = version
    return found


def aur_versions(ctx: "Context", names: Iterable[str], timeout: float) -> Dict[str, Optional[str]]:
    """AUR versions for ``names``: a version, "" when the AUR has no such package,
    or None when the AUR could not be reached. Answers are kept for 15 minutes.
    """
    wanted = sorted(set(names))
    answers: Dict[str, Optional[str]] = {}
    missing: List[str] = []
    for name in wanted:
        hit, cached = _MEMO.peek("rpc:" + name, RPC_TTL)
        if hit and isinstance(cached, str):
            answers[name] = cached
        else:
            missing.append(name)
    for start in range(0, len(missing), RPC_BATCH):
        chunk = missing[start:start + RPC_BATCH]
        parsed = _parse_rpc(fetch_json(ctx, _rpc_url(chunk), timeout, RPC_MAX_BYTES))
        for name in chunk:
            if parsed is None:
                answers[name] = None
                _MEMO.drop("rpc:" + name)
                continue
            value = parsed.get(name, "")
            _MEMO.put("rpc:" + name, value)
            answers[name] = value
    return answers


def _trusted(ctx: "Context") -> bool:
    """True with ``settings aur trust``."""
    return setting(ctx, "aur", "review") == "trust"


def _skip_review_flags(helper: str) -> Tuple[str, ...]:
    """Flags that answer the helper's review and clean prompts without asking."""
    if helper == "paru":
        return ("--noconfirm", "--skipreview")
    return ("--noconfirm", "--answerdiff", "None", "--answerclean", "None", "--answeredit", "None")


def _helper_step(ctx: "Context", helper: str, argv: Sequence[str], label: str, may_trust: bool) -> Step:
    """One helper step, run as the user; the helper runs sudo itself (``helper-sudo``).

    Review mode (or a new install) needs the terminal, so without one the
    engine defers it. Trust mode on an update skips the prompts; without a
    terminal it also passes ``-n`` to the helper's own sudo, so a needed
    password fails at once and the engine reports the tool deferred.
    """
    full: List[str] = [helper] + list(argv)
    if may_trust and _trusted(ctx):
        full.extend(_skip_review_flags(helper))
        if not ctx.interactive:
            full.extend(["--sudoflags", "-n"])
        return user_step(full, label, interactive=bool(ctx.interactive), privilege="helper-sudo")
    return user_step(full, label, interactive=True, privilege="helper-sudo")


class AurProvider(Provider):
    """AUR packages: installed state from pacman, versions from the AUR RPC."""

    name = "aur"
    oses = frozenset({"linux"})
    scope = "system"
    lane = "system"
    exclusive = True
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        """True on a pacman system with paru or yay on PATH."""
        return pacman_present(ctx) and aur_helper(ctx) is not None

    def _helper(self, ctx: "Context") -> str:
        """The helper to use. Only called after ``available``."""
        return aur_helper(ctx) or "paru"

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """The installed foreign package, or None."""
        name = target.package
        if name not in foreign_names(ctx):
            return None
        package = local_packages(ctx).get(name)
        if package is None:
            return None
        return Installed(version=package.version, path=None, scope="system", channel=self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """AUR version from the RPC. Every installed AUR package is asked for in the same request."""
        name = target.package
        if is_vcs(name):
            return Latest("", self.name, "VCS package: its AUR version does not follow upstream commits")
        names = [n for n in foreign_names(ctx) if not is_vcs(n)] + [name]
        version = aur_versions(ctx, names, timeout).get(name)
        if version is None:
            return Latest("", self.name, "the AUR could not be reached")
        if version == "":
            return Latest("", self.name, "not found in the AUR")
        return Latest(version, self.name)

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Installed AUR packages whose AUR version differs, in one batched read.

        The engine compares versions; this only drops exact matches.
        """
        local = local_packages(ctx)
        names = [n for n in foreign_names(ctx) if not is_vcs(n)]
        found: Dict[str, Latest] = {}
        for name, version in aur_versions(ctx, names, 10.0).items():
            installed = local.get(name)
            if version and installed is not None and installed.version != version:
                found[name] = Latest(version, self.name)
        return found

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Every foreign package (AUR or built by hand)."""
        local = local_packages(ctx)
        rows: List[PackageRecord] = []
        for name in sorted(foreign_names(ctx)):
            package = local.get(name)
            if package is not None:
                rows.append(PackageRecord(manager=self.name, name=name, version=package.version,
                                          scope="system", explicit=package.explicit))
        return tuple(rows)

    def install(self, ctx: "Context", target: Target) -> Action:
        """``paru -S --needed --aur PKG`` (or yay), always with the terminal for review."""
        helper = self._helper(ctx)
        step = _helper_step(ctx, helper, ("-S", "--needed", "--aur", target.package),
                            "{} -S {}".format(helper, target.package), may_trust=False)
        note = "{} shows the PKGBUILD for {} before it builds anything.".format(helper, target.package)
        return Action(tool=target.package, op="install", channel=self.name, steps=(step,), note=note)

    def update(self, ctx: "Context", target: Target) -> Action:
        """Rebuild one AUR package. Trust mode skips the review prompts."""
        helper = self._helper(ctx)
        step = _helper_step(ctx, helper, ("-S", "--needed", "--aur", target.package),
                            "{} -S {}".format(helper, target.package), may_trust=True)
        return Action(tool=target.package, op="update", channel=self.name, steps=(step,))

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``pacman -Rs PKG``."""
        argv: List[str] = ["pacman", "-Rs"]
        if not ctx.interactive:
            argv.append("--noconfirm")
        argv.extend(["--", target.package])
        step = system_step(ctx, argv, "pacman -Rs " + target.package)
        return Action(tool=target.package, op="remove", channel=self.name, steps=(step,))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """``pacman -Qo`` when the owner is a foreign package."""
        if not self.available(ctx):
            return None
        return self.owns_many(ctx, (path,)).get(path)

    def owns_many(self, ctx: "Context", paths: Sequence[str]) -> Dict[str, Ownership]:
        """pacman's batched ``pacman -Qo``, keeping the foreign (AUR) owners."""
        if not self.available(ctx):
            return {}
        resolved = {path: os.path.realpath(path) for path in paths}
        owners = owners_of(ctx, sorted(set(resolved.values())))
        if not owners:
            return {}
        foreign = foreign_names(ctx)
        result: Dict[str, Ownership] = {}
        for path, real in resolved.items():
            package = owners.get(real)
            if package is not None and package in foreign:
                result[path] = Ownership(manager=self.name, package=package, confidence="exact")
        return result

    def system_upgrade(self, ctx: "Context") -> Optional[Action]:
        """``paru -Syu`` or ``yay -Syu`` as the user: repositories and AUR in one pass."""
        if not self.available(ctx):
            return None
        helper = self._helper(ctx)
        step = _helper_step(ctx, helper, ("-Syu",), helper + " -Syu", may_trust=True)
        note = "This runs a full system upgrade with {}: {} -Syu".format(helper, helper)
        return Action(tool="system", op="update", channel=self.name, steps=(step,), note=note)

    def lock_held(self, ctx: "Context") -> str:
        """pacman's database lock covers the helper too."""
        return lock_note() if self.available(ctx) else ""
