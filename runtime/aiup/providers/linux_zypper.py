"""zypper provider (openSUSE and SUSE). Design doc 6.3, 7.1 and 7.3.

The catalog has no zypper column (open question 4 is settled that way). This
provider still reports installed packages, ownership and ``aiup system``.
For a tool it can only serve a dnf-column package name when the same name
exists in an enabled zypper repository; the engine decides whether to try.

- Installed state comes from rpm (shared with the dnf provider).
- Latest versions come from zypper's XML output with ``--no-refresh``, so a
  check never downloads metadata. ``metadata_refresh`` runs ``zypper refresh``.
- ``aiup system``: ``zypper dup`` on Tumbleweed and Slowroll, which only
  support distribution upgrades, and ``zypper update`` everywhere else.
- Transactional systems (MicroOS, Aeon, Kalpa) are updated with
  transactional-update, so zypper counts as unavailable there.
- aiup never adds a repository.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from typing import TYPE_CHECKING, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers.linux_dnf import (
    rpm_installed, rpm_inventory, rpm_lock_held, rpm_owns, rpm_owns_many, rpmdb_stamp,
)
from aiup.providers._linux import (
    INVENTORY_MAX_BYTES, LOCKED_NOTE, Memo, asking_remove, distro_ids, is_linux, mtime_of, pidfile_held, run_c,
    system_step, which,
)
from aiup.versions import version_cmp

if TYPE_CHECKING:
    from aiup.engine.context import Context

ZYPP_PID_FILES = ("/run/zypp.pid", "/var/run/zypp.pid")
ROLLING_IDS = ("opensuse-tumbleweed", "opensuse-slowroll")
SYSTEM_REPO = "@System"
MEMO_TTL = 300.0
QUERY_TIMEOUT = 30.0
_MEMO = Memo()


def _zypper_read(*words: str) -> Tuple[str, ...]:
    """A zypper read: XML output, no prompts, no metadata download."""
    return ("zypper", "--xmlout", "--non-interactive", "--no-refresh") + tuple(words)


def _xml_root(text: str) -> Optional[ElementTree.Element]:
    """The parsed XML stream, or None when zypper printed something else."""
    start = text.find("<")
    if start < 0:
        return None
    try:
        return ElementTree.fromstring(text[start:])
    except ElementTree.ParseError:
        return None


def _repo_stamp() -> str:
    """Changes when zypper refreshes its repository cache."""
    return str(mtime_of("/var/cache/zypp/solv") + mtime_of("/var/cache/zypp/raw"))


def parse_updates(text: str) -> Dict[str, str]:
    """``list-updates`` XML: {name: new edition} for packages."""
    root = _xml_root(text)
    found: Dict[str, str] = {}
    if root is None:
        return found
    for item in root.iter("update"):
        name, edition = item.get("name") or "", item.get("edition") or ""
        if item.get("kind", "package") == "package" and name and edition:
            found[name] = edition
    return found


def parse_search(text: str, name: str) -> str:
    """``search --details`` XML: the newest repository edition of ``name``, or ""."""
    root = _xml_root(text)
    best = ""
    if root is None:
        return best
    for item in root.iter("solvable"):
        if item.get("name") != name or item.get("kind", "package") != "package":
            continue
        repo = item.get("repository") or ""
        edition = item.get("edition") or ""
        if not edition or repo in ("", SYSTEM_REPO, "(System Packages)"):
            continue
        if not best or version_cmp(edition, best, "rpm") > 0:
            best = edition
    return best


def pending_updates(ctx: "Context", timeout: float = QUERY_TIMEOUT) -> Optional[Dict[str, str]]:
    """Pending package updates from the cached metadata, or None when zypper failed."""

    def produce() -> Optional[Dict[str, str]]:
        result = run_c(ctx, _zypper_read("list-updates", "--type", "package"), timeout=max(timeout, 10.0),
                       max_bytes=INVENTORY_MAX_BYTES)
        return parse_updates(result.out) if result.code == 0 else None

    return _MEMO.get("updates:{}:{}".format(rpmdb_stamp(), _repo_stamp()), MEMO_TTL, produce)


def repo_version(ctx: "Context", name: str, timeout: float) -> Optional[str]:
    """Newest edition of ``name`` in the enabled repositories: "" when none, None on failure."""

    def produce() -> Optional[str]:
        argv = _zypper_read("search", "--match-exact", "--details", "--type", "package", name)
        result = run_c(ctx, argv, timeout=max(timeout, 5.0), max_bytes=INVENTORY_MAX_BYTES)
        # zypper exits 104 when nothing matched.
        if result.code == 104:
            return ""
        return parse_search(result.out, name) if result.code == 0 else None

    return _MEMO.get("search:{}:{}".format(_repo_stamp(), name), MEMO_TTL, produce)


def _global_flags(ctx: "Context") -> Tuple[str, ...]:
    """``--non-interactive`` without a terminal; with one, zypper asks on screen."""
    return () if ctx.interactive else ("--non-interactive",)


def _rolling(ctx: "Context") -> bool:
    """True on Tumbleweed and Slowroll."""
    return any(ident in ROLLING_IDS for ident in distro_ids(ctx))


class ZypperProvider(Provider):
    """rpm packages through zypper."""

    name = "zypper"
    oses = frozenset({"linux"})
    scope = "system"
    lane = "system"
    exclusive = True
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        """True with zypper and rpm on PATH, on a system that is not transactional."""
        return (is_linux(ctx) and which(ctx, "zypper") is not None and which(ctx, "rpm") is not None
                and which(ctx, "transactional-update") is None)

    def can_provide(self, ctx: "Context", target: Target) -> bool:
        """True when an enabled repository has the package."""
        return self.available(ctx) and bool(repo_version(ctx, target.package, 5.0))

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """Installed version from rpm, or None."""
        package = rpm_installed(ctx, target.package)
        if package is None:
            return None
        return Installed(version=package.version, path=None, scope="system", channel=self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """Pending update or newest repository edition, from the cached metadata."""
        installed = rpm_installed(ctx, target.package)
        if installed is not None:
            updates = pending_updates(ctx, timeout)
            if updates is not None and target.package in updates:
                return Latest(updates[target.package], self.name)
        version = repo_version(ctx, target.package, timeout)
        if version is None:
            return Latest("", self.name, "zypper could not read its repository cache")
        if not version:
            return Latest("", self.name, "not in a configured repository")
        if installed is not None and version_cmp(version, installed.version, "rpm") < 0:
            return Latest(installed.version, self.name)
        return Latest(version, self.name)

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Every pending package update, in one read."""
        updates = pending_updates(ctx) or {}
        return {name: Latest(version, self.name) for name, version in updates.items()}

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Every installed rpm. Explicit marks come from zypper's ``--userinstalled`` query."""
        return rpm_inventory(ctx, self.name, self._user_installed(ctx))

    def _user_installed(self, ctx: "Context") -> FrozenSet[str]:
        """Names installed on request (``zypper search --userinstalled``)."""

        def produce() -> FrozenSet[str]:
            result = run_c(ctx, _zypper_read("search", "--userinstalled", "--type", "package"),
                           timeout=QUERY_TIMEOUT, max_bytes=INVENTORY_MAX_BYTES)
            root = _xml_root(result.out) if result.code == 0 else None
            if root is None:
                return frozenset()
            return frozenset(item.get("name") or "" for item in root.iter("solvable")) - {""}

        return _MEMO.get("userinstalled:" + rpmdb_stamp(), MEMO_TTL, produce)

    def _step(self, ctx: "Context", words: Sequence[str], label: str) -> Step:
        """A sudo zypper step with the right prompt flags."""
        argv: List[str] = ["zypper"] + list(_global_flags(ctx)) + list(words)
        return system_step(ctx, argv, label)

    def install(self, ctx: "Context", target: Target) -> Action:
        """``zypper install PKG``."""
        step = self._step(ctx, ("install", target.package), "zypper install " + target.package)
        return Action(tool=target.package, op="install", channel=self.name, steps=(step,))

    def update(self, ctx: "Context", target: Target) -> Action:
        """``zypper update PKG``."""
        step = self._step(ctx, ("update", target.package), "zypper update " + target.package)
        return Action(tool=target.package, op="update", channel=self.name, steps=(step,))

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``zypper remove PKG``. Asks on the terminal, since zypper may remove more; deferred without one."""
        return asking_remove(ctx, self.name, target.package, ("zypper", "remove", target.package))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """``rpm -qf``."""
        return rpm_owns(ctx, self.name, path) if self.available(ctx) else None

    def owns_many(self, ctx: "Context", paths: Sequence[str]) -> Dict[str, Ownership]:
        """Batched ``rpm -qf`` for every path."""
        return rpm_owns_many(ctx, self.name, paths) if self.available(ctx) else {}

    def system_upgrade(self, ctx: "Context") -> Optional[Action]:
        """``zypper dup`` on Tumbleweed and Slowroll, ``zypper update`` elsewhere."""
        if not self.available(ctx):
            return None
        command = "dup" if _rolling(ctx) else "update"
        step = self._step(ctx, (command,), "zypper " + command)
        return Action(tool="system", op="update", channel=self.name, steps=(step,),
                      note="This runs sudo zypper {}.".format(command))

    def metadata_refresh(self, ctx: "Context") -> Optional[Action]:
        """``zypper refresh``: downloads repository metadata, changes no package."""
        if not self.available(ctx):
            return None
        step = system_step(ctx, ("zypper", "--non-interactive", "refresh"), "zypper refresh")
        return Action(tool="zypper", op="update", channel=self.name, steps=(step,))

    def lock_held(self, ctx: "Context") -> str:
        """``LOCKED_NOTE`` while zypper (or another libzypp user) or rpm holds a lock."""
        if any(pidfile_held(path) for path in ZYPP_PID_FILES) or rpm_lock_held():
            return LOCKED_NOTE
        return ""

