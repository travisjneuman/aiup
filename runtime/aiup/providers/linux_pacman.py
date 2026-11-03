"""pacman provider (Arch and derivatives), plus helpers the Linux providers share.

Rules from design doc sections 6.3, 7.1 and 7.3:

- pacman cannot update one package safely (``targeted_update = False``).
  Every update is a full ``pacman -Syu``. ``pacman -Sy PKG`` is never built:
  it is a partial upgrade, which Arch does not support.
- A new install uses ``pacman -S --needed PKG`` only when the system is in
  step with its package databases and those databases match the mirrors.
  Otherwise the install runs as ``pacman -Syu --needed PKG``, a full upgrade
  with the install, and the action's note says so before anything runs.
- Latest versions are read offline first. ``checkupdates`` (pacman-contrib)
  refreshes a private copy of the sync databases under aiup's cache folder
  with fakeroot, so the real databases are never touched and no root is used.
  Without it, the local sync databases answer.
- Packages held by ``IgnorePkg`` or ``IgnoreGroup`` in pacman.conf are left
  alone and reported as held.
- Foreign packages (``pacman -Qm``: AUR or hand built) belong to the ``aur``
  provider when an AUR helper exists.

The helpers every Linux provider shares (``run_c``, ``which``, ``setting``,
the lock checks and ``Memo``) live in ``_linux.py``.
"""

from __future__ import annotations

import fnmatch
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Dict, FrozenSet, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers._linux import INVENTORY_MAX_BYTES, LOCKED_NOTE, Memo, is_linux, mtime_of, run_c, system_step, which
from aiup.providers.base import Provider

if TYPE_CHECKING:
    from aiup.engine.context import Context


# ---------------------------------------------------------------------------
# pacman local and sync database
# ---------------------------------------------------------------------------

PACMAN_CONF = "/etc/pacman.conf"
DEFAULT_DBPATH = "/var/lib/pacman/"
METADATA_TTL = 900.0                 # section 9.1, package-manager metadata
MEMO_TTL = 300.0
_DESC_MAX = 256 * 1024
_MEMO = Memo()


class LocalPackage(NamedTuple):
    """One package from pacman's local database."""

    name: str
    version: str
    explicit: bool


def dbpath() -> str:
    """pacman's DBPath from pacman.conf, with a trailing slash."""
    value = DEFAULT_DBPATH
    try:
        with open(PACMAN_CONF, "r", encoding="utf-8", errors="replace") as handle:
            section = ""
            for raw in handle.read(256 * 1024).splitlines():
                line = raw.split("#", 1)[0].strip()
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1].strip()
                elif section == "options" and "=" in line:
                    key, _, rest = line.partition("=")
                    if key.strip() == "DBPath" and rest.strip().startswith("/"):
                        value = rest.strip()
    except OSError:
        pass
    return value if value.endswith("/") else value + "/"


def pacman_present(ctx: "Context") -> bool:
    """True when this is a pacman system (not the pacman game on other distros)."""
    return (is_linux(ctx) and which(ctx, "pacman") is not None
            and os.path.isfile(PACMAN_CONF) and os.path.isdir(dbpath() + "local"))


def lock_note() -> str:
    """``LOCKED_NOTE`` when pacman's database lock exists, else ""."""
    return LOCKED_NOTE if os.path.exists(dbpath() + "db.lck") else ""


def _parse_desc(text: str) -> Dict[str, List[str]]:
    """Sections of a local ``desc`` file: ``%NAME%`` -> lines."""
    sections: Dict[str, List[str]] = {}
    current = ""
    for line in text.splitlines():
        if line.startswith("%") and line.endswith("%") and len(line) > 2:
            current = line[1:-1]
            sections[current] = []
        elif current and line:
            sections[current].append(line)
    return sections


def _read_local_db(ctx: "Context") -> Dict[str, LocalPackage]:
    """Every installed package, read from ``<DBPath>/local/*/desc`` directly."""
    packages: Dict[str, LocalPackage] = {}
    local = Path(dbpath()) / "local"
    try:
        entries = list(os.scandir(str(local)))
    except OSError:
        return _read_local_cli(ctx)
    for entry in entries:
        if not entry.is_dir(follow_symlinks=False):
            continue
        try:
            with open(os.path.join(entry.path, "desc"), "r", encoding="utf-8", errors="replace") as handle:
                sections = _parse_desc(handle.read(_DESC_MAX))
        except OSError:
            continue
        name = (sections.get("NAME") or [""])[0]
        version = (sections.get("VERSION") or [""])[0]
        if not name or not version:
            continue
        reason = (sections.get("REASON") or ["0"])[0]
        packages[name] = LocalPackage(name, version, reason != "1")
    return packages


def _read_local_cli(ctx: "Context") -> Dict[str, LocalPackage]:
    """Fallback when the local database folder cannot be listed: ``pacman -Q``."""
    listed = run_c(ctx, ("pacman", "-Q"), max_bytes=INVENTORY_MAX_BYTES)
    explicit = run_c(ctx, ("pacman", "-Qqe"), max_bytes=INVENTORY_MAX_BYTES)
    wanted = set(explicit.out.split()) if explicit.code == 0 else set()
    packages: Dict[str, LocalPackage] = {}
    if listed.code != 0:
        return packages
    for line in listed.out.splitlines():
        parts = line.split()
        if len(parts) == 2:
            packages[parts[0]] = LocalPackage(parts[0], parts[1], parts[0] in wanted)
    return packages


def local_packages(ctx: "Context") -> Dict[str, LocalPackage]:
    """Installed packages, cached until the local database changes."""
    stamp = "local:{}".format(mtime_of(dbpath() + "local"))
    return _MEMO.get(stamp, MEMO_TTL, lambda: _read_local_db(ctx))


def foreign_names(ctx: "Context") -> FrozenSet[str]:
    """Installed packages that no configured repository has (``pacman -Qqm``)."""
    stamp = "foreign:{}:{}".format(mtime_of(dbpath() + "local"), mtime_of(dbpath() + "sync"))

    def produce() -> FrozenSet[str]:
        result = run_c(ctx, ("pacman", "-Qqm"), max_bytes=INVENTORY_MAX_BYTES)
        # Exit 1 with no output means "no foreign packages".
        if result.code in (0, 1):
            return frozenset(result.out.split())
        return frozenset()

    return _MEMO.get(stamp, MEMO_TTL, produce)


def aur_helper(ctx: "Context") -> Optional[str]:
    """``paru``, then ``yay``, when one is on PATH."""
    for helper in ("paru", "yay"):
        if which(ctx, helper) is not None:
            return helper
    return None


def _conf_list(ctx: "Context", directive: str) -> Tuple[str, ...]:
    """Values of one pacman.conf directive through ``pacman-conf``."""
    result = run_c(ctx, ("pacman-conf", directive))
    if result.code != 0:
        return ()
    words: List[str] = []
    for line in result.out.splitlines():
        words.extend(line.split())
    return tuple(words)


def ignored_patterns(ctx: "Context") -> Tuple[str, ...]:
    """IgnorePkg patterns plus every member of each IgnoreGroup."""

    def produce() -> Tuple[str, ...]:
        if which(ctx, "pacman-conf") is None:
            return ()
        patterns = list(_conf_list(ctx, "IgnorePkg"))
        groups = _conf_list(ctx, "IgnoreGroup")
        if groups:
            members = run_c(ctx, ("pacman", "-Sgq") + groups, max_bytes=INVENTORY_MAX_BYTES)
            if members.code == 0:
                patterns.extend(members.out.split())
        return tuple(patterns)

    return _MEMO.get("ignored:{}".format(mtime_of(PACMAN_CONF)), MEMO_TTL, produce)


def is_ignored(ctx: "Context", name: str) -> bool:
    """True when pacman.conf holds ``name`` back (glob patterns allowed)."""
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in ignored_patterns(ctx))


def package_name(target: Target) -> str:
    """``repo/pkg`` -> ``pkg``."""
    return target.package.rsplit("/", 1)[-1]


def _parse_updates(text: str) -> Dict[str, str]:
    """``name old -> new`` lines -> {name: new}. ``[ignored]`` lines are skipped."""
    updates: Dict[str, str] = {}
    for line in text.splitlines():
        if "[ignored]" in line:
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[2] == "->":
            updates[parts[0]] = parts[3]
    return updates


class UpdateView(NamedTuple):
    """Pending repository updates and how fresh the answer is."""

    updates: Dict[str, str]
    fresh: bool          # checked against the mirrors just now (checkupdates)
    behind_local: bool   # the system trails its own sync databases


def _checkupdates_db(ctx: "Context") -> str:
    """aiup's private temporary database folder for checkupdates."""
    return str(Path(ctx.dirs.cache) / "pacman-checkupdates")


STALE_LOCK_AGE = 600.0


def _clear_stale_lock(lock: str) -> None:
    """Remove a lock left in aiup's private checkupdates database.

    A check stopped at its timeout can leave ``db.lck`` behind, and every
    later refresh of that private copy would then fail. No check runs longer
    than a few minutes, so a lock older than ten is left over. This only ever
    touches aiup's own cache folder, never pacman's real database.
    """
    try:
        if time.time() - os.lstat(lock).st_mtime > STALE_LOCK_AGE:
            os.remove(lock)
    except OSError:
        pass


def _run_checkupdates(ctx: "Context", timeout: float) -> Optional[Dict[str, str]]:
    """Pending updates against the mirrors, or None when the check failed.

    A private database refreshed less than 15 minutes ago is reused with
    ``--nosync``, so repeated runs stay offline.
    """
    db = _checkupdates_db(ctx)
    _clear_stale_lock(os.path.join(db, "db.lck"))
    argv: List[str] = ["checkupdates", "--nocolor"]
    if time.time() - mtime_of(os.path.join(db, "sync")) < METADATA_TTL:
        argv.append("--nosync")
    result = run_c(ctx, argv, timeout=max(timeout, 5.0), max_bytes=INVENTORY_MAX_BYTES,
                   env=("CHECKUPDATES_DB=" + db,))
    if result.code == 0:
        return _parse_updates(result.out)
    if result.code == 2:
        return {}
    return None


def update_view(ctx: "Context", timeout: float = 60.0) -> UpdateView:
    """Repository updates for installed packages (one bulk read per run)."""

    def produce() -> UpdateView:
        local = run_c(ctx, ("pacman", "-Qu"), max_bytes=INVENTORY_MAX_BYTES)
        local_updates = _parse_updates(local.out) if local.code == 0 else {}
        if which(ctx, "checkupdates") is not None and which(ctx, "fakeroot") is not None:
            remote = _run_checkupdates(ctx, timeout)
            if remote is not None:
                return UpdateView(remote, True, bool(local_updates))
        return UpdateView(local_updates, False, bool(local_updates))

    stamp = "updates:{}:{}".format(mtime_of(dbpath() + "local"), mtime_of(dbpath() + "sync"))
    return _MEMO.get(stamp, MEMO_TTL, produce)


def sync_is_current(ctx: "Context") -> bool:
    """True when ``pacman -S --needed PKG`` cannot cause a partial upgrade.

    The system must have no pending updates from its own sync databases, and
    the mirrors must have nothing newer (checkupdates). Without checkupdates,
    sync databases refreshed within the last day count as current.
    """
    view = update_view(ctx)
    if view.behind_local:
        return False
    if view.fresh:
        return not view.updates
    newest = max((mtime_of(str(p)) for p in Path(dbpath(), "sync").glob("*.db")), default=0.0)
    return time.time() - newest < 86400


def sync_version(ctx: "Context", spec: str, timeout: float) -> Optional[str]:
    """Version of ``spec`` (``pkg`` or ``repo/pkg``) in the sync databases."""

    def produce() -> Optional[str]:
        result = run_c(ctx, ("pacman", "-Si", "--", spec), timeout=timeout)
        if result.code != 0:
            return None
        for line in result.out.splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip() == "Version":
                return value.strip() or None
        return None

    stamp = "si:{}:{}".format(spec, mtime_of(dbpath() + "sync"))
    return _MEMO.get(stamp, MEMO_TTL, produce)


def owners_of(ctx: "Context", paths: Sequence[str]) -> Dict[str, str]:
    """Batched ``pacman -Qo``: {path: package} for the paths pacman owns.

    pacman prints a directory with a trailing slash ("/usr/lib/node_modules/x/
    is owned by ..."), so the slash is dropped to match the path asked.
    """
    if not paths:
        return {}
    result = run_c(ctx, ("pacman", "-Qo", "--") + tuple(paths), max_bytes=INVENTORY_MAX_BYTES)
    found: Dict[str, str] = {}
    marker = " is owned by "
    for line in result.out.splitlines():
        head, sep, tail = line.partition(marker)
        if sep:
            words = tail.split()
            if words:
                found[head.strip().rstrip("/") or "/"] = words[0]
    return found


def pacnew_files(limit: int = 200) -> Tuple[str, ...]:
    """``.pacnew`` and ``.pacsave`` files under /etc that need a look after an upgrade."""
    found: List[str] = []
    for root, dirs, files in os.walk("/etc"):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for name in files:
            if name.endswith((".pacnew", ".pacsave")):
                found.append(os.path.join(root, name))
                if len(found) >= limit:
                    return tuple(sorted(found))
    return tuple(sorted(found))


def full_upgrade_argv(ctx: "Context", extra: Sequence[str] = ()) -> Tuple[str, ...]:
    """``pacman -Syu`` (plus ``extra``), with ``--noconfirm`` only without a terminal."""
    argv: List[str] = ["pacman", "-Syu"]
    if not ctx.interactive:
        argv.append("--noconfirm")
    argv.extend(extra)
    return tuple(argv)


FULL_UPGRADE_NOTE = ("pacman cannot update one package safely, so this runs a full "
                     "system upgrade: sudo pacman -Syu")


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class PacmanProvider(Provider):
    """Arch repository packages through pacman."""

    name = "pacman"
    oses = frozenset({"linux"})
    scope = "system"
    lane = "system"
    exclusive = True
    targeted_update = False

    def available(self, ctx: "Context") -> bool:
        """True on a pacman system."""
        return pacman_present(ctx)

    def can_provide(self, ctx: "Context", target: Target) -> bool:
        """True when a configured repository has the package (or it is installed from one)."""
        if not self.available(ctx):
            return False
        return sync_version(ctx, target.package, 5.0) is not None

    def _owned_here(self, ctx: "Context", name: str) -> bool:
        """False for foreign packages the aur provider owns."""
        return not (name in foreign_names(ctx) and aur_helper(ctx) is not None)

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """Installed version from the local database, or None."""
        name = package_name(target)
        package = local_packages(ctx).get(name)
        if package is None or not self._owned_here(ctx, name):
            return None
        return Installed(version=package.version, path=None, scope="system", channel=self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """Newest repository version, offline first."""
        name = package_name(target)
        if name in foreign_names(ctx):
            return Latest("", self.name, "not in a configured repository")
        if is_ignored(ctx, name):
            return Latest("", self.name, "held by IgnorePkg or IgnoreGroup in pacman.conf")
        installed = local_packages(ctx).get(name)
        if installed is not None:
            view = update_view(ctx, timeout)
            return Latest(view.updates.get(name, installed.version), self.name)
        version = sync_version(ctx, target.package, timeout)
        if version is None:
            return Latest("", self.name, "not in a configured repository")
        return Latest(version, self.name)

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Every repository package with a newer version, in one read."""
        foreign = foreign_names(ctx)
        updates = update_view(ctx).updates
        return {name: Latest(version, self.name) for name, version in updates.items()
                if name not in foreign and not is_ignored(ctx, name)}

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Installed packages; foreign ones are left to the aur provider when it is available."""
        skip = foreign_names(ctx) if aur_helper(ctx) is not None else frozenset()
        return tuple(PackageRecord(manager=self.name, name=p.name, version=p.version,
                                   scope="system", explicit=p.explicit)
                     for p in sorted(local_packages(ctx).values()) if p.name not in skip)

    def install(self, ctx: "Context", target: Target) -> Action:
        """``pacman -S --needed`` when the databases are current, else ``pacman -Syu --needed``."""
        name = package_name(target)
        if sync_is_current(ctx):
            argv: List[str] = ["pacman", "-S", "--needed"]
            if not ctx.interactive:
                argv.append("--noconfirm")
            argv.extend(["--", target.package])
            step = system_step(ctx, argv, "pacman -S --needed " + target.package)
            return Action(tool=name, op="install", channel=self.name, steps=(step,))
        argv_full = full_upgrade_argv(ctx, ("--needed", "--", target.package))
        step = system_step(ctx, argv_full, "pacman -Syu --needed " + target.package)
        note = ("The package databases are not current, so installing {} runs a full system "
                "upgrade with it: sudo pacman -Syu --needed {}").format(name, target.package)
        return Action(tool=name, op="install", channel=self.name, steps=(step,), note=note)

    def update(self, ctx: "Context", target: Target) -> Action:
        """A full ``pacman -Syu``; pacman has no safe single-package update."""
        name = package_name(target)
        note = FULL_UPGRADE_NOTE
        if is_ignored(ctx, name):
            note += ". {} is held by IgnorePkg or IgnoreGroup in pacman.conf, so it stays as it is".format(name)
        step = system_step(ctx, full_upgrade_argv(ctx), "pacman -Syu")
        return Action(tool=name, op="update", channel=self.name, steps=(step,), note=note)

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``pacman -Rs PKG``. pacman refuses when another package needs it."""
        name = package_name(target)
        argv: List[str] = ["pacman", "-Rs"]
        if not ctx.interactive:
            argv.append("--noconfirm")
        argv.extend(["--", name])
        step = system_step(ctx, argv, "pacman -Rs " + name)
        return Action(tool=name, op="remove", channel=self.name, steps=(step,))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """``pacman -Qo`` on the resolved path."""
        if not self.available(ctx):
            return None
        found = self.owns_many(ctx, (path,))
        return found.get(path)

    def owns_many(self, ctx: "Context", paths: Sequence[str]) -> Dict[str, Ownership]:
        """Batched ownership: one ``pacman -Qo`` for every path."""
        resolved = {path: os.path.realpath(path) for path in paths}
        owners = owners_of(ctx, sorted(set(resolved.values())))
        result: Dict[str, Ownership] = {}
        for path, real in resolved.items():
            package = owners.get(real)
            if package is not None and self._owned_here(ctx, package):
                result[path] = Ownership(manager=self.name, package=package, confidence="exact")
        return result

    def system_upgrade(self, ctx: "Context") -> Optional[Action]:
        """``sudo pacman -Syu``. With an AUR helper, the aur provider's upgrade covers both."""
        if not self.available(ctx) or aur_helper(ctx) is not None:
            return None
        step = system_step(ctx, full_upgrade_argv(ctx), "pacman -Syu")
        return Action(tool="system", op="update", channel=self.name, steps=(step,),
                      note="This runs a full system upgrade: sudo pacman -Syu")

    def metadata_refresh(self, ctx: "Context") -> Optional[Action]:
        """None: ``pacman -Sy`` on its own sets up a partial upgrade, so aiup never runs it.

        Fresh data comes from checkupdates' private database instead.
        """
        return None

    def lock_held(self, ctx: "Context") -> str:
        """``LOCKED_NOTE`` while pacman's ``db.lck`` exists."""
        return lock_note() if self.available(ctx) else ""

    def notices(self, ctx: "Context") -> Tuple[str, ...]:
        """Lines to show after a system upgrade: config files pacman left beside the old ones."""
        if not self.available(ctx):
            return ()
        files = pacnew_files()
        if not files:
            return ()
        lines = ["pacman left {} config file(s) to review (pacdiff merges them):".format(len(files))]
        lines.extend("  " + path for path in files)
        return tuple(lines)

    def forget(self) -> None:
        """Drop cached reads after a mutation."""
        _MEMO.clear()
