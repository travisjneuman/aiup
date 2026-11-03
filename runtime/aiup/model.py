"""Shared data classes (design doc section 6.1).

Every package codes against these shapes. Change them only through the design
doc, because providers, the engine, the TUI and the commands all read them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class Target:
    """One install target for a tool on one channel."""

    channel: str                 # provider name, section 6.3
    package: str                 # package id, crate, module, URL, or command line
    flags: Tuple[str, ...] = ()  # only "--classic" today
    update_command: str = ""     # vendor channel: self-update command
    install_script: str = ""     # vendor channel: script URL


@dataclass(frozen=True)
class CatalogEntry:
    """One catalog tool with its macOS data and its Linux and Windows targets."""

    id: str
    category: str
    lifecycle: str
    label: str
    docs: str
    endpoint: str
    macos_kind: str
    macos_target: str
    targets: Mapping[str, Tuple[Target, ...]]   # "linux" / "windows" -> targets in default order
    defaults: Mapping[str, str]                 # "linux" / "windows" -> channel name or ""
    aliases: Tuple[str, ...]
    commands: Tuple[str, ...]
    processes: Tuple[str, ...]
    user_data: Mapping[str, Tuple[str, ...]]    # unexpanded paths per OS
    notes: str

    def targets_for(self, os_name: str) -> Tuple[Target, ...]:
        """Targets for one OS ("linux" or "windows"), in default order."""
        return tuple(self.targets.get(os_name, ()))

    def available_on(self, os_name: str) -> bool:
        """True when the catalog lists at least one target for this OS."""
        if os_name == "darwin":
            return True
        return bool(self.targets.get(os_name))


@dataclass(frozen=True)
class Installed:
    """A copy of a tool found on this computer."""

    version: str                 # "" when present but unreadable
    path: Optional[str]
    scope: str                   # "user" | "system" | "machine"
    channel: str


@dataclass(frozen=True)
class Latest:
    """The newest version a channel offers."""

    version: str                 # "" when unverified
    source: str                  # "registry", "pypi", "pacman", "winget", "vendor-endpoint", ...
    unverified_reason: str = ""
    pending: bool = False        # the manager says an update is waiting but names no version (flatpak)
    managed: str = ""            # set when another updater owns this copy (Microsoft Store): the note to show


@dataclass(frozen=True)
class Step:
    """One command the engine runs for an action."""

    argv: Tuple[str, ...]
    label: str                   # shown in progress and logs
    privilege: str = "none"      # one of PRIVILEGES below; "helper-sudo": the command runs sudo itself (AUR helper)
    interactive: bool = False    # needs the terminal (sudo prompt, AUR review)
    env: Mapping[str, str] = field(default_factory=dict)
    timeout: Optional[float] = None
    ok_codes: Tuple[int, ...] = (0,)
    download: str = ""           # script steps: URL the engine downloads first; argv gets the file path as {file}
    on_fail: str = "stop"        # "stop" | "next": on failure run the next step; on success skip exactly the next step
    confirm: str = ""            # a yes/no question the engine asks first ("Add and trust tap X?"); default no


@dataclass(frozen=True)
class Action:
    """What a provider wants done for one tool: an install, update or remove."""

    tool: str
    op: str                      # "install" | "update" | "remove"
    channel: str
    steps: Tuple[Step, ...]
    note: str = ""
    result: str = ""             # empty steps only: "skipped" | "deferred" | "self-updated" | "failed"; "" means failed for install, skipped otherwise


@dataclass(frozen=True)
class PackageRecord:
    """One package-manager inventory row."""

    manager: str
    name: str
    version: str
    scope: str
    explicit: bool               # installed on request, not as a dependency
    paths: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Ownership:
    """Which manager owns a path."""

    manager: str
    package: str
    confidence: str              # "exact" (manager said so) | "prefix" (path is under its root)


@dataclass
class ToolResult:
    """One row of aiup-run-v1 / aiup-check-v1."""

    tool: str
    result: str                  # same vocabulary as docs/scripting.md
    before: str = ""
    after: str = ""
    installed: str = ""
    latest: str = ""
    channel: str = ""
    note: str = ""
    warning: bool = False
    duration: int = 0


# The note for an update that waits without a version number (Latest.pending).
PENDING_UPDATE_NOTE = "An update is waiting; its version is not published."

PRIVILEGES = ("none", "sudo", "helper-sudo", "uac-possible", "elevated-required", "polkit")
EMPTY_RESULTS = ("skipped", "deferred", "self-updated", "failed")
OPERATIONS = ("install", "update", "remove")
SCOPES = ("user", "system", "machine")
