"""Homebrew formulae on Linux (Homebrew on Linux). Design doc 6.3.

Ported from the brew parts of macos/aiup:

- brew always runs as the user, never under sudo, and never as root.
- Every read sets ``HOMEBREW_NO_AUTO_UPDATE=1`` and ``HOMEBREW_NO_ENV_HINTS=1``
  so a check never updates Homebrew. ``metadata_refresh`` runs
  ``brew update --auto-update --quiet`` instead, unless the user set
  ``HOMEBREW_NO_AUTO_UPDATE`` themselves.
- Installed formulae are read from the Cellar's install receipts, without
  starting brew. Pending upgrades come from one ``brew outdated --json=v2``.
- A formula from a tap that is not added yet needs the user's OK: the
  install starts with ``brew tap USER/REPO`` as an interactive step, and the
  action's note names the tap. Core taps need no OK.
- Bottle attestation checks are turned on when gh is installed and signed in
  (or ``HOMEBREW_GITHUB_API_TOKEN`` is set), unless
  ``AIUP_BREW_ATTESTATIONS=0`` or ``HOMEBREW_NO_VERIFY_ATTESTATIONS`` is set.
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Mapping, NamedTuple, Optional, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers._linux import (
    INVENTORY_MAX_BYTES, LOCKED_NOTE, Memo, is_linux, mtime_of, posix_lock_held, run_c, user_step, which,
)
from aiup.versions import version_cmp

if TYPE_CHECKING:
    from aiup.engine.context import Context

READ_ENV = ("HOMEBREW_NO_AUTO_UPDATE=1", "HOMEBREW_NO_ENV_HINTS=1")
STEP_ENV = {"HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_ENV_HINTS": "1"}
TRUSTED_TAPS = frozenset({"homebrew/core", "homebrew/cask", "homebrew/bundle", "homebrew/services"})
FALLBACK_BREWS = ("/home/linuxbrew/.linuxbrew/bin/brew", "~/.linuxbrew/bin/brew")
RECEIPT_MAX_BYTES = 1024 * 1024
MEMO_TTL = 300.0
QUERY_TIMEOUT = 30.0
_MEMO = Memo()


class Formula(NamedTuple):
    """One installed formula."""

    name: str
    version: str           # Cellar folder name, for example "1.2.3_1"
    tap: str
    explicit: bool


def brew_path(ctx: "Context") -> Optional[str]:
    """The brew command: on PATH, else the standard Linux prefixes."""
    found = which(ctx, "brew")
    if found:
        return found
    for candidate in FALLBACK_BREWS:
        path = os.path.expanduser(candidate)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def brew_prefix(brew: str) -> Path:
    """The Homebrew prefix that holds ``Cellar``.

    ``brew`` may be a symlink from another folder (``~/.local/bin/brew``), so
    the real file decides. It lives in ``<prefix>/Homebrew/bin`` on Linux
    and in ``<prefix>/bin`` when the repository is the prefix.
    """
    real = Path(os.path.realpath(brew))
    repository = real.parent.parent
    if repository.name == "Homebrew" and (repository.parent / "Cellar").is_dir():
        return repository.parent
    if (repository / "Cellar").is_dir():
        return repository
    return Path(brew).parent.parent


def split_formula(target: Target) -> Tuple[str, str]:
    """``user/repo/name`` -> (``user/repo``, ``name``); a plain name has no tap."""
    parts = target.package.split("/")
    if len(parts) == 3:
        return "{}/{}".format(parts[0], parts[1]).lower(), parts[2]
    return "", target.package


def tap_added(prefix: Path, tap: str) -> bool:
    """True when ``user/repo`` is cloned under the Homebrew repository's Taps."""
    user, _, repo = tap.partition("/")
    for library in (prefix / "Homebrew" / "Library", prefix / "Library"):
        if (library / "Taps" / user / ("homebrew-" + repo)).is_dir():
            return True
    return False


def _read_receipt(folder: Path) -> Tuple[str, bool]:
    """(tap, installed on request) from an INSTALL_RECEIPT.json."""
    try:
        with open(str(folder / "INSTALL_RECEIPT.json"), "r", encoding="utf-8") as handle:
            data = json.loads(handle.read(RECEIPT_MAX_BYTES))
    except (OSError, ValueError):
        return "", True
    if not isinstance(data, dict):
        return "", True
    source = data.get("source")
    tap = source.get("tap") if isinstance(source, dict) else ""
    return (tap if isinstance(tap, str) else ""), bool(data.get("installed_on_request", True))


def _active_version(prefix: Path, name: str, versions: List[str]) -> str:
    """The linked version (``opt/<name>``), else the newest Cellar folder."""
    try:
        linked = Path(os.path.realpath(str(prefix / "opt" / name)))
        if linked.parent == prefix / "Cellar" / name and linked.name in versions:
            return linked.name
    except (OSError, ValueError):
        pass
    best = versions[0]
    for version in versions[1:]:
        if version_cmp(version, best) > 0:
            best = version
    return best


def _scan_cellar(prefix: Path) -> Dict[str, Formula]:
    """Every installed formula from the Cellar, without starting brew."""
    cellar = prefix / "Cellar"
    formulae: Dict[str, Formula] = {}
    try:
        names = sorted(entry.name for entry in os.scandir(str(cellar)) if entry.is_dir())
    except OSError:
        return formulae
    for name in names:
        try:
            versions = sorted(entry.name for entry in os.scandir(str(cellar / name)) if entry.is_dir())
        except OSError:
            continue
        if not versions:
            continue
        version = _active_version(prefix, name, versions)
        tap, explicit = _read_receipt(cellar / name / version)
        formulae[name] = Formula(name, version, tap, explicit)
    return formulae


def installed_formulae(prefix: Path) -> Dict[str, Formula]:
    """Installed formulae, cached until the Cellar changes."""
    stamp = "cellar:{}:{}".format(prefix, mtime_of(str(prefix / "Cellar")))
    return _MEMO.get(stamp, MEMO_TTL, lambda: _scan_cellar(prefix))


def _formula_version(item: Mapping[str, object]) -> str:
    """``stable`` plus ``_revision`` from ``brew info --json=v2``."""
    versions = item.get("versions")
    stable = versions.get("stable") if isinstance(versions, dict) else None
    if not isinstance(stable, str) or not stable:
        return ""
    revision = item.get("revision")
    return "{}_{}".format(stable, revision) if isinstance(revision, int) and revision > 0 else stable


def _json_formulae(text: str) -> List[Mapping[str, object]]:
    """The ``formulae`` list of a ``--json=v2`` answer."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    items = data.get("formulae") if isinstance(data, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


class BrewProvider(Provider):
    """Homebrew formulae, run as the user."""

    name = "brew"
    oses = frozenset({"linux"})
    scope = "user"
    lane = "brew"
    exclusive = False
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        """True with a brew command, when aiup is not running as root."""
        return is_linux(ctx) and os.geteuid() != 0 and brew_path(ctx) is not None

    def _brew(self, ctx: "Context") -> str:
        """The brew command. Only called after ``available``."""
        return brew_path(ctx) or "brew"

    def _read(self, ctx: "Context", *words: str) -> Tuple[Optional[int], str]:
        """A brew read that never updates Homebrew."""
        result = run_c(ctx, (self._brew(ctx),) + words, timeout=QUERY_TIMEOUT,
                       max_bytes=INVENTORY_MAX_BYTES, env=READ_ENV)
        return result.code, result.out

    def _outdated_map(self, ctx: "Context") -> Optional[Dict[str, Tuple[str, bool]]]:
        """{name: (current version, pinned)} from one ``brew outdated``. None on failure."""

        def produce() -> Optional[Dict[str, Tuple[str, bool]]]:
            code, out = self._read(ctx, "outdated", "--json=v2", "--formula")
            if code != 0:
                return None
            found: Dict[str, Tuple[str, bool]] = {}
            for item in _json_formulae(out):
                name, current = item.get("name"), item.get("current_version")
                if isinstance(name, str) and isinstance(current, str):
                    found[name.rsplit("/", 1)[-1]] = (current, bool(item.get("pinned")))
            return found

        prefix = brew_prefix(self._brew(ctx))
        return _MEMO.get("outdated:{}".format(mtime_of(str(prefix / "Cellar"))), MEMO_TTL, produce)

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """The installed formula from the Cellar, or None."""
        _, name = split_formula(target)
        prefix = brew_prefix(self._brew(ctx))
        formula = installed_formulae(prefix).get(name)
        if formula is None:
            return None
        return Installed(version=formula.version, path=str(prefix / "opt" / name), scope="user", channel=self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """Newest version in the local tap data."""
        tap, name = split_formula(target)
        prefix = brew_prefix(self._brew(ctx))
        formula = installed_formulae(prefix).get(name)
        if formula is not None:
            outdated = self._outdated_map(ctx)
            if outdated is None:
                return Latest("", self.name, "brew outdated failed")
            if name in outdated:
                current, pinned = outdated[name]
                if pinned:
                    return Latest("", self.name, "pinned in Homebrew")
                return Latest(current, self.name)
            return Latest(formula.version, self.name)
        if tap and tap not in TRUSTED_TAPS and not tap_added(prefix, tap):
            return Latest("", self.name, "the Homebrew tap {} is not added".format(tap))
        code, out = self._read(ctx, "info", "--json=v2", "--formula", target.package)
        items = _json_formulae(out) if code == 0 else []
        version = _formula_version(items[0]) if items else ""
        if not version:
            return Latest("", self.name, "not found in Homebrew")
        return Latest(version, self.name)

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Every outdated formula that is not pinned, in one read."""
        outdated = self._outdated_map(ctx) or {}
        return {name: Latest(current, self.name) for name, (current, pinned) in outdated.items() if not pinned}

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Every installed formula."""
        prefix = brew_prefix(self._brew(ctx))
        return tuple(PackageRecord(manager=self.name, name=f.name, version=f.version, scope="user",
                                   explicit=f.explicit, paths=(str(prefix / "opt" / f.name),))
                     for f in installed_formulae(prefix).values())

    def _step_env(self, ctx: "Context") -> Dict[str, str]:
        """Environment for brew steps: no auto-update, no hints, attestations when possible."""
        env = dict(STEP_ENV)
        if self._attestations(ctx):
            env["HOMEBREW_VERIFY_ATTESTATIONS"] = "1"
        return env

    def _attestations(self, ctx: "Context") -> bool:
        """True when bottle attestations can be checked (gh signed in, or a token is set)."""
        environ = getattr(ctx, "env", os.environ)
        if not getattr(getattr(ctx, "config", None), "brew_attestations", True):
            return False
        if environ.get("HOMEBREW_NO_VERIFY_ATTESTATIONS"):
            return False
        if environ.get("HOMEBREW_VERIFY_ATTESTATIONS"):
            return False  # the user's own value already reaches brew
        if which(ctx, "gh") is None:
            return False
        if environ.get("HOMEBREW_GITHUB_API_TOKEN"):
            return True
        return _MEMO.get("gh-auth", 3600.0, lambda: run_c(ctx, ("gh", "auth", "status")).code == 0)

    def _brew_step(self, ctx: "Context", words: Tuple[str, ...], label: str, interactive: bool = False) -> Step:
        """A brew step as the user."""
        return user_step((self._brew(ctx),) + words, label, interactive=interactive, env=self._step_env(ctx))

    def install(self, ctx: "Context", target: Target) -> Action:
        """``brew install --formula NAME``, after ``brew tap`` when the tap is not added yet."""
        tap, name = split_formula(target)
        prefix = brew_prefix(self._brew(ctx))
        steps: List[Step] = []
        note = ""
        if tap and tap not in TRUSTED_TAPS and not tap_added(prefix, tap):
            # The engine asks this question first; no, or no terminal, adds nothing.
            tap_step = self._brew_step(ctx, ("tap", tap), "brew tap " + tap)
            steps.append(replace(tap_step, confirm="Add and trust tap {}?".format(tap)))
            note = "This adds and trusts the Homebrew tap {} for {}. aiup asks first.".format(tap, name)
        steps.append(self._brew_step(ctx, ("install", "--formula", "--yes", target.package),
                                     "brew install " + target.package))
        return Action(tool=name, op="install", channel=self.name, steps=tuple(steps), note=note)

    def update(self, ctx: "Context", target: Target) -> Action:
        """``brew upgrade --formula NAME``."""
        _, name = split_formula(target)
        step = self._brew_step(ctx, ("upgrade", "--formula", "--yes", name), "brew upgrade " + name)
        return Action(tool=name, op="update", channel=self.name, steps=(step,))

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``brew uninstall --formula NAME``. brew refuses when another formula needs it."""
        _, name = split_formula(target)
        step = self._brew_step(ctx, ("uninstall", "--formula", name), "brew uninstall " + name)
        return Action(tool=name, op="remove", channel=self.name, steps=(step,))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """A path that resolves into ``Cellar/<formula>/``."""
        brew = brew_path(ctx)
        if brew is None:
            return None
        cellar = str(brew_prefix(brew) / "Cellar") + "/"
        real = os.path.realpath(path)
        if not real.startswith(cellar):
            return None
        name = real[len(cellar):].split("/", 1)[0]
        return Ownership(manager=self.name, package=name, confidence="exact") if name else None

    def metadata_refresh(self, ctx: "Context") -> Optional[Action]:
        """``brew update --auto-update --quiet``, unless the user turned auto-update off."""
        environ = getattr(ctx, "env", os.environ)
        if not self.available(ctx) or environ.get("HOMEBREW_NO_AUTO_UPDATE"):
            return None
        step = user_step((self._brew(ctx), "update", "--auto-update", "--quiet"), "brew update",
                         env={"HOMEBREW_NO_ENV_HINTS": "1"})
        return Action(tool="brew", op="update", channel=self.name, steps=(step,))

    def lock_held(self, ctx: "Context") -> str:
        """``LOCKED_NOTE`` while another brew holds one of its lock files."""
        brew = brew_path(ctx)
        if brew is None:
            return ""
        locks = glob.glob(str(brew_prefix(brew) / "var" / "homebrew" / "locks" / "*.lock"))
        return LOCKED_NOTE if posix_lock_held(locks) else ""

    def forget(self) -> None:
        """Drop cached reads after a step. An upgrade adds ``Cellar/<name>/<version>``,
        which leaves the Cellar folder's own mtime alone."""
        _MEMO.clear()
