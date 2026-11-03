"""The cell grammar of catalog/platforms.tsv (design doc section 5.3).

    cell     = "" | target *( ";" target )
    target   = plain | prefixed
    plain    = package [ " " flag ]     ; only in manager columns
    prefixed = prefix ":" value         ; only in *_other columns, and
                                        ; aur: / msstore: / remote: in their own columns

Every value is checked against a strict pattern for its channel, so catalog
data cannot slip extra arguments into a command line. The only flag allowed is
snap ``--classic``. ``script:URL;vendor:CMD`` in one cell becomes one ``vendor``
target that updates with CMD and falls back to the script.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Pattern, Tuple
from urllib.parse import urlsplit

from aiup.errors import CatalogError
from aiup.model import Target

OS_NAMES = ("linux", "windows")

# platforms.tsv columns 2 to 12, with the channel a plain value in each means.
MANAGER_COLUMNS: Dict[str, Tuple[str, str]] = {
    "linux_arch": ("linux", "pacman"),
    "linux_apt": ("linux", "apt"),
    "linux_dnf": ("linux", "dnf"),
    "linux_flatpak": ("linux", "flatpak"),
    "linux_snap": ("linux", "snap"),
    "linux_brew": ("linux", "brew"),
    "windows_winget": ("windows", "winget"),
    "windows_scoop": ("windows", "scoop"),
    "windows_choco": ("windows", "choco"),
}
OTHER_COLUMNS: Dict[str, str] = {"linux_other": "linux", "windows_other": "windows"}
TARGET_COLUMNS: Tuple[str, ...] = (
    "linux_arch", "linux_apt", "linux_dnf", "linux_flatpak", "linux_snap", "linux_brew",
    "linux_other", "windows_winget", "windows_scoop", "windows_choco", "windows_other",
)

OTHER_PREFIXES: Dict[str, Tuple[str, ...]] = {
    "linux": ("npm", "uv", "pipx", "cargo", "go", "nix", "script", "vendor"),
    "windows": ("npm", "uv", "pipx", "cargo", "go", "script", "vendor"),
}

# Section 5.4: static precedence after the row's own default. Distro managers
# that do not match this computer are filtered out by the engine, which knows
# what is available here.
CHANNEL_ORDER: Dict[str, Tuple[str, ...]] = {
    "linux": ("vendor", "script", "npm", "uv", "pipx", "cargo", "go",
              "pacman", "aur", "apt", "dnf", "brew", "flatpak", "snap", "nix"),
    "windows": ("vendor", "script", "npm", "uv", "pipx", "cargo", "go",
                "winget", "scoop", "choco"),
}

_NAME = r"[A-Za-z0-9][A-Za-z0-9._+-]*"
PATTERNS: Dict[str, Pattern[str]] = {
    "pacman": re.compile(r"(?:[a-z0-9][a-z0-9._-]*/)?[a-z0-9@_+][a-z0-9@._+-]*"),
    "aur": re.compile(r"[a-z0-9@_+][a-z0-9@._+-]*"),
    "apt": re.compile(r"[a-z0-9][a-z0-9.+-]+"),
    "dnf": re.compile(_NAME),
    "flatpak": re.compile(r"(?:[A-Za-z0-9][A-Za-z0-9._-]*:)?[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)+"),
    "snap": re.compile(r"[a-z0-9][a-z0-9-]*"),
    "brew": re.compile(r"(?:[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*/)?[a-z0-9][a-z0-9@+_.-]*"),
    "winget": re.compile(r"(?:msstore:[A-Za-z0-9]+|[A-Za-z0-9][A-Za-z0-9_+-]*(?:\.[A-Za-z0-9_+-]+)+)"),
    "scoop": re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._@+-]*"),
    "choco": re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*"),
    "npm": re.compile(r"(?:@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*"),
    "uv": re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?(?:\[[A-Za-z0-9._,-]+\])?"),
    "pipx": re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?(?:\[[A-Za-z0-9._,-]+\])?"),
    "cargo": re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*"),
    "go": re.compile(r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:/[A-Za-z0-9._~-]+)+"),
    "nix": re.compile(r"[A-Za-z0-9_][A-Za-z0-9._+-]*"),
}
_VENDOR_COMMAND = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
_VENDOR_ARG = re.compile(r"[A-Za-z0-9._/@:=+,~-]+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
SNAP_FLAGS = ("--classic",)


@dataclass(frozen=True)
class CellRef:
    """Where a cell came from, for error messages."""

    path: str
    line: int
    column: str
    index: int

    def location(self) -> str:
        """``catalog/platforms.tsv line 12, column linux_apt (3)``."""
        return "{} line {}, column {} ({})".format(self.path, self.line, self.column, self.index)


def _fail(ref: CellRef, message: str) -> CatalogError:
    return CatalogError(message, ref.location())


def _check_value(ref: CellRef, channel: str, value: str) -> None:
    pattern = PATTERNS[channel]
    if not pattern.fullmatch(value):
        raise _fail(ref, "'{}' is not a valid {} target".format(value, channel))


def _check_vendor(ref: CellRef, value: str) -> None:
    words = value.split(" ")
    if not words or not _VENDOR_COMMAND.fullmatch(words[0]):
        raise _fail(ref, "vendor command must start with a command name: '{}'".format(value))
    for word in words[1:]:
        if not _VENDOR_ARG.fullmatch(word):
            raise _fail(ref, "vendor command has an unsafe word '{}'".format(word))


def check_script_url(ref: CellRef, os_name: str, url: str) -> None:
    """A script URL must be HTTPS; on Windows it must also end in .ps1."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or " " in url:
        raise _fail(ref, "script URL must be HTTPS: '{}'".format(url))
    if os_name == "windows" and not parts.path.lower().endswith(".ps1"):
        raise _fail(ref, "Windows script URL must end in .ps1: '{}'".format(url))


def _split(ref: CellRef, cell: str) -> List[str]:
    if _CONTROL.search(cell):
        raise _fail(ref, "control character in cell")
    parts = cell.split(";")
    for part in parts:
        if not part or part != part.strip():
            raise _fail(ref, "empty target or stray space around ';' in '{}'".format(cell))
    return parts


def _manager_target(ref: CellRef, channel: str, raw: str) -> Target:
    package = raw
    flags: Tuple[str, ...] = ()
    if " " in raw:
        package, _, flag = raw.partition(" ")
        if channel != "snap" or flag not in SNAP_FLAGS:
            raise _fail(ref, "flag '{}' is not allowed here (only snap --classic)".format(flag))
        flags = (flag,)
    if channel == "pacman" and package.startswith("aur:"):
        channel, package = "aur", package[len("aur:"):]
    _check_value(ref, channel, package)
    return Target(channel=channel, package=package, flags=flags)


def _other_target(ref: CellRef, os_name: str, raw: str) -> Target:
    prefix, sep, value = raw.partition(":")
    if not sep or prefix not in OTHER_PREFIXES[os_name]:
        allowed = ", ".join(p + ":" for p in OTHER_PREFIXES[os_name])
        raise _fail(ref, "'{}' needs one of the prefixes {}".format(raw, allowed))
    if not value:
        raise _fail(ref, "'{}' has no value after the prefix".format(raw))
    if prefix == "script":
        check_script_url(ref, os_name, value)
        return Target(channel="script", package=value, install_script=value)
    if prefix == "vendor":
        _check_vendor(ref, value)
        return Target(channel="vendor", package=value, update_command=value)
    _check_value(ref, prefix, value)
    return Target(channel=prefix, package=value)


def _merge_vendor(ref: CellRef, targets: List[Target]) -> List[Target]:
    """Fold ``script:URL;vendor:CMD`` into one vendor target (section 5.3)."""
    scripts = [t for t in targets if t.channel == "script"]
    vendors = [t for t in targets if t.channel == "vendor"]
    if len(scripts) > 1 or len(vendors) > 1:
        raise _fail(ref, "at most one script: and one vendor: target per cell")
    if not scripts or not vendors:
        return targets
    script, vendor = scripts[0], vendors[0]
    merged = Target(channel="vendor", package=vendor.package,
                    update_command=vendor.update_command, install_script=script.install_script)
    first = min(targets.index(script), targets.index(vendor))
    out = [t for t in targets if t is not script and t is not vendor]
    out.insert(first, merged)
    return out


def parse_cell(ref: CellRef, cell: str) -> Tuple[Target, ...]:
    """Parse one platforms.tsv target cell. Raises CatalogError on bad input."""
    if cell == "":
        return ()
    raws = _split(ref, cell)
    if ref.column in MANAGER_COLUMNS:
        _, channel = MANAGER_COLUMNS[ref.column]
        return tuple(_manager_target(ref, channel, raw) for raw in raws)
    if ref.column in OTHER_COLUMNS:
        os_name = OTHER_COLUMNS[ref.column]
        targets = [_other_target(ref, os_name, raw) for raw in raws]
        return tuple(_merge_vendor(ref, targets))
    raise _fail(ref, "not a target column")


def channel_rank(os_name: str, channel: str) -> int:
    """Position of a channel in the static order of section 5.4."""
    order = CHANNEL_ORDER.get(os_name, ())
    return order.index(channel) if channel in order else len(order)


def order_targets(os_name: str, targets: Tuple[Target, ...], default: str) -> Tuple[Target, ...]:
    """Sort targets: the row's default channel first, then the section 5.4 order.

    Targets on the same channel keep their order from the file.
    """
    indexed = list(enumerate(targets))
    indexed.sort(key=lambda item: (
        0 if default and item[1].channel == default else 1,
        channel_rank(os_name, item[1].channel),
        item[0],
    ))
    return tuple(target for _, target in indexed)


def check_default(ref: CellRef, os_name: str, default: str, targets: Tuple[Target, ...]) -> str:
    """A default must name a channel that has a target for that OS in this row."""
    if default == "":
        return ""
    if default not in CHANNEL_ORDER[os_name]:
        raise _fail(ref, "'{}' is not a {} channel".format(default, os_name))
    if not any(t.channel == default for t in targets):
        raise _fail(ref, "default '{}' has no {} target in this row".format(default, os_name))
    return default


def first_channel(targets: Tuple[Target, ...]) -> Optional[str]:
    """The channel of the first target, or None when there are none."""
    return targets[0].channel if targets else None
