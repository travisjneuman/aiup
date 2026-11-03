"""Chocolatey provider (machine-wide Windows packages).

Chocolatey 2 changed ``choco list`` to local packages only; Chocolatey 1 needs
``--local-only`` for that. aiup reads the version from
``lib\\chocolatey\\chocolatey.nuspec`` and picks the flags to match.

Most reads skip choco itself: ``lib\\<id>\\<id>.nuspec`` holds each installed
package's ``<version>``. ``choco outdated --limit-output`` gives the update
list as ``id|current|available|pinned`` lines, and ``choco search --exact
--limit-output`` gives one package's newest version.

Every change needs an elevated terminal. aiup never elevates itself: steps are
``elevated-required``, and when aiup is not elevated the note carries the exact
command to run from an elevated terminal.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers._win import (READ_TIMEOUT, SLOW_TIMEOUT, SMALL_MAX_BYTES, WINDOWS, Memo, env_dir,
                                 first_line, is_windows, path_parts, read_text_file, run_w, under, which)

if TYPE_CHECKING:
    from aiup.engine.context import Context

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")
_NUSPEC_VERSION = re.compile(r"<version>\s*([^<\s]+)\s*</version>", re.IGNORECASE)
STEP_TIMEOUT = 3600.0
NUSPEC_MAX_BYTES = 256 * 1024
TOOLS_SCAN_LIMIT = 4000              # files looked at when matching a shim to a package
MEMO_TTL = 300.0
QUIET = ("-y", "--no-progress")
# Exit codes Chocolatey passes on from installers (MSI conventions).
REBOOT_INITIATED = 1641
REBOOT_REQUIRED = 3010
REBOOT_PENDING = 350                 # choco refuses to start while a restart is pending
NOTHING_TO_DO = 2                    # enhanced exit codes: no results, nothing outdated
OK_CODES = (0, REBOOT_INITIATED, REBOOT_REQUIRED)
_EXIT_MEANINGS: Mapping[int, Tuple[str, str]] = {
    REBOOT_REQUIRED: ("", "restart Windows to finish"),
    REBOOT_INITIATED: ("", "Windows will restart to finish"),
    REBOOT_PENDING: ("deferred", "Windows has a restart pending; restart, then run aiup again"),
}
_MEMO = Memo()
_EXTENSION_SUFFIXES = (".extension",)
_INSTALLER_SUFFIXES = (".install", ".portable")


def choco_root() -> Optional[Path]:
    """Chocolatey's folder: ``%ChocolateyInstall%``, else ``%ProgramData%\\chocolatey``."""
    return env_dir("ChocolateyInstall") or env_dir("ProgramData", "chocolatey")


def nuspec_version(lib: Path, ident: str) -> Optional[str]:
    """The version in ``lib\\<id>\\<id>.nuspec``, or None when the package is not installed."""
    text = read_text_file(lib / ident / (ident + ".nuspec"), NUSPEC_MAX_BYTES)
    if text is None:
        return None
    found = _NUSPEC_VERSION.search(text)
    return found.group(1) if found else ""


def installed_ids(lib: Path) -> List[str]:
    """Installed package ids, from the folders under ``lib`` that hold a nuspec."""
    try:
        names = sorted(entry.name for entry in os.scandir(lib) if entry.is_dir())
    except OSError:
        return []
    return [name for name in names if NAME.match(name) and (lib / name / (name + ".nuspec")).is_file()]


def is_dependency(ident: str, present: FrozenSet[str]) -> bool:
    """Heuristic: True for packages Chocolatey pulls in itself.

    Chocolatey keeps no installed-on-request flag. Extensions, Windows update
    packages (``kb...``), choco itself and the ``.install``/``.portable``
    halves of a meta package count as dependencies.
    """
    lowered = ident.lower()
    if lowered == "chocolatey" or lowered.endswith(_EXTENSION_SUFFIXES):
        return True
    if re.match(r"^kb\d+", lowered):
        return True
    for suffix in _INSTALLER_SUFFIXES:
        if lowered.endswith(suffix) and lowered[: -len(suffix)] in present:
            return True
    return False


def explain_choco_exit(code: Optional[int], op: str = "") -> Optional[Tuple[str, str]]:
    """``(result, note)`` for a choco exit status, or None; "" keeps the engine's result.

    With Chocolatey's ``useEnhancedExitCodes`` feature on, ``choco upgrade``
    exits 2 when nothing was outdated.
    """
    if code is None or code == 0:
        return None
    if code == NOTHING_TO_DO and op in ("update", "system"):
        return ("unchanged", "Chocolatey has no newer version")
    return _EXIT_MEANINGS.get(code)


def parse_outdated(text: str) -> Dict[str, Tuple[str, str, bool]]:
    """``id -> (installed, available, pinned)`` from ``choco outdated --limit-output``."""
    found: Dict[str, Tuple[str, str, bool]] = {}
    for line in text.splitlines():
        fields = [field.strip() for field in line.split("|")]
        if len(fields) < 3 or not NAME.match(fields[0]):
            continue
        pinned = len(fields) > 3 and fields[3].lower() == "true"
        found[fields[0].lower()] = (fields[1], fields[2], pinned)
    return found


class ChocoProvider(Provider):
    """Chocolatey. Machine scope; every change needs an elevated terminal."""

    name = "choco"
    oses = WINDOWS
    scope = "system"
    lane = "system"
    exclusive = True
    targeted_update = True

    def lib(self) -> Optional[Path]:
        """Chocolatey's package folder."""
        root = choco_root()
        return root / "lib" if root is not None else None

    def exe(self, ctx: "Context") -> Optional[str]:
        """``choco.exe``: on PATH, else in Chocolatey's ``bin`` folder."""
        found = which(ctx, "choco")
        if found:
            return found
        root = choco_root()
        candidate = root / "bin" / "choco.exe" if root is not None else None
        return str(candidate) if candidate is not None and candidate.is_file() else None

    def choco_version(self) -> str:
        """Chocolatey's own version, from its nuspec ("" when unknown)."""
        lib = self.lib()
        return (nuspec_version(lib, "chocolatey") or "") if lib is not None else ""

    def v1(self) -> bool:
        """True for Chocolatey 1.x, where ``choco list`` still searches the sources."""
        major = self.choco_version().split(".", 1)[0]
        return major.isdigit() and int(major) < 2

    def available(self, ctx: "Context") -> bool:
        """True when choco is installed."""
        return is_windows(ctx) and self.exe(ctx) is not None

    def unavailable_reason(self, ctx: "Context") -> str:
        """Why choco cannot be used here, or ""."""
        if not is_windows(ctx):
            return "Chocolatey is Windows only"
        return "" if self.exe(ctx) is not None else "Chocolatey is not installed"

    # ----- reads -----------------------------------------------------------

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """The installed package, from its nuspec."""
        ident = target.package.strip()
        lib = self.lib()
        if not NAME.match(ident) or lib is None or not is_windows(ctx):
            return None
        version = nuspec_version(lib, ident)
        if version is None:
            return None
        return Installed(version=version, path=str(lib / ident), scope="machine", channel=self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """The newest version on the configured sources (``choco search --exact``)."""
        ident = target.package.strip()
        exe = self.exe(ctx)
        if not NAME.match(ident):
            return Latest("", self.name, "not a Chocolatey package id: " + ident)
        if exe is None:
            return Latest("", self.name, "Chocolatey is not installed")
        verb = "list" if self.v1() else "search"
        out = run_w(ctx, (exe, verb, ident, "--exact", "--limit-output"), max(timeout, READ_TIMEOUT))
        if out.code is None:
            return Latest("", self.name, "choco " + out.error)
        if out.code not in (0, NOTHING_TO_DO):
            return Latest("", self.name, first_line(out.err or out.out) or "choco {} exited {}".format(verb, out.code))
        for line in out.out.splitlines():
            fields = line.strip().split("|")
            if len(fields) >= 2 and fields[0].lower() == ident.lower() and fields[1]:
                return Latest(fields[1], self.name)
        return Latest("", self.name, "no Chocolatey source has this package")

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Packages with updates (``choco outdated``), read once per run. Pinned ones are left out."""
        exe = self.exe(ctx) if is_windows(ctx) else None
        if exe is None:
            return {}
        return _MEMO.get("outdated", MEMO_TTL, lambda: self._read_outdated(ctx, exe))

    def _read_outdated(self, ctx: "Context", exe: str) -> Mapping[str, Latest]:
        # choco outdated exits 2 when something is outdated (enhanced exit codes).
        out = run_w(ctx, (exe, "outdated", "--limit-output"), SLOW_TIMEOUT, SMALL_MAX_BYTES * 2)
        if out.code not in (0, NOTHING_TO_DO):
            return {}
        return {ident: Latest(available, self.name)
                for ident, (_current, available, pinned) in parse_outdated(out.out).items()
                if available and not pinned}

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Every installed package, from Chocolatey's lib folder."""
        lib = self.lib()
        if lib is None or not is_windows(ctx):
            return ()
        ids = installed_ids(lib)
        present = frozenset(ident.lower() for ident in ids)
        return tuple(
            PackageRecord(manager=self.name, name=ident, version=nuspec_version(lib, ident) or "",
                          scope="machine", explicit=not is_dependency(ident, present), paths=(str(lib / ident),))
            for ident in ids
        )

    # ----- actions ---------------------------------------------------------

    def _action(self, ctx: "Context", target: Target, op: str, verb: str, *extra: str) -> Action:
        ident = target.package.strip()
        if not NAME.match(ident):
            return Action(target.package, op, self.name, (), "not a Chocolatey package id")
        exe = self.exe(ctx) or "choco"
        argv = (exe, verb, ident) + QUIET + extra
        step = Step(argv=argv, label="choco {} {}".format(verb, ident), privilege="elevated-required",
                    timeout=STEP_TIMEOUT, ok_codes=OK_CODES)
        return Action(target.package, op, self.name, (step,), self.elevation_note(ctx, argv))

    def elevation_note(self, ctx: "Context", argv: Tuple[str, ...]) -> str:
        """The exact command for an elevated terminal, when aiup itself is not elevated."""
        try:
            elevated = bool(ctx.platform.is_elevated())
        except OSError:
            elevated = False
        if elevated:
            return ""
        return "needs an elevated terminal; run: choco " + " ".join(argv[1:])

    def install(self, ctx: "Context", target: Target) -> Action:
        """``choco install ID -y``."""
        return self._action(ctx, target, "install", "install")

    def update(self, ctx: "Context", target: Target) -> Action:
        """``choco upgrade ID -y``, which never installs a package that is missing."""
        return self._action(ctx, target, "update", "upgrade", "--fail-on-not-installed")

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``choco uninstall ID -y``."""
        return self._action(ctx, target, "remove", "uninstall")

    def system_upgrade(self, ctx: "Context") -> Optional[Action]:
        """``choco upgrade all -y`` for ``aiup system``; elevated runs only."""
        exe = self.exe(ctx) if is_windows(ctx) else None
        if exe is None:
            return None
        argv = (exe, "upgrade", "all") + QUIET
        step = Step(argv=argv, label="choco upgrade all", privilege="elevated-required", ok_codes=OK_CODES)
        return Action("choco", "update", self.name, (step,), self.elevation_note(ctx, argv))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """Files under ``lib\\<id>`` (exact), and ``bin`` shims matched to a package by file name."""
        root = choco_root()
        if root is None:
            return None
        rest = under(path_parts(path), root)
        if not rest or len(rest) < 2:
            return None
        if rest[0] == "lib" and NAME.match(rest[1]):
            return Ownership(self.name, rest[1], "exact")
        if rest[0] == "bin" and len(rest) == 2:
            ident = shim_package(root / "lib", rest[1])
            if ident:
                return Ownership(self.name, ident, "prefix")
        return None

    # ----- engine hooks beyond the base interface --------------------------

    def explain_exit(self, op: str, code: Optional[int]) -> Optional[Tuple[str, str]]:
        """``(result, note)`` for a choco exit status; see ``explain_choco_exit``."""
        return explain_choco_exit(code, op)

    def forget(self) -> None:
        """Drop cached reads after a mutation."""
        _MEMO.clear()


def shim_package(lib: Path, file_name: str) -> str:
    """The package whose files include ``file_name`` (bounded walk of ``lib``); "" when none or unsure."""
    wanted = file_name.lower()
    seen = 0
    owners: List[str] = []
    for ident in installed_ids(lib):
        for _folder, _dirs, files in os.walk(lib / ident):
            seen += len(files)
            if any(name.lower() == wanted for name in files):
                owners.append(ident.lower())
                break
            if seen > TOOLS_SCAN_LIMIT:
                return ""
    return owners[0] if len(owners) == 1 else ""
