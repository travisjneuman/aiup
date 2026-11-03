"""Scoop provider (user-scope Windows packages).

Reads never start PowerShell. Scoop keeps its state in plain files, so aiup
reads them directly (system detection research, section 5.3):

- ``<root>\\apps\\<app>\\current\\manifest.json`` holds the installed version and
  ``install.json`` beside it the bucket and a ``hold`` flag;
- ``<root>\\buckets\\<bucket>\\bucket\\<app>.json`` (or the bucket's top folder)
  holds the version the bucket offers, as of the bucket's last ``scoop update``;
- ``<root>\\shims\\<name>.shim`` has a ``path = "..."`` line naming the real file.

``<root>`` is ``%SCOOP%``, else ``root_path`` in Scoop's config file, else
``%USERPROFILE%\\scoop``. Global installs live under ``%SCOOP_GLOBAL%`` (default
``%ProgramData%\\scoop``) and are reported, but aiup never changes them: they
need an elevated terminal, and Scoop steps never ask for elevation (7.4).

Steps run Scoop's own ``scoop.ps1`` the way Scoop's shim does: PowerShell with
``-ExecutionPolicy Bypass -File``, which applies to that one process (6.7).
Catalog cells are ``bucket/app`` (or ``app`` for the main bucket).
"""

from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Mapping, NamedTuple, Optional, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.versions import version_cmp
from aiup.providers._win import (WINDOWS, any_powershell, env_dir, home_dir, is_windows, path_parts,
                                 powershell_env, read_json_file, read_text_file, under)

if TYPE_CHECKING:
    from aiup.engine.context import Context

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]*$")
DEFAULT_BUCKET = "main"
STEP_TIMEOUT = 3600.0
# ``scoop bucket known``: buckets Scoop can add by name alone.
KNOWN_BUCKETS = frozenset({
    "main", "extras", "versions", "nirsoft", "sysinternals", "php", "nerd-fonts", "nonportable", "java", "games",
})
_SHIM_PATH = re.compile(r'^\s*path\s*=\s*"?([^"\r\n]+)"?\s*$', re.MULTILINE | re.IGNORECASE)
_APPS_IN_TEXT = re.compile(r"[\\/]apps[\\/]([A-Za-z0-9][A-Za-z0-9._+\-]*)[\\/]", re.IGNORECASE)


class ScoopApp(NamedTuple):
    """One installed app as Scoop's files describe it."""

    name: str
    version: str
    bucket: str
    held: bool
    global_install: bool
    path: str


def split_target(target: Target) -> Tuple[str, str]:
    """``(bucket, app)`` from ``bucket/app``; the bucket is "" when the cell names only the app."""
    package = target.package.strip()
    if "/" in package:
        bucket, app = package.split("/", 1)
        return bucket.strip(), app.strip()
    return "", package


def valid(name: str) -> bool:
    """True for a bucket or app name aiup will pass to Scoop."""
    return bool(NAME.match(name))


def scoop_config() -> Mapping[str, object]:
    """Scoop's own config file (``%XDG_CONFIG_HOME%`` or ``~\\.config``), or {}."""
    base = env_dir("XDG_CONFIG_HOME") or home_dir() / ".config"
    value = read_json_file(base / "scoop" / "config.json")
    return value if isinstance(value, dict) else {}


def _configured(env_name: str, key: str, fallback: Optional[Path]) -> Optional[Path]:
    from_env = env_dir(env_name)
    if from_env is not None:
        return from_env
    configured = scoop_config().get(key)
    if isinstance(configured, str) and configured and Path(configured).is_absolute():
        return Path(configured)
    return fallback


def user_root() -> Path:
    """Scoop's user folder."""
    root = _configured("SCOOP", "root_path", None)
    return root if root is not None else home_dir() / "scoop"


def global_root() -> Optional[Path]:
    """Scoop's global folder, when ``%ProgramData%`` or a setting names one."""
    return _configured("SCOOP_GLOBAL", "global_path", env_dir("ProgramData", "scoop"))


def roots() -> Tuple[Tuple[Path, bool], ...]:
    """``(root, is_global)`` pairs, user first."""
    found: List[Tuple[Path, bool]] = [(user_root(), False)]
    other = global_root()
    if other is not None:
        found.append((other, True))
    return tuple(found)


def read_app(root: Path, name: str, global_install: bool) -> Optional[ScoopApp]:
    """The installed app ``name`` under ``root``, or None."""
    current = root / "apps" / name / "current"
    manifest = read_json_file(current / "manifest.json")
    if not isinstance(manifest, dict):
        return None
    install = read_json_file(current / "install.json")
    install = install if isinstance(install, dict) else {}
    bucket = str(install.get("bucket") or "")
    return ScoopApp(name=name, version=str(manifest.get("version") or ""), bucket=bucket,
                    held=bool(install.get("hold")), global_install=global_install, path=str(current))


def find_app(name: str) -> Optional[ScoopApp]:
    """The installed copy of ``name``, user scope first."""
    for root, is_global in roots():
        app = read_app(root, name, is_global)
        if app is not None:
            return app
    return None


def installed_apps() -> List[ScoopApp]:
    """Every installed app in both roots, except Scoop itself."""
    apps: List[ScoopApp] = []
    for root, is_global in roots():
        try:
            names = sorted(entry.name for entry in os.scandir(root / "apps") if entry.is_dir())
        except OSError:
            continue
        for name in names:
            if name.lower() == "scoop" or not valid(name):
                continue
            app = read_app(root, name, is_global)
            if app is not None:
                apps.append(app)
    return apps


def bucket_dir(bucket: str) -> Path:
    """Where Scoop keeps a bucket's checkout."""
    return user_root() / "buckets" / bucket


def bucket_version(bucket: str, app: str) -> Optional[str]:
    """The version a local bucket offers for ``app``; None when the bucket or manifest is missing."""
    base = bucket_dir(bucket)
    for manifest in (base / "bucket" / (app + ".json"), base / (app + ".json")):
        value = read_json_file(manifest)
        if isinstance(value, dict):
            return str(value.get("version") or "")
    return None


class ScoopProvider(Provider):
    """Scoop: portable apps in the user's own folder. Never needs elevation."""

    name = "scoop"
    oses = WINDOWS
    scope = "user"
    lane = "scoop"
    exclusive = False
    targeted_update = True

    def script(self) -> Path:
        """Scoop's entry script."""
        return user_root() / "apps" / "scoop" / "current" / "bin" / "scoop.ps1"

    def available(self, ctx: "Context") -> bool:
        """True when Scoop is installed for this user and PowerShell can run it."""
        return not self.unavailable_reason(ctx)

    def unavailable_reason(self, ctx: "Context") -> str:
        """Why Scoop cannot be used here, or ""."""
        if not is_windows(ctx):
            return "Scoop is Windows only"
        if not self.script().is_file():
            return "Scoop is not installed for this account"
        if any_powershell(ctx) is None:
            return "PowerShell was not found"
        return ""

    def argv(self, ctx: "Context", *args: str) -> Tuple[str, ...]:
        """A Scoop command line, the same way Scoop's own shim starts it."""
        shell = any_powershell(ctx) or "powershell.exe"
        return (shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                str(self.script())) + args

    def step(self, ctx: "Context", label: str, *args: str) -> Step:
        """One Scoop step. Never elevated."""
        argv = self.argv(ctx, *args)
        return Step(argv=argv, label=label, privilege="none", env=powershell_env(argv[0]), timeout=STEP_TIMEOUT)

    # ----- reads -----------------------------------------------------------

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """The installed copy, read from Scoop's files."""
        _bucket, app = split_target(target)
        if not valid(app) or not is_windows(ctx):
            return None
        found = find_app(app)
        if found is None:
            return None
        return Installed(version=found.version, path=found.path,
                         scope="machine" if found.global_install else "user", channel=self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """The version the app's bucket offers, as of the last ``scoop update``."""
        bucket, app = split_target(target)
        if not valid(app) or (bucket and not valid(bucket)):
            return Latest("", self.name, "not a Scoop app name: " + target.package)
        if not bucket:
            found = find_app(app)
            bucket = found.bucket if found is not None and found.bucket else DEFAULT_BUCKET
        version = bucket_version(bucket, app)
        if version is None:
            if not bucket_dir(bucket).is_dir():
                return Latest("", self.name, "the Scoop bucket {} is not added".format(bucket))
            return Latest("", self.name, "the Scoop bucket {} has no app {}".format(bucket, app))
        if not version:
            return Latest("", self.name, "the bucket manifest has no version")
        return Latest(version, self.name)

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Installed apps whose bucket offers another version, keyed ``bucket/app``."""
        if not self.available(ctx):
            return {}
        result: Dict[str, Latest] = {}
        for app in installed_apps():
            if not app.bucket or not valid(app.bucket):
                continue
            offered = bucket_version(app.bucket, app.name)
            if offered and app.version and version_cmp(offered, app.version) > 0:
                result[app.bucket + "/" + app.name] = Latest(offered, self.name)
        return result

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Every Scoop app, user and global."""
        if not is_windows(ctx):
            return ()
        return tuple(
            PackageRecord(manager=self.name, name=app.name, version=app.version,
                          scope="machine" if app.global_install else "user", explicit=True, paths=(app.path,))
            for app in installed_apps()
        )

    # ----- actions ---------------------------------------------------------

    def install(self, ctx: "Context", target: Target) -> Action:
        """``scoop install bucket/app``, adding a known bucket first when it is missing."""
        bucket, app = split_target(target)
        bucket = bucket or DEFAULT_BUCKET
        if not valid(app) or not valid(bucket):
            return Action(target.package, "install", self.name, (), "not a Scoop app name")
        steps: List[Step] = []
        note = ""
        if not bucket_dir(bucket).is_dir():
            if bucket.lower() not in KNOWN_BUCKETS:
                return Action(target.package, "install", self.name, (),
                              "the Scoop bucket {0} is not added; add it with scoop bucket add {0} <url>".format(bucket))
            add = self.step(ctx, "scoop bucket add " + bucket, "bucket", "add", bucket)
            steps.append(replace(add, confirm="Add the Scoop bucket {}?".format(bucket)))
            note = "adds the Scoop bucket {} first".format(bucket)
        steps.append(self.step(ctx, "scoop install " + app, "install", bucket + "/" + app))
        return Action(target.package, "install", self.name, tuple(steps), note)

    def update(self, ctx: "Context", target: Target) -> Action:
        """``scoop update app`` for a user install."""
        _bucket, app = split_target(target)
        if not valid(app):
            return Action(target.package, "update", self.name, (), "not a Scoop app name")
        found = find_app(app)
        if found is not None and found.global_install:
            return Action(target.package, "update", self.name, (), global_note("update", app))
        if found is not None and found.held:
            return Action(target.package, "update", self.name, (),
                          "held in Scoop; run scoop unhold {} to allow updates".format(app))
        return Action(target.package, "update", self.name, (self.step(ctx, "scoop update " + app, "update", app),))

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``scoop uninstall app``. Keeps the app's persisted data (no ``--purge``)."""
        _bucket, app = split_target(target)
        if not valid(app):
            return Action(target.package, "remove", self.name, (), "not a Scoop app name")
        found = find_app(app)
        if found is not None and found.global_install:
            return Action(target.package, "remove", self.name, (), global_note("uninstall", app))
        return Action(target.package, "remove", self.name,
                      (self.step(ctx, "scoop uninstall " + app, "uninstall", app),))

    def metadata_refresh(self, ctx: "Context") -> Optional[Action]:
        """``scoop update``: pulls Scoop and every bucket, so ``latest`` reads fresh manifests."""
        if not self.available(ctx):
            return None
        return Action("scoop", "update", self.name, (self.step(ctx, "scoop update", "update"),))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """Files under ``apps\\<app>``, and shims that point there."""
        parts = path_parts(path)
        for root, _is_global in roots():
            rest = under(parts, root)
            if not rest or len(rest) < 2:
                continue
            if rest[0] == "apps" and valid(rest[1]) and rest[1] != "scoop":
                return Ownership(self.name, rest[1], "exact")
            if rest[0] == "shims" and len(rest) == 2:
                app = shim_app(root / "shims", rest[1])
                if app:
                    return Ownership(self.name, app, "exact")
        return None


def global_note(verb: str, app: str) -> str:
    """Note for a global install, which aiup leaves alone."""
    return "installed globally; run scoop {} {} --global from an elevated terminal".format(verb, app)


def shim_app(shims: Path, file_name: str) -> str:
    """The app a shim starts, from ``<name>.shim``'s path line or the shim script's text."""
    stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    candidates = [shims / (stem + ".shim"), shims / (stem + ".cmd"), shims / (stem + ".ps1")]
    if not file_name.lower().endswith(".exe"):
        candidates.insert(1, shims / file_name)
    for candidate in candidates:
        text = read_text_file(candidate, 64 * 1024)
        if not text:
            continue
        found = _SHIM_PATH.search(text) if candidate.suffix.lower() == ".shim" else None
        target = found.group(1) if found else text
        app = _APPS_IN_TEXT.search(target)
        if app and app.group(1).lower() != "scoop":
            return app.group(1).lower()
    return ""
