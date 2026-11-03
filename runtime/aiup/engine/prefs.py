"""preferences.json, channels.tsv and settings (design doc sections 2.1, 6.5, 7.3, 9.2).

``preferences.json`` keeps the macOS format: ``excluded``, ``holds``,
``groups``, ``cleanup``, ``welcomed``. This runtime adds two keys, ``system``
(report | ask | auto) and ``aur`` (review | trust). Keys this runtime does not
know are kept as they are when the file is written.

``channels.tsv`` holds one ``tool<TAB>channel`` pick per line and the policy
as ``*<TAB>policy`` (macOS ``channels_load`` / ``channels_write``).

Every write holds ``.preferences.lock`` (a folder made with mkdir, as on
macOS), writes ``next.json`` inside it, and moves it into place. Symbolic
links are refused.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import AbstractSet, Callable, Dict, List, Mapping, Optional, Tuple

from aiup.errors import AiupError
from aiup.paths import Dirs, ensure_dir, private_mkdir

from aiup.engine.cache import atomic_write_text, read_text_bounded

PREFERENCES_FILE = "preferences.json"
CHANNELS_FILE = "channels.tsv"
LOCK_NAME = ".preferences.lock"
MAX_FILE_BYTES = 1024 * 1024

GROUP_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
PACKAGE_ID = re.compile(r"pkg:[a-z0-9][a-z0-9-]*:[A-Za-z0-9@+._/:-]+")
TOOL_ID = re.compile(r"[a-z0-9][a-z0-9-]*")

SYSTEM_SETTINGS = ("report", "ask", "auto")
AUR_SETTINGS = ("review", "trust")
CLEANUP_SETTINGS = ("auto", "review")

COMMON_POLICIES = ("newest", "keep")
LINUX_POLICIES = ("system", "pacman", "aur", "apt", "dnf", "zypper", "brew", "flatpak", "snap", "nix")
WINDOWS_POLICIES = ("system", "winget", "scoop", "choco")


class PreferencesError(AiupError):
    """preferences.json or channels.tsv could not be read or changed."""

    def __init__(self, message: str) -> None:
        super().__init__("Preferences: " + message)


@dataclass(frozen=True)
class Settings:
    """The user settings the engine follows (``aiup settings``)."""

    system: str = "ask"      # 7.3: report | ask | auto
    aur: str = "review"      # 7.2: review | trust
    cleanup: str = "auto"    # stored for portability; no effect here


@dataclass
class Preferences:
    """The contents of preferences.json."""

    excluded: List[str] = field(default_factory=list)
    holds: Dict[str, str] = field(default_factory=dict)
    groups: Dict[str, List[str]] = field(default_factory=dict)
    cleanup: str = "auto"
    welcomed: bool = False
    system: str = "ask"
    aur: str = "review"
    extra: Dict[str, object] = field(default_factory=dict)

    def settings(self) -> Settings:
        """The settings part."""
        return Settings(system=self.system, aur=self.aur, cleanup=self.cleanup)

    def to_json(self) -> Dict[str, object]:
        """The document written to disk (unknown keys kept)."""
        data: Dict[str, object] = dict(self.extra)
        data.update({"excluded": list(self.excluded), "holds": dict(self.holds),
                     "groups": {name: list(tools) for name, tools in self.groups.items()},
                     "cleanup": self.cleanup})
        if self.welcomed:
            data["welcomed"] = True
        if self.system != "ask":
            data["system"] = self.system
        if self.aur != "review":
            data["aur"] = self.aur
        return data


# ----- ids -------------------------------------------------------------------


class IdRules:
    """Which ids preferences accept: catalog ids plus ``pkg:<manager>:<name>``."""

    def __init__(self, catalog_ids: AbstractSet[str]) -> None:
        self.catalog_ids = catalog_ids

    def valid(self, tool: str) -> bool:
        """An id that exclusions and holds may name."""
        return tool in self.catalog_ids or bool(PACKAGE_ID.fullmatch(tool))

    def managed(self, tool: str) -> bool:
        """An id a group may hold (catalog tools only, as on macOS)."""
        return tool in self.catalog_ids


def today() -> str:
    """Today's date as YYYY-MM-DD."""
    return datetime.date.today().isoformat()


def policy_reason(prefs: Preferences, tool: str, on: Optional[str] = None) -> str:
    """Why a run leaves ``tool`` alone, or "" (macOS ``preferences reason``)."""
    if tool in prefs.excluded:
        return "Excluded by preference; aiup include " + tool + " to restore"
    until = prefs.holds.get(tool, "")
    if until and until >= (on or today()):
        return "Held through " + until + "; aiup unhold " + tool + " to restore"
    return ""


# ----- reading -----------------------------------------------------------------


def preferences_path(dirs: Dirs) -> Path:
    """Where preferences.json lives."""
    return dirs.config / PREFERENCES_FILE


def load_preferences(dirs: Dirs, ids: IdRules) -> Preferences:
    """Read and validate preferences.json. A missing file gives the defaults."""
    path = preferences_path(dirs)
    if path.is_symlink():
        raise PreferencesError("Refusing symbolic-link preferences")
    if not path.exists():
        return Preferences()
    text = read_text_bounded(path, MAX_FILE_BYTES)
    if text is None:
        raise PreferencesError("could not read " + str(path))
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise PreferencesError("Invalid preferences: " + str(exc)) from exc
    return _parse(data, ids)


def _parse(data: object, ids: IdRules) -> Preferences:
    if not isinstance(data, dict):
        raise PreferencesError("Invalid preferences")
    excluded, holds, groups = data.get("excluded", []), data.get("holds", {}), data.get("groups", {})
    if not isinstance(excluded, list) or not isinstance(holds, dict) or not isinstance(groups, dict):
        raise PreferencesError("Invalid preferences")
    if any(not isinstance(tool, str) or not ids.valid(tool) for tool in excluded):
        raise PreferencesError("Unknown excluded tool")
    for tool, until in holds.items():
        if not ids.valid(tool):
            raise PreferencesError("Unknown held tool")
        _parse_date(until)
    for name, tools in groups.items():
        if (not GROUP_NAME.fullmatch(str(name)) or not isinstance(tools, list)
                or any(not isinstance(t, str) or not ids.managed(t) for t in tools)):
            raise PreferencesError("Invalid group")
    cleanup = _choice(data, "cleanup", CLEANUP_SETTINGS, "auto", "Invalid cleanup setting")
    system = _choice(data, "system", SYSTEM_SETTINGS, "ask", "Invalid system setting")
    aur = _choice(data, "aur", AUR_SETTINGS, "review", "Invalid aur setting")
    known = {"excluded", "holds", "groups", "cleanup", "welcomed", "system", "aur"}
    return Preferences(
        excluded=list(excluded), holds={str(k): str(v) for k, v in holds.items()},
        groups={str(k): list(v) for k, v in groups.items()}, cleanup=cleanup,
        welcomed=data.get("welcomed") is True, system=system, aur=aur,
        extra={k: v for k, v in data.items() if k not in known},
    )


def _choice(data: Mapping[str, object], key: str, allowed: Tuple[str, ...], default: str, error: str) -> str:
    value = data.get(key, default)
    if value not in allowed:
        raise PreferencesError(error)
    return str(value)


def _parse_date(text: object) -> datetime.date:
    try:
        return datetime.date.fromisoformat(str(text))
    except ValueError as exc:
        raise PreferencesError("Invalid date: " + str(text)) from exc


def read_settings(dirs: Dirs) -> Settings:
    """Only the settings keys, read leniently: a bad or missing value gives its default.

    Runs use this so a damaged preferences.json never stops an update; the
    commands that edit preferences use :func:`load_preferences` and report it.
    """
    data = None
    path = preferences_path(dirs)
    if not path.is_symlink():
        text = read_text_bounded(path, MAX_FILE_BYTES)
        try:
            data = json.loads(text) if text else None
        except ValueError:
            data = None
    if not isinstance(data, dict):
        return Settings()
    def pick(key: str, allowed: Tuple[str, ...], default: str) -> str:
        value = data.get(key) if isinstance(data, dict) else None
        return str(value) if value in allowed else default
    return Settings(system=pick("system", SYSTEM_SETTINGS, "ask"),
                    aur=pick("aur", AUR_SETTINGS, "review"),
                    cleanup=pick("cleanup", CLEANUP_SETTINGS, "auto"))


# ----- writing -----------------------------------------------------------------


def edit_preferences(dirs: Dirs, ids: IdRules, change: Callable[[Preferences], None],
                     dry_run: bool = False) -> Preferences:
    """Read, change and save preferences.json under the macOS lock folder.

    ``change`` edits the object in place and may raise :class:`PreferencesError`.
    With ``dry_run`` nothing is written. Prints nothing; callers say
    "Preferences saved."
    """
    ensure_dir(dirs.config)
    lock = dirs.config / LOCK_NAME
    try:
        private_mkdir(lock)
    except FileExistsError as exc:
        raise PreferencesError("Preferences are being edited; retry after the other command finishes") from exc
    except OSError as exc:
        raise PreferencesError(str(exc)) from exc
    temp = lock / "next.json"
    try:
        prefs = load_preferences(dirs, ids)
        change(prefs)
        if not dry_run:
            _write_locked(temp, preferences_path(dirs), prefs)
        return prefs
    finally:
        try:
            if temp.exists():
                temp.unlink()
            lock.rmdir()
        except OSError:
            pass


def _write_locked(temp: Path, target: Path, prefs: Preferences) -> None:
    if target.is_symlink():
        raise PreferencesError("Refusing symbolic-link preferences")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(temp), flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(prefs.to_json(), handle, indent=2)
        handle.write("\n")
    os.replace(temp, target)


def exclude(prefs: Preferences, ids: IdRules, tool: str) -> None:
    """Add an exclusion."""
    _require_id(ids, tool)
    prefs.excluded = sorted(set(prefs.excluded + [tool]))


def include(prefs: Preferences, ids: IdRules, tool: str) -> None:
    """Remove an exclusion."""
    _require_id(ids, tool)
    prefs.excluded = [t for t in prefs.excluded if t != tool]


def hold(prefs: Preferences, ids: IdRules, tool: str, until: str) -> None:
    """Hold a tool through a date that is today or later."""
    _require_id(ids, tool)
    date = _parse_date(until)
    if date < datetime.date.today():
        raise PreferencesError("Hold date must be today or later")
    prefs.holds[tool] = date.isoformat()


def unhold(prefs: Preferences, ids: IdRules, tool: str) -> None:
    """Remove a hold."""
    _require_id(ids, tool)
    prefs.holds.pop(tool, None)


def _require_id(ids: IdRules, tool: str) -> None:
    if not ids.valid(tool):
        raise PreferencesError("Use a catalog ID or a pkg:<manager>:<name> package ID")


def set_group(prefs: Preferences, ids: IdRules, name: str, tools: List[str]) -> None:
    """Create or replace a group of managed tools."""
    if not GROUP_NAME.fullmatch(name) or not tools or any(not ids.managed(t) for t in tools):
        raise PreferencesError("Use a simple group name and managed tool IDs")
    prefs.groups[name] = list(dict.fromkeys(tools))


def remove_group(prefs: Preferences, name: str) -> None:
    """Delete a group (no error when it does not exist)."""
    prefs.groups.pop(name, None)


def group_tools(prefs: Preferences, name: str) -> List[str]:
    """The tools of one group."""
    if name not in prefs.groups:
        raise PreferencesError("Unknown group: " + name)
    return list(prefs.groups[name])


def set_setting(prefs: Preferences, key: str, value: str, os_name: str) -> None:
    """``aiup settings KEY VALUE`` for cleanup, system and aur."""
    if key == "cleanup":
        if value not in CLEANUP_SETTINGS:
            raise PreferencesError("Choose auto or review")
        prefs.cleanup = value
    elif key == "system":
        if value not in SYSTEM_SETTINGS:
            raise PreferencesError("Choose report, ask or auto")
        prefs.system = value
    elif key == "aur":
        if os_name != "linux":
            raise AiupError("AUR is Linux only")
        if value not in AUR_SETTINGS:
            raise PreferencesError("Choose review or trust")
        prefs.aur = value
    else:
        raise PreferencesError("Unknown setting: " + key)


def merge(prefs: Preferences, ids: IdRules, incoming: object) -> None:
    """``aiup import``: add another computer's preferences to these.

    Exclusions are added, a later hold date wins, a group of the same name is
    replaced, and cleanup, system and aur are taken from the file when valid
    (macOS ``preferences merge``). Unknown ids are skipped.
    """
    if not isinstance(incoming, dict):
        raise PreferencesError("Invalid imported preferences")
    for tool in incoming.get("excluded") or []:
        if isinstance(tool, str) and ids.valid(tool) and tool not in prefs.excluded:
            prefs.excluded.append(tool)
    prefs.excluded = sorted(prefs.excluded)
    holds = incoming.get("holds") or {}
    if isinstance(holds, dict):
        for tool, until in holds.items():
            if not ids.valid(str(tool)):
                continue  # unknown ids are skipped before their dates are read
            date = _parse_date(until).isoformat()
            if date > prefs.holds.get(str(tool), ""):
                prefs.holds[str(tool)] = date
    groups = incoming.get("groups") or {}
    if isinstance(groups, dict):
        for name, tools in groups.items():
            kept = [t for t in tools if isinstance(t, str) and ids.managed(t)] if isinstance(tools, list) else []
            if GROUP_NAME.fullmatch(str(name)) and kept:
                prefs.groups[str(name)] = list(dict.fromkeys(kept))
    if incoming.get("cleanup") in CLEANUP_SETTINGS:
        prefs.cleanup = str(incoming["cleanup"])
    if incoming.get("system") in SYSTEM_SETTINGS:
        prefs.system = str(incoming["system"])
    if incoming.get("aur") in AUR_SETTINGS:
        prefs.aur = str(incoming["aur"])


def mark_welcomed(prefs: Preferences) -> None:
    """Record that the welcome guide was shown."""
    prefs.welcomed = True


# ----- channels.tsv --------------------------------------------------------------


@dataclass(frozen=True)
class ChannelChoices:
    """The policy and the per-tool picks from channels.tsv."""

    policy: str = "newest"
    picks: Mapping[str, str] = field(default_factory=dict)


def policies_for(os_name: str) -> Tuple[str, ...]:
    """Policies ``aiup channel --policy`` accepts on this OS."""
    if os_name == "windows":
        return COMMON_POLICIES + WINDOWS_POLICIES
    if os_name == "linux":
        return COMMON_POLICIES + LINUX_POLICIES
    return COMMON_POLICIES + ("brew",)


def channels_path(dirs: Dirs) -> Path:
    """Where channels.tsv lives."""
    return dirs.config / CHANNELS_FILE


def load_channels(dirs: Dirs, os_name: str) -> ChannelChoices:
    """Read channels.tsv. Bad lines are skipped; the first pick per tool wins."""
    path = channels_path(dirs)
    if path.is_symlink():
        return ChannelChoices()
    text = read_text_bounded(path, MAX_FILE_BYTES)
    if not text:
        return ChannelChoices()
    policy = "newest"
    picks: Dict[str, str] = {}
    allowed = policies_for(os_name)
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        tool, name = fields[0], fields[1].strip()
        if tool == "*":
            if name in allowed:
                policy = name
            continue
        if not TOOL_ID.fullmatch(tool) or tool in picks or not TOOL_ID.fullmatch(name):
            continue
        picks[tool] = name
    return ChannelChoices(policy=policy, picks=picks)


def write_channel(dirs: Dirs, tool: str, name: str) -> None:
    """Set (``name``) or clear (``""``) one line of channels.tsv.

    ``tool`` "*" sets the policy; "newest" is stored as no line, as on macOS.
    """
    path = channels_path(dirs)
    if path.is_symlink():
        raise AiupError("Refusing to write through a symlink: " + str(path))
    old = read_text_bounded(path, MAX_FILE_BYTES) or ""
    kept = [line for line in old.splitlines() if line and line.split("\t", 1)[0] != tool]
    if name and not (tool == "*" and name == "newest"):
        kept.append(tool + "\t" + name)
    atomic_write_text(path, "".join(line + "\n" for line in kept))
