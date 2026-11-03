"""Nix packages in the user's ``nix profile``. Design doc 6.3.

- Everything runs as the user. Every call passes
  ``--extra-experimental-features "nix-command flakes"``, so it works on a
  Nix install that has not turned those on.
- ``nix profile list --json`` has two shapes: ``elements`` as an object keyed
  by name (newer Nix) or as a list (older Nix). Both are read; with the list
  shape, upgrade and remove use the element's index.
- Versions come from the store path (``/nix/store/<hash>-<name>-<version>``).
- Latest versions come from ``nix eval`` on the element's flake reference,
  which can download the flake. It runs only with the engine's timeout.
- A profile managed by ``nix-env`` cannot be read by ``nix profile``; then
  this provider counts as unavailable.
"""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING, Iterable, List, Mapping, NamedTuple, Optional, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Target
from aiup.providers.base import Provider
from aiup.providers._linux import INVENTORY_MAX_BYTES, Memo, is_linux, run_c, user_step, which

if TYPE_CHECKING:
    from aiup.engine.context import Context

FEATURES = ("--extra-experimental-features", "nix-command flakes")
DEFAULT_FLAKE = "nixpkgs"
STORE = "/nix/store/"
MEMO_TTL = 300.0
QUERY_TIMEOUT = 20.0
_STORE_NAME = re.compile(r"^/nix/store/[0-9a-z]{32}-(.+)$")
_VERSION_START = re.compile(r"-(?=\d)")
_OUTPUT_SUFFIX = re.compile(r"-(bin|dev|devdoc|doc|info|lib|man|out|debug|static)$")
_MEMO = Memo()


class ProfileElement(NamedTuple):
    """One package in the profile."""

    name: str              # what ``nix profile upgrade/remove`` takes
    attr: str              # last part of attrPath, for example "hello"
    attr_path: str         # "legacyPackages.x86_64-linux.hello"
    flake: str             # "flake:nixpkgs" or "github:NixOS/nixpkgs/..."
    store_paths: Tuple[str, ...]
    version: str


def nix_argv(*words: str) -> Tuple[str, ...]:
    """``nix`` with the needed experimental features turned on."""
    return ("nix",) + FEATURES + tuple(words)


def store_version(path: str) -> str:
    """Version from a store path: the part after the first ``-`` that a digit follows.

    Outputs other than ``out`` end in a name (``hello-2.12.1-man``); that is dropped.
    """
    found = _STORE_NAME.match(path)
    if not found:
        return ""
    parts = _VERSION_START.split(found.group(1), maxsplit=1)
    return _OUTPUT_SUFFIX.sub("", parts[1]) if len(parts) == 2 else ""


def _element(name: str, data: Mapping[str, object]) -> Optional[ProfileElement]:
    """One element from the JSON, or None when it is not a package."""
    raw_attr = data.get("attrPath")
    attr_path = raw_attr if isinstance(raw_attr, str) else ""
    raw_flake = data.get("originalUrl") or data.get("url") or ""
    flake = raw_flake if isinstance(raw_flake, str) else ""
    raw_paths = data.get("storePaths")
    paths = tuple(p for p in raw_paths if isinstance(p, str)) if isinstance(raw_paths, list) else ()
    attr = attr_path.rsplit(".", 1)[-1] if attr_path else name
    version = store_version(paths[0]) if paths else ""
    if not attr:
        return None
    return ProfileElement(name or attr, attr, attr_path, flake, paths, version)


def parse_profile(text: str) -> Tuple[ProfileElement, ...]:
    """Elements of ``nix profile list --json`` in either shape."""
    try:
        data = json.loads(text)
    except ValueError:
        return ()
    elements = data.get("elements") if isinstance(data, dict) else None
    found: List[ProfileElement] = []
    if isinstance(elements, dict):
        for name, item in elements.items():
            if isinstance(item, dict) and isinstance(name, str):
                element = _element(name, item)
                if element is not None:
                    found.append(element)
    elif isinstance(elements, list):
        for index, item in enumerate(elements):
            if isinstance(item, dict):
                element = _element(str(index), item)
                if element is not None:
                    found.append(element)
    return tuple(found)


def profile(ctx: "Context") -> Optional[Tuple[ProfileElement, ...]]:
    """The profile's elements, or None when ``nix profile`` cannot read it."""

    def produce() -> Optional[Tuple[ProfileElement, ...]]:
        result = run_c(ctx, nix_argv("profile", "list", "--json"), timeout=QUERY_TIMEOUT,
                       max_bytes=INVENTORY_MAX_BYTES)
        return parse_profile(result.out) if result.code == 0 else None

    return _MEMO.get("profile:{}".format(_profile_stamp()), MEMO_TTL, produce)


def _profile_stamp() -> str:
    """Changes when the profile link moves to a new generation."""
    for path in (os.path.expanduser("~/.local/state/nix/profiles/profile"), os.path.expanduser("~/.nix-profile")):
        try:
            return os.readlink(path)
        except OSError:
            continue
    return ""


def find_element(ctx: "Context", attr: str) -> Optional[ProfileElement]:
    """The element installed from ``attr`` (matched on the attribute path), or None."""
    for element in profile(ctx) or ():
        if element.attr_path == attr or element.attr_path.endswith("." + attr) or element.name == attr:
            return element
    return None


def _flake_ref(element: Optional[ProfileElement], attr: str) -> str:
    """``<flake>#<attrPath>`` for ``nix eval`` and ``nix profile install``."""
    if element is not None and element.flake and element.attr_path:
        return "{}#{}".format(element.flake, element.attr_path)
    return "{}#{}".format(DEFAULT_FLAKE, attr)


class NixProvider(Provider):
    """Packages in the user's ``nix profile``."""

    name = "nix"
    oses = frozenset({"linux"})
    scope = "user"
    lane = "nix"
    exclusive = False
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        """True with nix on PATH and a profile ``nix profile`` can read."""
        return is_linux(ctx) and which(ctx, "nix") is not None and profile(ctx) is not None

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """The profile element for the target, or None."""
        element = find_element(ctx, target.package)
        if element is None:
            return None
        path = element.store_paths[0] if element.store_paths else None
        return Installed(version=element.version, path=path, scope="user", channel=self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """``nix eval --raw <flake>#<attr>.version``."""
        ref = _flake_ref(find_element(ctx, target.package), target.package) + ".version"

        def produce() -> Latest:
            result = run_c(ctx, nix_argv("eval", "--raw", ref), timeout=max(timeout, 5.0))
            version = result.out.strip()
            if result.code == 0 and version and "\n" not in version:
                return Latest(version, self.name)
            if result.code is None:
                return Latest("", self.name, "nix eval did not finish in time")
            return Latest("", self.name, "the flake has no version for {}".format(target.package))

        return _MEMO.get("eval:" + ref, MEMO_TTL, produce)

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Nothing in bulk: each check needs its own ``nix eval``."""
        return {}

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Every element of the profile."""
        return tuple(PackageRecord(manager=self.name, name=e.attr, version=e.version, scope="user",
                                   explicit=True, paths=e.store_paths)
                     for e in profile(ctx) or ())

    def install(self, ctx: "Context", target: Target) -> Action:
        """``nix profile install nixpkgs#ATTR``."""
        ref = _flake_ref(None, target.package)
        step = user_step(nix_argv("profile", "install", ref), "nix profile install " + ref)
        return Action(tool=target.package, op="install", channel=self.name, steps=(step,))

    def update(self, ctx: "Context", target: Target) -> Action:
        """``nix profile upgrade NAME``."""
        element = find_element(ctx, target.package)
        name = element.name if element is not None else target.package
        step = user_step(nix_argv("profile", "upgrade", name), "nix profile upgrade " + name)
        return Action(tool=target.package, op="update", channel=self.name, steps=(step,))

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``nix profile remove NAME``. The store keeps the files until garbage collection."""
        element = find_element(ctx, target.package)
        name = element.name if element is not None else target.package
        step = user_step(nix_argv("profile", "remove", name), "nix profile remove " + name)
        return Action(tool=target.package, op="remove", channel=self.name, steps=(step,))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """A path that resolves into the store path of a profile element."""
        real = os.path.realpath(path)
        if not real.startswith(STORE):
            return None
        for element in profile(ctx) or ():
            for store_path in element.store_paths:
                if real == store_path or real.startswith(store_path.rstrip("/") + "/"):
                    return Ownership(manager=self.name, package=element.attr, confidence="exact")
        return None

    def forget(self) -> None:
        """Drop cached reads after a step. With the older per-user profile layout the
        profile link never moves, so the generation stamp alone would not notice."""
        _MEMO.clear()
