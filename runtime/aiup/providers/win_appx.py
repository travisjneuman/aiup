"""Appx and MSIX packages for the current user (inventory and removal only).

aiup never installs or updates these. The Microsoft Store updates Store apps
itself, so ``latest`` answers "managed by Microsoft Store" and the engine
reports them that way.

Reads run ``Get-AppxPackage`` once through Windows PowerShell 5.1, called by
its absolute path (the Appx module is a Windows PowerShell module). The script
turns enum values into names before ``ConvertTo-Json``, which otherwise writes
them as numbers. Frameworks, resource packages and System packages are left
out; ``NonRemovable`` packages are listed but never get a remove step.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterable, List, NamedTuple, Optional, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.versions import version_cmp
from aiup.providers._win import (SLOW_TIMEOUT, STORE_NOTE, WINDOWS, Memo, env_dir, is_windows, path_parts,
                                 powershell_argv, powershell_env, powershell_json, under,
                                 windows_powershell)

if TYPE_CHECKING:
    from aiup.engine.context import Context

MEMO_TTL = 300.0
# Package names are letters, digits, dots and dashes. Wildcards and quotes are refused,
# because the name is written into a PowerShell script as a literal.
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{2,49}$")
FULL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_~]{2,200}$")
_MEMO = Memo()

_LIST_SCRIPT = """
Import-Module Appx -ErrorAction SilentlyContinue
$rows = @(Get-AppxPackage | Where-Object {
  -not $_.IsFramework -and -not $_.IsResourcePackage -and [string]$_.SignatureKind -ne 'System'
} | ForEach-Object {
  [pscustomobject]@{
    Name = [string]$_.Name
    Version = [string]$_.Version
    FullName = [string]$_.PackageFullName
    Family = [string]$_.PackageFamilyName
    Signature = [string]$_.SignatureKind
    NonRemovable = [bool]$_.NonRemovable
    Location = [string]$_.InstallLocation
  }
})
ConvertTo-Json -InputObject $rows -Depth 2 -Compress
"""


class AppxPackage(NamedTuple):
    """One package from ``Get-AppxPackage``."""

    name: str
    version: str
    full_name: str
    family: str
    signature: str
    removable: bool
    location: str


def _packages(value: Optional[object]) -> List[AppxPackage]:
    """Packages from the script's JSON."""
    if not isinstance(value, list):
        return []
    found: List[AppxPackage] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name, full_name = str(item.get("Name") or ""), str(item.get("FullName") or "")
        if not NAME.match(name) or not FULL_NAME.match(full_name):
            continue
        found.append(AppxPackage(
            name=name, version=str(item.get("Version") or ""), full_name=full_name,
            family=str(item.get("Family") or ""), signature=str(item.get("Signature") or ""),
            removable=not bool(item.get("NonRemovable")), location=str(item.get("Location") or ""),
        ))
    return found


def ps_literal(value: str) -> str:
    """A single-quoted PowerShell string literal."""
    return "'" + value.replace("'", "''") + "'"


class AppxProvider(Provider):
    """Store and sideloaded app packages for the current user."""

    name = "appx"
    oses = WINDOWS
    scope = "user"
    lane = "appx"
    exclusive = False
    targeted_update = False
    self_updating = True             # the Microsoft Store updates these, never aiup

    def available(self, ctx: "Context") -> bool:
        """True on Windows when Windows PowerShell is present."""
        return is_windows(ctx) and windows_powershell() is not None

    def unavailable_reason(self, ctx: "Context") -> str:
        """Why Appx reads cannot run here, or ""."""
        if not is_windows(ctx):
            return "Appx packages are Windows only"
        return "" if windows_powershell() is not None else "Windows PowerShell was not found"

    def packages(self, ctx: "Context") -> Tuple[AppxPackage, ...]:
        """Every listed package, read once per run."""
        if not self.available(ctx):
            return ()
        return _MEMO.get("packages", MEMO_TTL, lambda: self._read(ctx))

    def _read(self, ctx: "Context") -> Tuple[AppxPackage, ...]:
        exe = windows_powershell()
        if exe is None:
            return ()
        value, _reason = powershell_json(ctx, exe, _LIST_SCRIPT, SLOW_TIMEOUT)
        return tuple(_packages(value))

    def find(self, ctx: "Context", name: str) -> Optional[AppxPackage]:
        """The package called ``name`` (newest when several versions are listed)."""
        best: Optional[AppxPackage] = None
        for package in self.packages(ctx):
            if package.name.lower() == name.lower() and (best is None or version_cmp(package.version, best.version) > 0):
                best = package
        return best

    # ----- reads -----------------------------------------------------------

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """The installed package for the current user."""
        name = target.package.strip()
        if not NAME.match(name):
            return None
        package = self.find(ctx, name)
        if package is None:
            return None
        return Installed(version=package.version, path=package.location or None, scope="user", channel=self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """Always "managed by Microsoft Store": aiup has no way to read Store versions."""
        return Latest("", "msstore", STORE_NOTE, managed=STORE_NOTE)

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Store and Developer (sideloaded) packages; frameworks and System packages are left out."""
        return tuple(
            PackageRecord(manager=self.name, name=package.name, version=package.version, scope="user",
                          explicit=True, paths=(package.location,) if package.location else ())
            for package in self.packages(ctx)
        )

    # ----- actions ---------------------------------------------------------

    def install(self, ctx: "Context", target: Target) -> Action:
        """No steps: install Store apps from the Microsoft Store (or the msstore winget source)."""
        return Action(target.package, "install", self.name, (), STORE_NOTE, result="skipped")

    def update(self, ctx: "Context", target: Target) -> Action:
        """No steps: the Microsoft Store updates these apps."""
        return Action(target.package, "update", self.name, (), STORE_NOTE, result="skipped")

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``Remove-AppxPackage`` for the current user, by the exact full name read just now."""
        name = target.package.strip()
        if not NAME.match(name):
            return Action(target.package, "remove", self.name, (), "not an app package name")
        _MEMO.clear()                # live lookup: the engine is about to change this package
        package = self.find(ctx, name)
        exe = windows_powershell()
        if package is None or exe is None:
            return Action(target.package, "remove", self.name, (), "not installed for this account")
        if not package.removable or package.signature.lower() == "system":
            return Action(target.package, "remove", self.name, (), "Windows marks this package as not removable")
        script = "Remove-AppxPackage -Package {}\n".format(ps_literal(package.full_name))
        step = Step(argv=powershell_argv(exe, script), label="Remove-AppxPackage " + package.name,
                    privilege="none", env=powershell_env(exe), timeout=600.0)
        return Action(target.package, "remove", self.name, (step,))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """Files in a package's install folder or its App Execution Alias folder."""
        parts = path_parts(path)
        installs = under(parts, env_dir("ProgramFiles", "WindowsApps"))
        if installs:
            name = installs[0].split("_", 1)[0]
            return Ownership(self.name, name, "exact") if NAME.match(name) else None
        aliases = under(parts, env_dir("LOCALAPPDATA", "Microsoft\\WindowsApps"))
        if aliases and len(aliases) >= 2:
            name = aliases[0].split("_", 1)[0]
            return Ownership(self.name, name, "exact") if NAME.match(name) else None
        return None

    def forget(self) -> None:
        """Drop cached reads after a mutation."""
        _MEMO.clear()
