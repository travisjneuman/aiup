"""dnf provider (Fedora, RHEL and derivatives), plus the rpm reads zypper shares.

Design doc 6.3, 7.1 and 7.3:

- Installed state comes from one ``rpm -qa`` call, cached until the rpm
  database changes. "Installed on request" comes from
  ``dnf repoquery --userinstalled``.
- Latest versions come from ``dnf repoquery`` with ``-C`` (cache only), so a
  check never downloads metadata. ``metadata_refresh`` runs ``dnf makecache``.
- dnf4 and dnf5 both work. dnf5 needs an explicit newline in ``--queryformat``;
  every format here ends in one and blank lines are skipped, so the same
  argv serves both.
- ``aiup system`` runs ``dnf upgrade --refresh``.
- Image-based Fedora (Silverblue, Kinoite, CoreOS: ``/run/ostree-booted``) is
  updated by rpm-ostree, so dnf counts as unavailable there.
- aiup never adds a repository (no COPR, no RPM Fusion). A package no enabled
  repository has is reported as not in a configured repository.
"""

from __future__ import annotations

import glob
import os
from typing import TYPE_CHECKING, Dict, FrozenSet, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Set, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Target
from aiup.providers.base import Provider
from aiup.providers._linux import (
    INVENTORY_MAX_BYTES, LOCKED_NOTE, Memo, asking_remove, is_linux, mtime_of, pidfile_held, posix_lock_held, run_c,
    system_step, which,
)

if TYPE_CHECKING:
    from aiup.engine.context import Context

OSTREE_MARKER = "/run/ostree-booted"
RPMDB_DIRS = ("/usr/lib/sysimage/rpm", "/var/lib/rpm")
RPM_QUERYFORMAT = "%{NAME}\\t%{EPOCHNUM}\\t%{VERSION}\\t%{RELEASE}\\t%{ARCH}\\t%{INSTALLTIME}\\n"
DNF4_PID_LOCKS = (
    "/var/cache/dnf/metadata_lock.pid",
    "/var/cache/dnf/download_lock.pid",
    "/var/lib/dnf/rpmdb_lock.pid",
    "/var/run/dnf/rpmdb_lock.pid",
)
MEMO_TTL = 300.0
QUERY_TIMEOUT = 20.0
_MEMO = Memo()


class RpmPackage(NamedTuple):
    """One installed rpm."""

    key: str          # "name", or "name.arch" when another arch of the same name is installed
    name: str
    arch: str
    version: str      # "[epoch:]version-release"
    installed_at: int


# ----- rpm reads shared with zypper ----------------------------------------


def rpmdb_stamp() -> str:
    """Changes whenever an rpm transaction writes the database."""
    parts: List[str] = []
    for folder in RPMDB_DIRS:
        parts.append(str(mtime_of(folder)))
        for name in ("rpmdb.sqlite", "rpmdb.sqlite-wal", "Packages"):
            parts.append(str(mtime_of(os.path.join(folder, name))))
    return ":".join(parts)


def _evr(epoch: str, version: str, release: str) -> str:
    """``epoch:version-release``, without a zero epoch."""
    head = "" if epoch in ("", "0", "(none)") else epoch + ":"
    return "{}{}-{}".format(head, version, release)


def _parse_rpm_rows(text: str) -> List[RpmPackage]:
    """Rows of ``RPM_QUERYFORMAT`` output. Signing keys (gpg-pubkey) are skipped."""
    rows: List[RpmPackage] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 6 or parts[0] in ("gpg-pubkey", "gpg-pubkey-release"):
            continue
        name, epoch, version, release, arch, when = parts
        stamp = int(when) if when.isdigit() else 0
        rows.append(RpmPackage(name, name, arch, _evr(epoch, version, release), stamp))
    return rows


def _key_rows(rows: Sequence[RpmPackage]) -> Dict[str, RpmPackage]:
    """Key by name; a name installed for two arches gets ``name.arch`` keys.

    Install-only packages (kernels) keep the newest installed copy.
    """
    arches: Dict[str, Set[str]] = {}
    for row in rows:
        arches.setdefault(row.name, set()).add(row.arch)
    keyed: Dict[str, RpmPackage] = {}
    for row in rows:
        key = row.name if len(arches[row.name]) == 1 else "{}.{}".format(row.name, row.arch)
        current = keyed.get(key)
        if current is None or row.installed_at >= current.installed_at:
            keyed[key] = row._replace(key=key)
    return keyed


def rpm_packages(ctx: "Context") -> Dict[str, RpmPackage]:
    """Every installed rpm, from one ``rpm -qa`` call per database change."""

    def produce() -> Dict[str, RpmPackage]:
        result = run_c(ctx, ("rpm", "-qa", "--qf", RPM_QUERYFORMAT), timeout=QUERY_TIMEOUT,
                       max_bytes=INVENTORY_MAX_BYTES)
        return _key_rows(_parse_rpm_rows(result.out)) if result.code == 0 else {}

    return _MEMO.get("rpm:" + rpmdb_stamp(), MEMO_TTL, produce)


def rpm_installed(ctx: "Context", name: str) -> Optional[RpmPackage]:
    """The installed rpm called ``name`` (any arch), or None."""
    packages = rpm_packages(ctx)
    if name in packages:
        return packages[name]
    for package in packages.values():
        if package.name == name:
            return package
    return None


def rpm_owner(ctx: "Context", path: str) -> Optional[str]:
    """``rpm -qf``: the package that owns ``path``, or None."""
    result = run_c(ctx, ("rpm", "-qf", "--qf", "%{NAME}\\n", path))
    if result.code != 0:
        return None
    for line in result.out.splitlines():
        word = line.strip()
        if word and " " not in word:
            return word
    return None


def rpm_lock_held() -> bool:
    """True while an rpm transaction holds the database lock."""
    return posix_lock_held([os.path.join(folder, ".rpm.lock") for folder in RPMDB_DIRS])


def rpm_owns(ctx: "Context", manager: str, path: str) -> Optional[Ownership]:
    """Ownership for ``path`` (tried as given, then resolved)."""
    for candidate in (path, os.path.realpath(path)):
        package = rpm_owner(ctx, candidate)
        if package is not None:
            return Ownership(manager=manager, package=package, confidence="exact")
    return None


OWNS_BATCH = 200
_NOT_OWNED = " is not owned by any package"


def rpm_owners(ctx: "Context", paths: Sequence[str]) -> Dict[str, str]:
    """Batched ``rpm -qf``: {path: package} for the paths rpm owns.

    rpm prints one line per existing path, in order: the owner's name or
    "file PATH is not owned by any package". A path two packages own (multilib)
    prints two names, so when the line count or a "not owned" line does not
    line up with the paths asked, the batch is read again one path at a time.
    """
    wanted = [path for path in dict.fromkeys(paths) if os.path.isabs(path) and os.path.lexists(path)]
    found: Dict[str, str] = {}
    for start in range(0, len(wanted), OWNS_BATCH):
        batch = wanted[start:start + OWNS_BATCH]
        lines = _rpm_qf_lines(ctx, batch)
        if lines is None:
            for path in batch:
                package = rpm_owner(ctx, path)
                if package is not None:
                    found[path] = package
            continue
        for path, line in zip(batch, lines):
            if line and not line.endswith(_NOT_OWNED):
                found[path] = line
    return found


def _rpm_qf_lines(ctx: "Context", batch: Sequence[str]) -> Optional[List[str]]:
    """One stdout line per path ("" for not owned), or None when they do not line up."""
    result = run_c(ctx, ("rpm", "-qf", "--qf", "%{NAME}\\n") + tuple(batch), max_bytes=INVENTORY_MAX_BYTES)
    if result.code is None:
        return None
    lines = [line.strip() for line in result.out.splitlines() if line.strip()]
    if len(lines) != len(batch):
        return None
    out: List[str] = []
    for path, line in zip(batch, lines):
        if line.endswith(_NOT_OWNED):
            if line != "file " + path + _NOT_OWNED:
                return None
            out.append("")
        elif " " in line:
            return None
        else:
            out.append(line)
    return out


def rpm_owns_many(ctx: "Context", manager: str, paths: Sequence[str]) -> Dict[str, Ownership]:
    """:func:`rpm_owns` for many paths with batched ``rpm -qf`` reads."""
    real = {path: os.path.realpath(path) for path in paths}
    owners = rpm_owners(ctx, list(paths) + list(real.values()))
    result: Dict[str, Ownership] = {}
    for path in paths:
        package = owners.get(path) or owners.get(real[path])
        if package:
            result[path] = Ownership(manager=manager, package=package, confidence="exact")
    return result


def rpm_inventory(ctx: "Context", manager: str, explicit: FrozenSet[str]) -> Tuple[PackageRecord, ...]:
    """Inventory rows; ``explicit`` holds the names installed on request."""
    return tuple(PackageRecord(manager=manager, name=p.key, version=p.version, scope="system",
                               explicit=p.name in explicit)
                 for p in sorted(rpm_packages(ctx).values()))


def interactive_flags(ctx: "Context") -> Tuple[str, ...]:
    """``-y`` without a terminal; with one, the manager asks on screen."""
    return () if ctx.interactive else ("-y",)


# ----- dnf ---------------------------------------------------------------


def _dnf(*words: str) -> Tuple[str, ...]:
    """A quiet, cache-only dnf read."""
    return ("dnf", "-q", "-C") + tuple(words)


def _parse_name_evr(text: str) -> Dict[str, str]:
    """``name arch evr`` lines -> {name: evr}, preferring the native or noarch row."""
    found: Dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        name, arch, evr = parts
        if name not in found or arch in ("noarch", os.uname().machine):
            found[name] = evr
    return found


def user_installed(ctx: "Context") -> FrozenSet[str]:
    """Names dnf records as installed on request."""

    def produce() -> FrozenSet[str]:
        result = run_c(ctx, _dnf("repoquery", "--userinstalled", "--qf", "%{name}\\n"),
                       timeout=QUERY_TIMEOUT, max_bytes=INVENTORY_MAX_BYTES)
        return frozenset(result.out.split()) if result.code == 0 else frozenset()

    return _MEMO.get("userinstalled:" + rpmdb_stamp(), MEMO_TTL, produce)


def _cache_stamp() -> str:
    """Changes when dnf refreshes its metadata cache."""
    return str(max((mtime_of(path) for path in glob.glob("/var/cache/dnf/*") + glob.glob("/var/cache/libdnf5/*")),
                   default=0.0))


def available_versions(ctx: "Context", names: Sequence[str], timeout: float) -> Dict[str, str]:
    """Newest version in the enabled repositories for each of ``names`` ("" when none)."""
    stamp = _cache_stamp()
    answers: Dict[str, str] = {}
    missing: List[str] = []
    for name in sorted(set(names)):
        hit, value = _MEMO.peek("avail:{}:{}".format(stamp, name), MEMO_TTL)
        if hit and isinstance(value, str):
            answers[name] = value
        else:
            missing.append(name)
    if missing:
        argv = _dnf("repoquery", "--available", "--latest-limit", "1", "--qf", "%{name} %{arch} %{evr}\\n") + tuple(missing)
        result = run_c(ctx, argv, timeout=max(timeout, 5.0), max_bytes=INVENTORY_MAX_BYTES)
        if result.code != 0:
            return answers
        parsed = _parse_name_evr(result.out)
        for name in missing:
            answers[name] = parsed.get(name, "")
            _MEMO.put("avail:{}:{}".format(stamp, name), answers[name])
    return answers


class DnfProvider(Provider):
    """rpm packages through dnf (dnf4 or dnf5)."""

    name = "dnf"
    oses = frozenset({"linux"})
    scope = "system"
    lane = "system"
    exclusive = True
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        """True with dnf and rpm on PATH, on a system not booted from an ostree image."""
        return (is_linux(ctx) and which(ctx, "dnf") is not None and which(ctx, "rpm") is not None
                and not os.path.exists(OSTREE_MARKER))

    def can_provide(self, ctx: "Context", target: Target) -> bool:
        """True when an enabled repository has the package."""
        return self.available(ctx) and bool(available_versions(ctx, (target.package,), 5.0).get(target.package))

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """Installed version from rpm, or None."""
        package = rpm_installed(ctx, target.package)
        if package is None:
            return None
        return Installed(version=package.version, path=None, scope="system", channel=self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """Newest version in the cached metadata of the enabled repositories."""
        found = available_versions(ctx, (target.package,), timeout)
        if target.package not in found:
            return Latest("", self.name, "dnf has no cached metadata yet")
        version = found[target.package]
        if version:
            return Latest(version, self.name)
        return Latest("", self.name, "not in a configured repository")

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Pending upgrades for installed packages, from the cached metadata."""
        argv = _dnf("repoquery", "--upgrades", "--latest-limit", "1", "--qf", "%{name} %{arch} %{evr}\\n")
        result = run_c(ctx, argv, timeout=QUERY_TIMEOUT, max_bytes=INVENTORY_MAX_BYTES)
        if result.code != 0:
            return {}
        return {name: Latest(evr, self.name) for name, evr in _parse_name_evr(result.out).items()}

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Every installed rpm."""
        return rpm_inventory(ctx, self.name, user_installed(ctx))

    def install(self, ctx: "Context", target: Target) -> Action:
        """``dnf install PKG``."""
        argv = ("dnf", "install") + interactive_flags(ctx) + (target.package,)
        step = system_step(ctx, argv, "dnf install " + target.package)
        return Action(tool=target.package, op="install", channel=self.name, steps=(step,))

    def update(self, ctx: "Context", target: Target) -> Action:
        """``dnf upgrade PKG``."""
        argv = ("dnf", "upgrade") + interactive_flags(ctx) + (target.package,)
        step = system_step(ctx, argv, "dnf upgrade " + target.package)
        return Action(tool=target.package, op="update", channel=self.name, steps=(step,))

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``dnf remove PKG``. Asks on the terminal, since dnf may remove more; deferred without one."""
        return asking_remove(ctx, self.name, target.package, ("dnf", "remove", target.package))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """``rpm -qf``."""
        return rpm_owns(ctx, self.name, path) if self.available(ctx) else None

    def owns_many(self, ctx: "Context", paths: Sequence[str]) -> Dict[str, Ownership]:
        """Batched ``rpm -qf`` for every path."""
        return rpm_owns_many(ctx, self.name, paths) if self.available(ctx) else {}

    def system_upgrade(self, ctx: "Context") -> Optional[Action]:
        """``dnf upgrade --refresh``."""
        if not self.available(ctx):
            return None
        argv = ("dnf", "upgrade", "--refresh") + interactive_flags(ctx)
        step = system_step(ctx, argv, "dnf upgrade --refresh")
        return Action(tool="system", op="update", channel=self.name, steps=(step,),
                      note="This runs sudo dnf upgrade --refresh.")

    def metadata_refresh(self, ctx: "Context") -> Optional[Action]:
        """``dnf makecache``: downloads repository metadata, changes no package."""
        if not self.available(ctx):
            return None
        step = system_step(ctx, ("dnf", "makecache"), "dnf makecache")
        return Action(tool="dnf", op="update", channel=self.name, steps=(step,))

    def lock_held(self, ctx: "Context") -> str:
        """``LOCKED_NOTE`` while rpm or dnf holds a lock."""
        if rpm_lock_held() or any(pidfile_held(path) for path in DNF4_PID_LOCKS):
            return LOCKED_NOTE
        if posix_lock_held(glob.glob("/run/dnf/*.lock") + glob.glob("/var/lib/dnf/*.lock")):
            return LOCKED_NOTE
        return ""
