"""apt provider (Debian, Ubuntu and derivatives). Design doc 6.3, 7.1 and 7.3.

- Installed state comes straight from ``/var/lib/dpkg/status``, and
  "installed on request" from ``/var/lib/apt/extended_states``. One file read
  serves every tool.
- Latest versions are the ``Candidate`` from ``apt-cache policy``, which reads
  the local package lists only. ``metadata_refresh`` (``apt-get update``)
  keeps those lists fresh; the engine runs it at most once per run.
- Updates use ``apt-get install --only-upgrade PKG``. ``aiup system`` runs
  ``apt-get update`` then ``apt-get upgrade``, never ``dist-upgrade`` or
  ``full-upgrade``, so nothing is removed.
- Removal is ``apt-get remove`` (never purge) and always asks on the
  terminal, because apt can remove other packages with it.
- aiup never adds a repository or PPA. A package with no candidate is
  reported as not in a configured repository.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Set, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers._linux import (
    INVENTORY_MAX_BYTES, LOCKED_NOTE, Memo, asking_remove, is_linux, mtime_of, posix_lock_held, run_c, system_step, which,
)

if TYPE_CHECKING:
    from aiup.engine.context import Context

DPKG_STATUS = "/var/lib/dpkg/status"
OWNS_BATCH = 400
EXTENDED_STATES = "/var/lib/apt/extended_states"
LOCK_FILES = (
    "/var/lib/dpkg/lock-frontend",
    "/var/lib/dpkg/lock",
    "/var/lib/apt/lists/lock",
    "/var/cache/apt/archives/lock",
)
STATUS_MAX_BYTES = 64 * 1024 * 1024
MEMO_TTL = 300.0
NONINTERACTIVE_ENV = {"DEBIAN_FRONTEND": "noninteractive"}
# Keep the local copy of a changed config file and install the package's copy
# beside it, without asking (only used without a terminal).
CONFFILE_OPTIONS = ("-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold")
_MEMO = Memo()


class DebPackage(NamedTuple):
    """One installed package from the dpkg status file."""

    key: str          # "name", or "name:arch" for a foreign architecture
    name: str
    arch: str
    version: str
    explicit: bool


def stanzas(text: str) -> Iterable[Dict[str, str]]:
    """Debian control stanzas (``Field: value`` blocks split by blank lines).

    Continuation lines are dropped: none of the fields aiup reads use them.
    """
    current: Dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            if current:
                yield current
                current = {}
            continue
        if line[0] in " \t":
            continue
        key, sep, value = line.partition(":")
        if sep:
            current[key.strip()] = value.strip()
    if current:
        yield current


def _read_text(path: str, limit: int) -> str:
    """A local file as text, "" when it cannot be read."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def native_arch(ctx: "Context") -> str:
    """``dpkg --print-architecture``, for example ``amd64``."""

    def produce() -> str:
        result = run_c(ctx, ("dpkg", "--print-architecture"))
        return result.out.strip() if result.code == 0 else ""

    return _MEMO.get("arch", 3600.0, produce)


def _auto_installed() -> Set[Tuple[str, str]]:
    """(name, arch) pairs apt marked as installed for a dependency."""
    auto: Set[Tuple[str, str]] = set()
    for stanza in stanzas(_read_text(EXTENDED_STATES, STATUS_MAX_BYTES)):
        if stanza.get("Auto-Installed") == "1" and stanza.get("Package"):
            auto.add((stanza["Package"], stanza.get("Architecture", "")))
    return auto


def _read_status(ctx: "Context") -> Dict[str, DebPackage]:
    """Every installed package, keyed by ``name`` or ``name:arch``."""
    native = native_arch(ctx)
    auto = _auto_installed()
    packages: Dict[str, DebPackage] = {}
    for stanza in stanzas(_read_text(DPKG_STATUS, STATUS_MAX_BYTES)):
        status = stanza.get("Status", "").split()
        name, version = stanza.get("Package", ""), stanza.get("Version", "")
        if len(status) != 3 or status[2] != "installed" or not name or not version:
            continue
        arch = stanza.get("Architecture", "")
        key = name if arch in ("all", native, "") else "{}:{}".format(name, arch)
        explicit = (name, arch) not in auto and (name, "") not in auto
        packages[key] = DebPackage(key, name, arch, version, explicit)
    return packages


def installed_packages(ctx: "Context") -> Dict[str, DebPackage]:
    """Installed packages, cached until the status file changes."""
    stamp = "status:{}:{}".format(mtime_of(DPKG_STATUS), mtime_of(EXTENDED_STATES))
    return _MEMO.get(stamp, MEMO_TTL, lambda: _read_status(ctx))


def _lists_stamp() -> str:
    """Changes whenever ``apt-get update`` rewrites the package lists."""
    return str(mtime_of("/var/lib/apt/lists") + mtime_of("/var/cache/apt/pkgcache.bin"))


def parse_policy(text: str) -> Dict[str, str]:
    """``apt-cache policy A B``: {package: candidate}. "(none)" becomes ""."""
    found: Dict[str, str] = {}
    current = ""
    for line in text.splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            current = line.rstrip()[:-1]
            continue
        stripped = line.strip()
        if current and stripped.startswith("Candidate:"):
            value = stripped[len("Candidate:"):].strip()
            found[current] = "" if value == "(none)" else value
    return found


def candidates(ctx: "Context", names: Sequence[str], timeout: float) -> Dict[str, str]:
    """Candidate versions for ``names`` in one ``apt-cache policy`` call."""
    stamp = _lists_stamp()
    answers: Dict[str, str] = {}
    missing: List[str] = []
    for name in sorted(set(names)):
        hit, value = _MEMO.peek("policy:{}:{}".format(stamp, name), MEMO_TTL)
        if hit and isinstance(value, str):
            answers[name] = value
        else:
            missing.append(name)
    if missing:
        result = run_c(ctx, ["apt-cache", "policy"] + missing, timeout=timeout,
                       max_bytes=INVENTORY_MAX_BYTES)
        parsed = parse_policy(result.out) if result.code == 0 else {}
        for name in missing:
            value = parsed.get(name, "")
            if result.code == 0:
                _MEMO.put("policy:{}:{}".format(stamp, name), value)
            answers[name] = value
    return answers


def _parse_simulation(text: str) -> Dict[str, str]:
    """``Inst name [old] (new repo [arch])`` lines: {name: new} for upgrades only."""
    found: Dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "Inst" and parts[2].startswith("[") and parts[3].startswith("("):
            found[parts[1]] = parts[3][1:]
    return found


def _with_usr_variants(path: str) -> Tuple[str, ...]:
    """``path`` plus its other spelling on a merged-/usr system."""
    if path.startswith("/usr/"):
        return (path, path[len("/usr"):])
    return (path, "/usr" + path)


def dpkg_owners(ctx: "Context", paths: Sequence[str]) -> Dict[str, str]:
    """Batched ``dpkg-query -S`` with exact path matches only: {path: package}."""
    if not paths:
        return {}
    result = run_c(ctx, ["dpkg-query", "-S"] + list(paths), max_bytes=INVENTORY_MAX_BYTES)
    wanted = set(paths)
    found: Dict[str, str] = {}
    for line in result.out.splitlines():
        if line.startswith("diversion "):
            continue
        names, sep, path = line.partition(": ")
        path = path.strip()
        if sep and path in wanted:
            first = names.split(",")[0].strip()
            if first:
                found[path] = first
    return found


def _apt_argv(ctx: "Context", words: Sequence[str]) -> List[str]:
    """``apt-get`` argv, with ``-y`` and the config-file options only without a terminal."""
    argv: List[str] = ["apt-get"]
    if not ctx.interactive:
        argv.append("-y")
        argv.extend(CONFFILE_OPTIONS)
    argv.extend(words)
    return argv


def _apt_step(ctx: "Context", words: Sequence[str], label: str) -> Step:
    """A sudo apt-get step. Without a terminal debconf is told not to ask."""
    env = None if ctx.interactive else NONINTERACTIVE_ENV
    return system_step(ctx, _apt_argv(ctx, words), label, env=env)


class AptProvider(Provider):
    """Debian packages through apt-get and dpkg."""

    name = "apt"
    oses = frozenset({"linux"})
    scope = "system"
    lane = "system"
    exclusive = True
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        """True when apt-get, apt-cache and the dpkg database are present."""
        return (is_linux(ctx) and which(ctx, "apt-get") is not None
                and which(ctx, "apt-cache") is not None and os.path.isfile(DPKG_STATUS))

    def can_provide(self, ctx: "Context", target: Target) -> bool:
        """True when a configured repository has a candidate for the package."""
        return self.available(ctx) and bool(candidates(ctx, (target.package,), 5.0).get(target.package))

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """Installed version from the dpkg status file, or None."""
        package = installed_packages(ctx).get(target.package)
        if package is None:
            return None
        return Installed(version=package.version, path=None, scope="system", channel=self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """The candidate version from the local package lists."""
        result = candidates(ctx, (target.package,), timeout).get(target.package, "")
        if not result:
            return Latest("", self.name, "not in a configured repository")
        return Latest(result, self.name)

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Pending upgrades from a simulated ``apt-get upgrade`` (no lock, no change)."""
        result = run_c(ctx, ("apt-get", "-s", "-o", "Debug::NoLocking=1", "upgrade"),
                       timeout=30.0, max_bytes=INVENTORY_MAX_BYTES)
        if result.code != 0:
            return {}
        return {name: Latest(version, self.name) for name, version in _parse_simulation(result.out).items()}

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Every installed package."""
        return tuple(PackageRecord(manager=self.name, name=p.key, version=p.version,
                                   scope="system", explicit=p.explicit)
                     for p in sorted(installed_packages(ctx).values()))

    def install(self, ctx: "Context", target: Target) -> Action:
        """``apt-get install PKG``."""
        step = _apt_step(ctx, ("install", target.package), "apt-get install " + target.package)
        return Action(tool=target.package, op="install", channel=self.name, steps=(step,))

    def update(self, ctx: "Context", target: Target) -> Action:
        """``apt-get install --only-upgrade PKG``."""
        step = _apt_step(ctx, ("install", "--only-upgrade", target.package),
                         "apt-get install --only-upgrade " + target.package)
        return Action(tool=target.package, op="update", channel=self.name, steps=(step,))

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``apt-get remove PKG`` (never purge). Asks on the terminal; deferred without one."""
        return asking_remove(ctx, self.name, target.package, ("apt-get", "remove", target.package))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """``dpkg-query -S``, trying both spellings of a merged-/usr path."""
        if not self.available(ctx):
            return None
        tries: List[str] = []
        for candidate in (path, os.path.realpath(path)):
            for variant in _with_usr_variants(candidate):
                if variant not in tries:
                    tries.append(variant)
        owners = dpkg_owners(ctx, tries)
        for variant in tries:
            if variant in owners:
                return Ownership(manager=self.name, package=owners[variant], confidence="exact")
        return None

    def owns_many(self, ctx: "Context", paths: Sequence[str]) -> Dict[str, Ownership]:
        """Batched ``dpkg-query -S``: every spelling of every path, a few hundred per call."""
        if not self.available(ctx):
            return {}
        tries: Dict[str, List[str]] = {}
        for path in dict.fromkeys(paths):
            spellings: List[str] = []
            for candidate in (path, os.path.realpath(path)):
                for variant in _with_usr_variants(candidate):
                    if variant not in spellings:
                        spellings.append(variant)
            tries[path] = spellings
        every = list(dict.fromkeys(variant for spellings in tries.values() for variant in spellings))
        owners: Dict[str, str] = {}
        for start in range(0, len(every), OWNS_BATCH):
            owners.update(dpkg_owners(ctx, every[start:start + OWNS_BATCH]))
        result: Dict[str, Ownership] = {}
        for path, spellings in tries.items():
            for variant in spellings:
                if variant in owners:
                    result[path] = Ownership(manager=self.name, package=owners[variant], confidence="exact")
                    break
        return result

    def system_upgrade(self, ctx: "Context") -> Optional[Action]:
        """``apt-get update`` then ``apt-get upgrade``."""
        if not self.available(ctx):
            return None
        steps = (
            system_step(ctx, ("apt-get", "update"), "apt-get update"),
            _apt_step(ctx, ("upgrade",), "apt-get upgrade"),
        )
        return Action(tool="system", op="update", channel=self.name, steps=steps,
                      note="This runs sudo apt-get update and sudo apt-get upgrade.")

    def metadata_refresh(self, ctx: "Context") -> Optional[Action]:
        """``apt-get update``. The engine keeps a 15 minute stamp and runs it at most once."""
        if not self.available(ctx):
            return None
        step = system_step(ctx, ("apt-get", "update"), "apt-get update")
        return Action(tool="apt", op="update", channel=self.name, steps=(step,))

    def lock_held(self, ctx: "Context") -> str:
        """``LOCKED_NOTE`` while dpkg or apt holds one of its locks."""
        return LOCKED_NOTE if posix_lock_held(LOCK_FILES) else ""
