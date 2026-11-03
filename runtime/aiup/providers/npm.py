"""npm global packages (channel ``npm``, design doc sections 6.3 and 6.4).

Ports of the macOS npm helpers:

- ``npm_install_aiup_latest``: new installs go into aiup's own prefix
  (``npm install -g --prefix <aiup prefix> pkg@latest``), so no sudo is
  needed even when the system npm prefix belongs to root.
- ``npm_provenance_gate``: before an update to a release that lost the
  provenance record its installed version had, ask. Without a terminal the
  tool stays where it is and the note says why.
- ``npm_allowed_install_scripts``: with npm 11.19 or newer, the few packages
  that need their install scripts get ``--allow-scripts=<list>``.

Several Node installs can sit side by side (nvm, fnm, volta, mise, asdf,
nvm-windows, the system Node, aiup's prefix). An update goes to the copy that
owns the tool's command on PATH, through that install's own npm. A copy in a
root-owned folder is never updated with sudo: the note points at
``aiup channel TOOL npm``.

Each update reads the new release's ``engines.node`` and refuses with a clear
message when the Node that would run it is too old.
"""

from __future__ import annotations

import functools
import os
import re
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, NamedTuple, Optional, Sequence, Set, Tuple

from aiup import paths
from aiup.engine.cache import read_json, read_text_bounded
from aiup.engine.net import clean_version
from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers.script import (
    ALL_OSES, aiup_config, batch_args_safe, empty_action, env_dir as _env_dir, env_of, home, is_windows, os_name,
    path_inside, path_setup_step, read_command, real_path, tool_id, version_token, which,
)
from aiup.versions import version_cmp, version_is_greater

if TYPE_CHECKING:
    from aiup.engine.context import Context

# macOS npm_allowed_install_scripts.
ALLOWED_INSTALL_SCRIPTS: Dict[str, Tuple[str, ...]] = {
    "wrangler": ("esbuild", "workerd"),
    "pnpm": ("pnpm",),
    "@remotion/cli": ("esbuild",),
    "@earendil-works/pi-coding-agent": ("esbuild",),
    "@mariozechner/pi-coding-agent": ("esbuild",),
}

# Packages every Node ships with; they belong to the Node install, not to aiup.
_BUNDLED = frozenset({"npm", "corepack"})
_SAFE_VERSION = re.compile(r"^[0-9A-Za-z.+_-]+$")
_SHIM_TARGET = re.compile(r"node_modules[\\/]((?:@[^\\/\"']+[\\/])?[^\\/\"']+)[\\/]")
_PACKAGE_JSON_MAX = 1024 * 1024
_SHIM_MAX = 64 * 1024


class NodeInstall(NamedTuple):
    """One place npm global packages live."""

    manager: str        # aiup | system | nvm | fnm | mise | asdf | volta | nvm-windows | other
    prefix: Path
    node_modules: Path
    bin_dir: Path
    writable: bool


# ----- layouts and discovery -------------------------------------------------------


def _layout(ctx: "Context", manager: str, prefix: Path) -> NodeInstall:
    if is_windows(ctx):
        modules, bins = prefix / "node_modules", prefix
    else:
        modules, bins = prefix / "lib" / "node_modules", prefix / "bin"
    probe = modules if modules.exists() else prefix
    return NodeInstall(manager, prefix, modules, bins, os.access(str(probe), os.W_OK))


def aiup_install(ctx: "Context") -> NodeInstall:
    """aiup's own prefix (section 6.4)."""
    return _layout(ctx, "aiup", paths.npm_prefix(os_name(ctx), env_of(ctx)))


def _data_home(ctx: "Context") -> Path:
    return _env_dir(ctx, "XDG_DATA_HOME", home(ctx) / ".local" / "share")


def _manager_roots(ctx: "Context") -> List[Tuple[str, Path]]:
    """Version-manager folders and the glob under them that holds one prefix per Node."""
    h = home(ctx)
    roots: List[Tuple[str, Path]] = [
        ("nvm", _env_dir(ctx, "NVM_DIR", h / ".nvm") / "versions" / "node"),
        ("mise", _env_dir(ctx, "MISE_DATA_DIR", _data_home(ctx) / "mise") / "installs" / "node"),
        ("asdf", _env_dir(ctx, "ASDF_DATA_DIR", h / ".asdf") / "installs" / "nodejs"),
    ]
    if is_windows(ctx):
        roots.append(("fnm", _env_dir(ctx, "FNM_DIR", paths.roaming_appdata(env_of(ctx)) / "fnm") / "node-versions"))
        nvm_home = env_of(ctx).get("NVM_HOME", "")
        if nvm_home and os.path.isabs(nvm_home):
            roots.append(("nvm-windows", Path(nvm_home)))
    else:
        roots.append(("fnm", _env_dir(ctx, "FNM_DIR", _data_home(ctx) / "fnm") / "node-versions"))
    return roots


def _manager_prefixes(manager: str, root: Path) -> List[Path]:
    if not root.is_dir():
        return []
    found: List[Path] = []
    for entry in sorted(root.iterdir()):
        if entry.is_symlink() or not entry.is_dir():
            continue  # "latest", "22" and similar aliases point at a real folder
        if manager == "fnm":
            entry = entry / "installation"
        elif manager == "nvm-windows" and not entry.name.startswith("v"):
            continue
        if entry.is_dir():
            found.append(entry)
    return found


def _manager_of(ctx: "Context", path: str) -> str:
    resolved = real_path(path)
    for manager, root in _manager_roots(ctx):
        if path_inside(resolved, real_path(str(root))):
            return manager
    if path_inside(resolved, real_path(str(_volta_home(ctx)))):
        return "volta"
    return "other" if path_inside(resolved, str(home(ctx))) else "system"


def node_installs(ctx: "Context") -> List[NodeInstall]:
    """Every npm global folder found, aiup's first, without duplicates."""
    installs = [aiup_install(ctx)]
    path_prefix = _path_npm_prefix(ctx)
    if path_prefix is not None:
        installs.append(_layout(ctx, _manager_of(ctx, str(path_prefix)), path_prefix))
    for manager, root in _manager_roots(ctx):
        installs.extend(_layout(ctx, manager, prefix) for prefix in _manager_prefixes(manager, root))
    seen: set = set()
    unique: List[NodeInstall] = []
    for install in installs:
        key = os.path.normcase(real_path(str(install.prefix)))
        if key not in seen:
            seen.add(key)
            unique.append(install)
    return unique


_PREFIX_TTL = 60.0
_PREFIX_CACHE: Dict[str, Tuple[float, Optional[Path]]] = {}
_PREFIX_LOCK = threading.Lock()


def _path_npm_prefix(ctx: "Context") -> Optional[Path]:
    """``npm prefix -g`` of the npm on PATH, remembered for a minute."""
    npm = which(ctx, "npm")
    if not npm:
        return None
    with _PREFIX_LOCK:
        cached = _PREFIX_CACHE.get(npm)
        if cached and time.monotonic() - cached[0] < _PREFIX_TTL:
            return cached[1]
    out = read_command(ctx, (npm, "prefix", "-g"), max_bytes=64 * 1024) or ""
    lines = out.strip().splitlines()
    value = lines[-1].strip() if lines else ""
    prefix = Path(value) if value and os.path.isabs(value) else None
    with _PREFIX_LOCK:
        _PREFIX_CACHE[npm] = (time.monotonic(), prefix)
    return prefix


# ----- package reads -------------------------------------------------------------


def _package_dir(install: NodeInstall, package: str) -> Path:
    return install.node_modules.joinpath(*package.split("/"))


def package_json(install: NodeInstall, package: str) -> Optional[Dict[str, object]]:
    """The installed ``package.json`` of one package, or None."""
    data = read_json(_package_dir(install, package) / "package.json", _PACKAGE_JSON_MAX)
    return data if isinstance(data, dict) else None


def bin_names(package: str, data: Optional[Dict[str, object]]) -> Tuple[str, ...]:
    """Command names a package installs (``bin`` in package.json)."""
    value = data.get("bin") if data else None
    if isinstance(value, dict):
        return tuple(str(name) for name in value)
    if isinstance(value, str):
        return (package.rsplit("/", 1)[-1],)
    return ()


def _volta_home(ctx: "Context") -> Path:
    return _env_dir(ctx, "VOLTA_HOME", home(ctx) / ".volta")


def _volta_copy(ctx: "Context", package: str) -> Optional[Path]:
    folder = _volta_home(ctx) / "tools" / "image" / "packages" / package
    return folder if folder.is_dir() else None


def _shim_dirs(ctx: "Context") -> Dict[str, Path]:
    return {
        "mise": _env_dir(ctx, "MISE_DATA_DIR", _data_home(ctx) / "mise") / "shims",
        "asdf": _env_dir(ctx, "ASDF_DATA_DIR", home(ctx) / ".asdf") / "shims",
        "volta": _volta_home(ctx) / "bin",
    }


def _prefix_version(install: NodeInstall) -> str:
    name = install.prefix.name if install.manager != "fnm" else install.prefix.parent.name
    return name.lstrip("v")


class Copy(NamedTuple):
    """The copy of a package aiup acts on."""

    install: NodeInstall
    version: str
    command: str        # resolved command path on PATH, or ""


def find_copy(ctx: "Context", package: str) -> Optional[Copy]:
    """The copy that owns the tool's command on PATH, else aiup's, else the first."""
    installs = node_installs(ctx)
    volta = _volta_copy(ctx, package)
    if volta is not None:
        installs.append(_layout(ctx, "volta", volta))
    copies = [(i, package_json(i, package)) for i in installs]
    copies = [(i, data) for i, data in copies if data is not None]
    if not copies:
        return None
    names = bin_names(package, copies[0][1])
    command = which(ctx, names[0]) if names else None
    chosen = _owner_of_command(ctx, command, copies) if command else None
    if chosen is None:
        chosen = next((c for c in copies if c[0].manager == "aiup"), copies[0])
    return Copy(chosen[0], clean_version(chosen[1].get("version")) if chosen[1] else "", command or "")


def _owner_of_command(ctx: "Context", command: str,
                      copies: Sequence[Tuple[NodeInstall, Optional[Dict[str, object]]]]
                      ) -> Optional[Tuple[NodeInstall, Optional[Dict[str, object]]]]:
    resolved = real_path(command)
    for copy in copies:
        install = copy[0]
        if path_inside(resolved, real_path(str(install.prefix))) or path_inside(command, str(install.bin_dir)):
            return copy
    for manager, shims in _shim_dirs(ctx).items():
        if path_inside(command, str(shims)):
            same = [c for c in copies if c[0].manager == manager]
            if same:
                # A shim runs the selected Node; without reading the manager's
                # config, the newest install that has the package is the guess.
                return sorted(same, key=functools.cmp_to_key(_by_node_version))[-1]
    return None


def _by_node_version(a: Tuple[NodeInstall, object], b: Tuple[NodeInstall, object]) -> int:
    return version_cmp(_prefix_version(a[0]), _prefix_version(b[0]))


# ----- npm and node commands --------------------------------------------------------


_PATH_MANAGERS = ("aiup", "system", "other")


def _install_tool(ctx: "Context", install: NodeInstall, name: str) -> Optional[str]:
    """``npm`` or ``node`` of one install; PATH's for aiup, system and other prefixes."""
    if install.manager in _PATH_MANAGERS:
        return which(ctx, name)
    if is_windows(ctx):
        for candidate in (install.bin_dir / (name + ".cmd"), install.bin_dir / (name + ".exe")):
            if candidate.is_file():
                return str(candidate)
        return None
    candidate = install.bin_dir / name
    return str(candidate) if candidate.is_file() else None


def _install_env(ctx: "Context", install: NodeInstall) -> Dict[str, str]:
    """PATH with the install's own bin folder first, so its node runs npm."""
    if install.manager in _PATH_MANAGERS:
        return {}
    return {"PATH": str(install.bin_dir) + os.pathsep + env_of(ctx).get("PATH", "")}


_NPM_VERSIONS: Dict[str, str] = {}
_NPM_LOCK = threading.Lock()


def _npm_version(ctx: "Context", npm: str, env: Dict[str, str]) -> str:
    with _NPM_LOCK:
        if npm in _NPM_VERSIONS:
            return _NPM_VERSIONS[npm]
    version = version_token(read_command(ctx, (npm, "--version"), env=env) or "")
    with _NPM_LOCK:
        _NPM_VERSIONS[npm] = version
    return version


def allow_scripts_args(ctx: "Context", package: str, npm: str, env: Dict[str, str]) -> Tuple[str, ...]:
    """``--allow-scripts=<list>`` for packages that need it, on npm 11.19 or newer."""
    allowed = ALLOWED_INSTALL_SCRIPTS.get(package)
    if not allowed:
        return ()
    parts = [int(p) for p in re.findall(r"\d+", _npm_version(ctx, npm, env))[:2]] + [0, 0]
    major, minor = parts[0], parts[1]
    if major > 11 or (major == 11 and minor >= 19):
        return ("--allow-scripts=" + ",".join(allowed),)
    return ()


def _node_version(ctx: "Context", install: NodeInstall) -> str:
    node = _install_tool(ctx, install, "node")
    if not node:
        return ""
    return version_token(read_command(ctx, (node, "--version"), env=_install_env(ctx, install)) or "")


# ----- engines.node ---------------------------------------------------------------

_COMPARATOR = re.compile(r"^(>=|<=|>|<|=|\^|~)?v?(\d+|[xX*])(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?(?:[-+][0-9A-Za-z.-]+)?$")
_Version = Tuple[int, int, int]


def _parts(match: "re.Match[str]") -> List[int]:
    out: List[int] = []
    for group in match.groups()[1:]:
        if group is None or group in ("x", "X", "*"):
            break
        out.append(int(group))
    return out


def _upper(given: List[int]) -> _Version:
    """The first version above a partial version: 18 -> 19.0.0, 18.2 -> 18.3.0."""
    bumped = list(given)
    bumped[-1] += 1
    return _fill(bumped)


def _fill(given: List[int]) -> _Version:
    padded = list(given) + [0, 0, 0]
    return (padded[0], padded[1], padded[2])


def _bounds(op: str, given: List[int]) -> Optional[List[Tuple[str, _Version]]]:
    """A comparator as a list of (operator, version) bounds."""
    if not given:
        return [] if op in ("", "=", ">=", "<=", "^", "~") else None
    full = len(given) == 3
    if op in ("", "="):
        return [("=", _fill(given))] if full else [(">=", _fill(given)), ("<", _upper(given))]
    if op == ">=":
        return [(">=", _fill(given))]
    if op == ">":
        return [(">", _fill(given))] if full else [(">=", _upper(given))]
    if op == "<":
        return [("<", _fill(given))]
    if op == "<=":
        return [("<=", _fill(given))] if full else [("<", _upper(given))]
    if op == "~":
        return [(">=", _fill(given)), ("<", _upper(given[:2] if len(given) > 1 else given))]
    # ^: the first non-zero part given may not change.
    head = next((i for i, part in enumerate(given) if part != 0), len(given) - 1)
    return [(">=", _fill(given)), ("<", _upper(given[:head + 1]))]


def _check(version: _Version, bounds: Iterable[Tuple[str, _Version]]) -> bool:
    tests = {"=": version.__eq__, ">=": version.__ge__, ">": version.__gt__,
             "<": version.__lt__, "<=": version.__le__}
    return all(tests[op](limit) for op, limit in bounds)


def _range_bounds(text: str) -> Optional[List[Tuple[str, _Version]]]:
    text = re.sub(r"(>=|<=|>|<|=|\^|~)\s+", r"\1", text.strip())
    if " - " in text:
        low, _, high = text.partition(" - ")
        lo, hi = _COMPARATOR.match(low.strip()), _COMPARATOR.match(high.strip())
        if not lo or not hi or lo.group(1) or hi.group(1):
            return None
        hi_parts = _parts(hi)
        upper = [("<=", _fill(hi_parts))] if len(hi_parts) == 3 else ([("<", _upper(hi_parts))] if hi_parts else [])
        return [(">=", _fill(_parts(lo)))] + upper
    bounds: List[Tuple[str, _Version]] = []
    for word in text.split():
        match = _COMPARATOR.match(word)
        if not match:
            return None
        found = _bounds(match.group(1) or "", _parts(match))
        if found is None:
            return None
        bounds.extend(found)
    return bounds


def node_satisfies(node_version: str, spec: str) -> Optional[bool]:
    """Whether a Node version meets an ``engines.node`` range; None when unreadable."""
    numbers = [int(p) for p in re.findall(r"\d+", node_version)[:3]]
    if not numbers or not spec.strip():
        return None
    version = _fill(numbers)
    any_read = False
    for alternative in spec.split("||"):
        if not alternative.strip() or alternative.strip() == "*":
            return True
        bounds = _range_bounds(alternative)
        if bounds is None:
            continue
        any_read = True
        if _check(version, bounds):
            return True
    return False if any_read else None


def engines_refusal(ctx: "Context", package: str, version: str, install: NodeInstall,
                    timeout: float) -> str:
    """A note when ``package@version`` needs a newer Node than ``install`` runs; else ""."""
    if not version:
        return ""
    meta = ctx.net.npm_metadata(package, version, timeout)
    engines = meta.get("engines") if isinstance(meta, dict) else None
    spec = engines.get("node") if isinstance(engines, dict) else None
    if not isinstance(spec, str):
        return ""
    node = _node_version(ctx, install)
    if node and node_satisfies(node, spec) is False:
        return (package + " " + version + " needs Node " + spec.strip() + ", and the Node it would run on is "
                + node + ". Update Node first, then run aiup again.")
    return ""


# ----- provenance gate --------------------------------------------------------------


class Gate(NamedTuple):
    """The provenance gate's answer."""

    proceed: bool
    note: str
    result: str = ""


def _provenance(meta: Optional[Dict[str, object]]) -> Tuple[bool, str]:
    dist = meta.get("dist") if meta else None
    attestations = dist.get("attestations") if isinstance(dist, dict) else None
    has = bool(attestations.get("provenance")) if isinstance(attestations, dict) else False
    user = meta.get("_npmUser") if meta else None
    name = user.get("name") if isinstance(user, dict) else ""
    return has, name if isinstance(name, str) else ""


def provenance_gate(ctx: "Context", package: str, installed: str, latest: str, timeout: float,
                    tool: str = "") -> Gate:
    """macOS ``npm_provenance_gate``: ask before a release that lost its provenance record.

    ``tool`` is the catalog id the note tells you to run ``aiup only`` with.
    """
    if not aiup_config(ctx).npm_provenance_check:
        return Gate(True, "")
    if not (installed and latest and _SAFE_VERSION.match(installed) and _SAFE_VERSION.match(latest)):
        return Gate(True, "")
    old_has, old_user = _provenance(ctx.net.npm_metadata(package, installed, timeout))
    if not old_has:
        return Gate(True, "")
    meta = ctx.net.npm_metadata(package, latest, timeout)
    if meta is None:
        return Gate(True, "")
    new_has, new_user = _provenance(meta)
    if new_has:
        return Gate(True, "")
    warning = package + " " + latest + " has no provenance record; the installed " + installed + " has one"
    if getattr(ctx, "dry_run", False):
        return Gate(True, warning + ". A real run asks first.")
    if getattr(ctx, "interactive", False):
        answer = _ask(_prompt(package, installed, latest, old_user, new_user))
        if answer is True:
            return Gate(True, "Installed after you confirmed: " + latest + " has no provenance record.")
        if answer is False:
            return Gate(False, "Kept " + installed + ": " + latest + " has no provenance record. aiup resume asks again.",
                        "deferred")
    return Gate(False, "Kept " + installed + ": " + latest + " has no provenance record and needs your OK. "
                "Run aiup only " + (tool or package) + " in a terminal.", "deferred")


def _prompt(package: str, installed: str, latest: str, old_user: str, new_user: str) -> str:
    if new_user and new_user == old_user:
        publisher = "    Published by: " + new_user + " (same account as before)\n"
    elif new_user:
        publisher = "    Published by: " + new_user + " (the installed version came from " + (old_user or "an unknown account") + ")\n"
    else:
        publisher = ""
    return (
        "! " + package + " " + latest + " is missing its provenance record\n"
        "    What it is: npm releases can carry a signed record from the service\n"
        "    that built them, showing which source code and build made the release.\n"
        "    Your installed " + installed + " has one. The new " + latest + " does not.\n"
        "    Why it matters: this often just means a maintainer published from their\n"
        "    own computer this time. It can also mean someone else published it, for\n"
        "    example with a stolen npm login.\n"
        + publisher +
        "    Release page: https://www.npmjs.com/package/" + package + "/v/" + latest + "\n"
        "    If you are not sure, answer N. You keep " + installed + " and aiup asks again next time.\n"
        "  Install " + package + " " + latest + " anyway? [y/N] "
    )


_ASK_LOCK = threading.Lock()


def _ask(prompt: str) -> Optional[bool]:
    """Ask on the terminal itself; None when there is no terminal to ask on.

    Planning runs providers on worker threads, so one question at a time.
    """
    with _ASK_LOCK:
        return _ask_locked(prompt)


def _ask_locked(prompt: str) -> Optional[bool]:
    try:
        if os.name == "nt":
            with open("CONOUT$", "w", encoding="utf-8") as out, open("CONIN$", "r", encoding="utf-8") as inp:
                out.write(prompt)
                out.flush()
                reply = inp.readline(64)
        else:
            with open("/dev/tty", "r+", encoding="utf-8") as tty:
                tty.write(prompt)
                tty.flush()
                reply = tty.readline(64)
    except OSError:
        return None
    return reply.strip().lower() in ("y", "yes")


# ----- provider ----------------------------------------------------------------------


class NpmProvider(Provider):
    """npm global packages, installed into aiup's own prefix."""

    name = "npm"
    oses = ALL_OSES
    scope = "user"
    lane = "npm"
    exclusive = False
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        return which(ctx, "npm") is not None

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        copy = find_copy(ctx, target.package)
        if copy is None:
            return None
        path = copy.command or str(_package_dir(copy.install, target.package))
        scope = "user" if copy.install.writable else "system"
        return Installed(copy.version, path, scope, self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        version = ctx.net.npm_latest(target.package, timeout)
        return Latest(version, "registry") if version else Latest("", "registry", "the npm registry did not answer")

    def install(self, ctx: "Context", target: Target) -> Action:
        """``npm install -g --prefix <aiup prefix> pkg@latest``, then PATH setup."""
        return self._install_into(ctx, target, aiup_install(ctx), "install", "")

    def update(self, ctx: "Context", target: Target) -> Action:
        """Update the copy that owns the command, after the engines and provenance checks."""
        copy = find_copy(ctx, target.package)
        if copy is None:
            return self.install(ctx, target)
        install = copy.install
        if install.manager == "volta":
            return self._volta(ctx, target, "update")
        if not install.writable:
            return empty_action(target, "update", target.package + " is in a root-owned npm folder (" + str(install.prefix)
                                + "). aiup never runs sudo npm. Run aiup channel " + tool_id(ctx, target)
                                + " npm to move it into aiup's own folder.")
        timeout = float(aiup_config(ctx).available_version_provider_timeout or 10)
        latest = ctx.net.npm_latest(target.package, timeout)
        gate = Gate(True, "")
        if latest and copy.version and version_is_greater(latest, copy.version):
            gate = provenance_gate(ctx, target.package, copy.version, latest, timeout, tool_id(ctx, target))
        if not gate.proceed:
            return empty_action(target, "update", gate.note, gate.result)
        return self._install_into(ctx, target, install, "update", gate.note, latest)

    def remove(self, ctx: "Context", target: Target) -> Action:
        copy = find_copy(ctx, target.package)
        if copy is None:
            return empty_action(target, "remove", "Nothing to remove: " + target.package + " is not installed with npm.")
        install = copy.install
        if install.manager == "volta":
            return self._volta(ctx, target, "remove")
        if not install.writable:
            return empty_action(target, "remove", target.package + " is in a root-owned npm folder (" + str(install.prefix)
                                + "). aiup never runs sudo npm.")
        npm = _install_tool(ctx, install, "npm")
        argv = ("uninstall", "-g", "--prefix", str(install.prefix), target.package)
        if not npm or not batch_args_safe(npm, argv):
            return empty_action(target, "remove", "No usable npm for " + str(install.prefix) + ".")
        step = Step(argv=(npm,) + argv, label="npm uninstall -g " + target.package, env=_install_env(ctx, install))
        return Action(tool=target.package, op="remove", channel=self.name, steps=(step,))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        resolved = real_path(path)
        for install in node_installs(ctx):
            package = _package_under(resolved, install.node_modules)
            if not package and is_windows(ctx) and path_inside(path, str(install.bin_dir)):
                package = _package_from_shim(path)
            if not package or (package in _BUNDLED and install.manager != "aiup"):
                continue
            folder = str(_package_dir(install, package))
            if _distro_owned(ctx, install, (folder,)):
                return None  # pacman, apt, dnf or zypper installed it, not npm
            return Ownership(self.name, package, "exact")
        return None

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        records: List[PackageRecord] = []
        for install in node_installs(ctx):
            scope = "user" if install.writable else "system"
            packages = [p for p in _list_packages(install.node_modules)
                        if not (p in _BUNDLED and install.manager != "aiup")]
            distro = _distro_owned(ctx, install, [str(_package_dir(install, p)) for p in packages])
            for package in packages:
                if str(_package_dir(install, package)) in distro:
                    continue  # listed by the system package manager that installed it
                data = package_json(install, package)
                version = clean_version(data.get("version")) if data else ""
                records.append(PackageRecord(self.name, package, version, scope, True,
                                             (str(_package_dir(install, package)),)))
        return tuple(records)

    def _install_into(self, ctx: "Context", target: Target, install: NodeInstall, op: str,
                      note: str, latest: str = "") -> Action:
        npm = _install_tool(ctx, install, "npm")
        if not npm:
            return empty_action(target, op, "npm was not found for " + str(install.prefix) + ".")
        timeout = float(aiup_config(ctx).available_version_provider_timeout or 10)
        if not latest:
            latest = ctx.net.npm_latest(target.package, timeout)
        refusal = engines_refusal(ctx, target.package, latest, install, timeout)
        if refusal:
            return empty_action(target, op, refusal)
        env = _install_env(ctx, install)
        argv = ("install", "-g", "--prefix", str(install.prefix)) \
            + allow_scripts_args(ctx, target.package, npm, env) + (target.package + "@latest",)
        if not batch_args_safe(npm, argv):
            return empty_action(target, op, "Refusing to pass " + str(install.prefix) + " to npm.cmd: the path has characters cmd.exe would read.")
        steps: List[Step] = [Step(argv=(npm,) + argv, label="npm install -g " + target.package + "@latest", env=env)]
        if install.manager == "aiup":
            setup = path_setup_step(ctx, str(install.bin_dir))
            if setup is not None:
                steps.append(setup)
        return Action(tool=target.package, op=op, channel=self.name, steps=tuple(steps), note=note)

    def _volta(self, ctx: "Context", target: Target, op: str) -> Action:
        volta = which(ctx, "volta")
        if not volta:
            return empty_action(target, op, target.package + " belongs to volta, and volta is not on PATH.")
        verb = ("uninstall", target.package) if op == "remove" else ("install", target.package + "@latest")
        step = Step(argv=(volta,) + verb, label="volta " + " ".join(verb))
        return Action(tool=target.package, op=op, channel=self.name, steps=(step,))


def _distro_owned(ctx: "Context", install: NodeInstall, folders: Sequence[str]) -> Set[str]:
    """The package folders of a root-owned Linux install that a system package manager owns.

    Some distro packages (Arch's typescript, for one) install into the system
    npm folder; those copies belong to pacman, apt, dnf or zypper.
    """
    if install.writable or install.manager != "system" or os_name(ctx) != "linux" or not folders:
        return set()
    # Imported here so loading the providers does not load the detection package.
    from aiup.detect.owners import system_owners

    try:
        found = system_owners(ctx, list(folders))
    except (OSError, ValueError):
        return set()
    return {folder for folder, owner in found.items() if getattr(owner, "package", "")}


def _package_under(path: str, node_modules: Path) -> str:
    root = real_path(str(node_modules))
    if not path_inside(path, root) or os.path.normcase(path) == os.path.normcase(root):
        return ""
    parts = Path(os.path.relpath(path, root)).parts
    if parts[0].startswith("@") and len(parts) > 1:
        return parts[0] + "/" + parts[1]
    return parts[0] if not parts[0].startswith(".") else ""


def _package_from_shim(path: str) -> str:
    """Package a Windows npm shim (``x``, ``x.cmd``, ``x.ps1``) points at."""
    if os.path.splitext(path)[1].lower() not in ("", ".cmd", ".ps1") or not os.path.isfile(path):
        return ""
    text = read_text_bounded(Path(path), _SHIM_MAX)
    found = _SHIM_TARGET.search(text or "")
    return found.group(1).replace("\\", "/") if found else ""


def _list_packages(node_modules: Path) -> List[str]:
    if not node_modules.is_dir():
        return []
    names: List[str] = []
    for entry in sorted(node_modules.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.name.startswith("@") and entry.is_dir():
            names.extend(entry.name + "/" + sub.name for sub in sorted(entry.iterdir()) if not sub.name.startswith("."))
        elif entry.is_dir():
            names.append(entry.name)
    return names
