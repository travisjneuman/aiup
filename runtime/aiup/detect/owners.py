"""Who owns a file, and what aiup can do about an item (design 8.2, research 10).

Evidence order, cheapest first, stopping at the first exact answer:

1. layout rules read in-process: package.json ancestry (npm, pnpm, bun, Volta,
   mise npm backend), pipx venvs, Go build info in the Go bin folder, vendor
   version folders (Claude Code, Cursor agent, Grok, opencode, Deno, Bun),
   version managers (mise, asdf, Volta, proto, fnm, nvm, n), rustup proxies,
   .NET tool shims, the Nix store, and script shims read from their first 64 KiB;
2. providers whose ``owns()`` is a path check: uv, cargo, Homebrew, Flatpak,
   Snap, Nix, Scoop, Chocolatey, winget portable packages and Appx;
3. one batched system package query for paths outside the home folder
   (``pacman -Qo``, ``dpkg-query -S``; ``rpm -qf`` in batches);
4. Windows: the longest Uninstall ``InstallLocation`` that holds the file
   ("strong", never "exact").
"""

from __future__ import annotations

import importlib
import os
import re
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

from aiup.detect import files
from aiup.detect.items import ACTIONABLE, InventoryItem, Owner, fact
from aiup.errors import AiupError
from aiup.model import Action, Ownership, Step, Target

if TYPE_CHECKING:
    from aiup.catalog import Catalog
    from aiup.engine.context import Context
    from aiup.model import CatalogEntry

_ERRORS = (OSError, ValueError, NotImplementedError, AiupError)

# Channels whose provider can update and remove what it owns. vendor and
# script own nothing by path; their tools are reached through the catalog.
NO_PATH_ACTIONS = frozenset(("vendor", "script"))
SYSTEM_MANAGERS = ("pacman", "aur", "apt", "dnf", "zypper")

DEFAULT_DESCRIPTION = "Command available in your terminal"
DEFAULT_GUIDANCE = "Its owner has not been identified; inspect its location before changing it."


@dataclass(frozen=True)
class Found:
    """What a layout rule learned about one file."""

    owner: Owner
    version: str = ""
    self_updates: bool = False
    guidance: str = ""
    companion: bool = False      # npx with npm, rustc with rustup: never a duplicate


def _owner(manager: str, package: str, exact: bool, evidence: str, label: str = "") -> Owner:
    return Owner(manager=manager, package=package, confidence="exact" if exact else "prefix",
                 label=label, evidence=evidence)


# ----- layout rules ------------------------------------------------------------------------

_NAME_PART = re.compile(r"^[A-Za-z0-9@._+-]+$")


def _bin_targets(package_json: Mapping[str, object], name: str) -> List[str]:
    raw = package_json.get("bin")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, dict):
        return [v for v in raw.values() if isinstance(v, str)]
    return []


def node_package_owner(ctx: "Context", resolved: str) -> Optional[Found]:
    """package.json ancestry: a file inside ``.../node_modules/<pkg>/`` (macOS path_insights)."""
    parts = Path(resolved).parts
    index = -1
    for i in range(len(parts) - 2, -1, -1):
        if parts[i] == "node_modules":
            index = i
            break
    if index < 0:
        return None
    name = parts[index + 1]
    depth = index + 2
    if name.startswith("@") and len(parts) > index + 2:
        name = name + "/" + parts[index + 2]
        depth = index + 3
    if not all(_NAME_PART.match(p) for p in name.split("/")):
        return None
    package_dir = Path(*parts[:depth])
    data = files.read_json(package_dir / "package.json")
    if not isinstance(data, dict):
        return None
    declared = data.get("name")
    version = data.get("version")
    if declared != name:
        return None
    exact = any(files.norm(files.real(str(package_dir / t))) == files.norm(resolved)
                for t in _bin_targets(data, name))
    root = str(Path(*parts[:index]))
    lowered = root.replace("\\", "/").lower()
    if "/.bun/install/global" in lowered:
        manager, label = "bun", ""
    elif "/pnpm/" in lowered + "/" and "/global/" in lowered + "/":
        manager, label = "pnpm", ""
    elif "/.volta/tools/image/packages/" in lowered:
        manager, label = "volta", "Volta"
    elif "/mise/installs/" in lowered:
        manager, label = "mise", "mise"
        name = "npm:" + name
    else:
        manager, label = "npm", ""
        if ctx.os_name == "linux" and not files.inside(root, str(files.home(ctx))):
            # With npm's prefix at /usr, pacman (or another system manager)
            # often owns /usr/lib/node_modules/<pkg>. A weak answer lets the
            # one batched system query in ``attribute`` claim it first.
            exact = False
    return Found(_owner(manager, name, exact, "package.json ancestry", label),
                 version=version if isinstance(version, str) else "")


def _pipx_home(ctx: "Context") -> Tuple[Path, ...]:
    custom = files.env_dir(ctx, "PIPX_HOME")
    if custom is not None:
        return (custom,)
    data = files.xdg_data_home(ctx)
    return (data / "pipx", files.home(ctx) / ".local" / "pipx", files.home(ctx) / "pipx")


def pipx_owner(ctx: "Context", resolved: str) -> Optional[Found]:
    for root in _pipx_home(ctx):
        rest = files.relative_parts(resolved, str(root / "venvs"))
        if not rest:
            continue
        meta = files.read_json(root / "venvs" / rest[0] / "pipx_metadata.json")
        main = meta.get("main_package") if isinstance(meta, dict) else None
        version = main.get("package_version") if isinstance(main, dict) else ""
        package = main.get("package") if isinstance(main, dict) else ""
        return Found(_owner("pipx", package if isinstance(package, str) and package else rest[0],
                            isinstance(meta, dict), "pipx venv"),
                     version=version if isinstance(version, str) else "")
    return None


def go_bin_dirs(ctx: "Context") -> Tuple[Path, ...]:
    out: List[Path] = []
    gobin = files.env_dir(ctx, "GOBIN")
    if gobin is not None:
        out.append(gobin)
    gopath = files.env_get(ctx, "GOPATH")
    for entry in gopath.split(os.pathsep) if gopath else ():
        if entry and os.path.isabs(entry):
            out.append(Path(entry) / "bin")
    if not gopath:
        out.append(files.home(ctx) / "go" / "bin")
    return tuple(out)


def go_owner(ctx: "Context", path: str, resolved: str) -> Optional[Found]:
    folder = os.path.dirname(path)
    if not any(files.norm(folder) == files.norm(str(d)) for d in go_bin_dirs(ctx)):
        return None
    info = files.go_buildinfo(resolved)
    if info is None:
        return Found(_owner("go", os.path.basename(path), False, "Go bin folder"))
    main_path, _module, version = info
    return Found(_owner("go", main_path, True, "Go build info"),
                 version="" if version == "(devel)" else version)


# Vendor installers that keep versioned copies: (key, label, folder under home, update hint).
_VENDOR_VERSION_DIRS = (
    ("claude", "Claude Code installer", (".local", "share", "claude", "versions"), "claude update"),
    ("cursor-agent", "Cursor agent installer", (".local", "share", "cursor-agent", "versions"), "cursor-agent update"),
)
# Vendor installers with their own folder: (key, label, folder under home, update hint).
_VENDOR_HOMES = (
    ("grok", "Grok CLI installer", (".grok",), ""),
    ("opencode", "opencode installer", (".opencode",), "opencode upgrade"),
    ("deno", "Deno installer", (".deno",), "deno upgrade"),
    ("bun", "Bun installer", (".bun",), "bun upgrade"),
)
_SELF_NAMES = {"deno": ("deno",), "bun": ("bun", "bunx")}


def _grok_version(ctx: "Context") -> str:
    """Newest ``grok-<ver>-<platform>`` download name (research section 9)."""
    best = ("", 0)
    for entry in files.scandir(files.home(ctx) / ".grok" / "downloads"):
        match = re.match(r"^grok-v?(\d[\w.+-]*?)-(?:linux|darwin|windows|win)", entry.name)
        if not match:
            continue
        try:
            mtime = entry.stat().st_mtime_ns
        except OSError:
            continue
        if mtime > best[1]:
            best = (match.group(1), mtime)
    return best[0]


def vendor_owner(ctx: "Context", path: str, resolved: str) -> Optional[Found]:
    home = files.home(ctx)
    for key, label, rel, hint in _VENDOR_VERSION_DIRS:
        rest = files.relative_parts(resolved, str(home.joinpath(*rel)))
        if rest and rest[0][:1].isdigit():
            return Found(_owner("vendor", key, True, "version folder", label), version=rest[0],
                         self_updates=True, guidance=("Update it with: " + hint) if hint else "")
    for key, label, rel, hint in _VENDOR_HOMES:
        root = str(home.joinpath(*rel))
        if not files.inside(resolved, root):
            continue
        base = os.path.basename(resolved).lower()
        if base.endswith(".exe"):
            base = base[:-4]
        selves = _SELF_NAMES.get(key, (key,))
        if base not in selves:
            continue     # other files there (deno shims, bun globals) have their own rules
        version = _grok_version(ctx) if key == "grok" else ""
        return Found(_owner("vendor", key, True, "installer folder", label), version=version,
                     self_updates=True, guidance=("Update it with: " + hint) if hint else "")
    if files.is_windows(ctx):
        # The native Claude Code launcher on Windows is a real file, not a link.
        launcher = home / ".local" / "bin" / "claude.exe"
        if files.norm(path) == files.norm(str(launcher)):
            return Found(_owner("vendor", "claude", True, "launcher location", "Claude Code installer"),
                         version=files.pe_version(path), self_updates=True,
                         guidance="Update it with: claude update")
    return None


def manager_dirs(ctx: "Context") -> Tuple[Tuple[str, str, Path, int], ...]:
    """(manager, label, installs folder, depth of the tool name) for version managers."""
    home = files.home(ctx)
    data = files.xdg_data_home(ctx)
    # mise keeps its data in %LOCALAPPDATA%\mise on Windows.
    mise = files.env_dir(ctx, "MISE_DATA_DIR") or (
        files.local_appdata(ctx) / "mise" if files.is_windows(ctx) else data / "mise")
    asdf = files.env_dir(ctx, "ASDF_DATA_DIR") or home / ".asdf"
    volta = files.env_dir(ctx, "VOLTA_HOME") or home / ".volta"
    proto = files.env_dir(ctx, "PROTO_HOME") or home / ".proto"
    fnm = files.env_dir(ctx, "FNM_DIR") or data / "fnm"
    nvm = files.env_dir(ctx, "NVM_DIR") or home / ".nvm"
    return (
        ("mise", "mise", mise / "installs", 0),
        ("asdf", "asdf", asdf / "installs", 0),
        ("volta", "Volta", volta / "tools" / "image", 0),
        ("proto", "proto", proto / "tools", 0),
        ("fnm", "fnm", fnm / "node-versions", -1),
        ("nvm", "nvm", nvm / "versions" / "node", -1),
        ("n", "n", Path("/usr/local/n/versions/node"), -1),
    )


def version_manager_owner(ctx: "Context", resolved: str) -> Optional[Found]:
    for manager, label, root, depth in manager_dirs(ctx):
        rest = files.relative_parts(resolved, str(root))
        if len(rest) < 2 + (depth >= 0):
            continue
        if depth < 0:
            tool, version = "node", rest[0].lstrip("v")
        else:
            tool, version = rest[0], rest[1]
        hint = {"mise": "mise upgrade " + tool, "asdf": "asdf install " + tool + " latest",
                "volta": "volta install " + tool}.get(manager, "")
        return Found(_owner(manager, tool, True, "version manager folder", label), version=version,
                     guidance=("Update it with: " + hint) if hint else "")
    return None


_RUSTUP_PROXIES = frozenset((
    "rustc", "cargo", "rustup", "rustdoc", "rust-gdb", "rust-gdbgui", "rust-lldb", "rustfmt",
    "cargo-fmt", "cargo-clippy", "clippy-driver", "rls", "rust-analyzer", "cargo-miri",
))


def cargo_home(ctx: "Context") -> Path:
    return files.env_dir(ctx, "CARGO_HOME") or files.home(ctx) / ".cargo"


def rustup_owner(ctx: "Context", path: str) -> Optional[Found]:
    bin_dir = cargo_home(ctx) / "bin"
    if files.norm(os.path.dirname(path)) != files.norm(str(bin_dir)):
        return None
    base = os.path.basename(path).lower()
    if base.endswith(".exe"):
        base = base[:-4]
    if base not in _RUSTUP_PROXIES:
        return None
    rustup = bin_dir / ("rustup.exe" if files.is_windows(ctx) else "rustup")
    if not rustup.is_file():
        return None
    return Found(_owner("rustup", "rustup", True, "rustup proxy", "rustup"), self_updates=True,
                 guidance="Update it with: rustup update", companion=base != "rustup")


def dotnet_tool_owner(ctx: "Context", path: str) -> Optional[Found]:
    """A global .NET tool shim: the store package whose settings name the command."""
    tools = files.home(ctx) / ".dotnet" / "tools"
    if files.norm(os.path.dirname(path)) != files.norm(str(tools)):
        return None
    base = os.path.basename(path)
    if base.lower().endswith(".exe"):
        base = base[:-4]
    pattern = re.compile(r"<Command\s+Name=\"" + re.escape(base) + "\"", re.IGNORECASE)
    for package in files.scandir(tools / ".store"):
        if package.name.startswith("."):
            continue
        for version in files.scandir(package.path):
            for settings in Path(version.path).glob("*/*/tools/*/*/DotnetToolSettings.xml"):
                text = files.read_text(settings, files.HEADER_MAX)
                if text and pattern.search(text):
                    return Found(_owner("dotnet-tool", package.name, True, ".NET tool store", ".NET tool"),
                                 version=version.name,
                                 guidance="Update it with: dotnet tool update -g " + package.name)
    return None


_NIX_STORE = re.compile(r"^/nix/store/[0-9a-z]{32}-([^/]+)")


def nix_store_owner(resolved: str) -> Optional[Found]:
    match = _NIX_STORE.match(resolved.replace("\\", "/"))
    if not match:
        return None
    name, version = match.group(1), ""
    split = re.search(r"-(\d[^-]*)", name)
    if split:
        name, version = name[:split.start()], split.group(1)
    return Found(_owner("nix", name, False, "Nix store path", "Nix"), version=version)


# Script shims, read from the first 64 KiB.
_SHIM_RULES = (
    (re.compile(rb"\bmise\b[^\n]*\b(?:x|exec)\b"), "mise", "mise", "mise shim"),
    (re.compile(rb"\basdf\s+exec\b"), "asdf", "asdf", "asdf shim"),
    (re.compile(rb"distrobox-enter|#\s*distrobox_binary"), "distrobox", "distrobox", "distrobox export"),
)
_FLATPAK_RUN = re.compile(rb"\bflatpak\s+run\s+(?:--?[\w-]+(?:=\S+)?\s+)*([A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+)")
_DENO_RUN = re.compile(rb"\bdeno\b[^\n]*\brun\b[^\n]*?\b((?:jsr|npm):[@\w./-]+|https?://\S+)")
_DISTROBOX_NAME = re.compile(rb"(?:-n|--name)\s+[\"']?([\w.-]+)")
_NPM_SHIM = re.compile(rb"node_modules[\\/]+((?:@[^\\/\"'\s]+[\\/]+)?[^\\/\"'\s]+)[\\/]")


def script_owner(ctx: "Context", path: str, head: bytes) -> Optional[Found]:
    """Owners told by a script's own text: version manager shims, exports, deno and npm shims."""
    if not head:
        return None
    text = head
    for pattern, manager, label, evidence in _SHIM_RULES:
        if pattern.search(text):
            package = ""
            if manager == "distrobox":
                match = _DISTROBOX_NAME.search(text)
                package = match.group(1).decode("utf-8", "replace") if match else ""
            return Found(_owner(manager, package or os.path.basename(path), False, evidence, label))
    match = _FLATPAK_RUN.search(text)
    if match:
        return Found(_owner("flatpak", match.group(1).decode("utf-8", "replace"), False, "flatpak run script"))
    match = _DENO_RUN.search(text)
    if match:
        spec = match.group(1).decode("utf-8", "replace")
        name, version = _deno_spec(spec)
        return Found(_owner("deno", name, False, "deno install shim", "Deno"), version=version,
                     guidance="Reinstall it with deno install -g -f to update it.")
    match = _NPM_SHIM.search(text)
    if match and files.is_windows(ctx):
        package = match.group(1).decode("utf-8", "replace").replace("\\", "/").strip("/")
        package_dir = Path(os.path.dirname(path)) / "node_modules" / Path(*package.split("/"))
        data = files.read_json(package_dir / "package.json")
        if isinstance(data, dict) and data.get("name") == package:
            version = data.get("version")
            return Found(_owner("npm", package, True, "npm shim"),
                         version=version if isinstance(version, str) else "")
    return None


def _deno_spec(spec: str) -> Tuple[str, str]:
    if spec.startswith(("jsr:", "npm:")):
        body = spec.split(":", 1)[1]
        at = body.rfind("@")
        if at > 0:
            return body[:at], body[at + 1:].split("/", 1)[0]
        return body.split("/", 1)[0] if not body.startswith("@") else body, ""
    return spec, ""


def _is_script(head: bytes) -> bool:
    return head.startswith(b"#!") or head[:2] in (b"@e", b"@E", b"::") or b"\0" not in head[:512]


def layout_owner(ctx: "Context", path: str, resolved: str, head: Optional[bytes] = None) -> Optional[Found]:
    """Every in-process rule (step 1 of the evidence order)."""
    for rule in (
        lambda: node_package_owner(ctx, resolved),
        lambda: pipx_owner(ctx, resolved),
        lambda: vendor_owner(ctx, path, resolved),
        lambda: version_manager_owner(ctx, resolved),
        lambda: rustup_owner(ctx, path),
        lambda: go_owner(ctx, path, resolved),
        lambda: dotnet_tool_owner(ctx, path),
    ):
        found = rule()
        if found is not None:
            return found
    if head is None:
        head = files.read_head(resolved, 512)
    if head and _is_script(head):
        if len(head) == 512:
            head = files.read_head(resolved, files.HEADER_MAX)
        found = script_owner(ctx, path, head)
        if found is not None:
            return found
    return nix_store_owner(resolved)


# ----- providers -------------------------------------------------------------------------------

def _provider_hint(name: str, lowered: str, resolved: str) -> bool:
    """Only ask a provider whose folders the path could be in, so the rest cost nothing."""
    if name == "brew":
        return "/cellar/" in lowered or "linuxbrew" in lowered
    if name == "flatpak":
        return "flatpak" in lowered
    if name == "snap":
        return resolved.startswith(("/snap/", "/var/lib/snapd/snap/"))
    if name == "nix":
        return resolved.startswith("/nix/store/")
    if name == "scoop":
        return "scoop" in lowered
    if name == "choco":
        return "chocolatey" in lowered
    if name == "winget":
        return "winget" in lowered
    if name == "appx":
        return "windowsapps" in lowered
    if name == "cargo":
        return ".cargo" in lowered or "cargo" in lowered
    return name == "uv"


PATH_PROVIDERS = ("uv", "cargo", "brew", "flatpak", "snap", "nix", "scoop", "choco", "winget", "appx")


def provider_owner(ctx: "Context", path: str, resolved: str) -> Optional[Owner]:
    """Step 2: providers whose ``owns()`` only looks at the path."""
    lowered = (path + "\n" + resolved).replace("\\", "/").lower()
    for name in PATH_PROVIDERS:
        if not _provider_hint(name, lowered, resolved):
            continue
        provider = ctx.provider(name)
        if provider is None:
            continue
        try:
            found = provider.owns(ctx, path)
        except _ERRORS:
            found = None
        if found is not None and found.package:
            return _as_owner(found, name + " folder")
    return None


def _as_owner(found: Ownership, evidence: str) -> Owner:
    if isinstance(found, Owner):
        return found
    return Owner(manager=found.manager, package=found.package, confidence=found.confidence,
                 evidence=evidence)


def _module(name: str) -> Optional[object]:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def system_owners(ctx: "Context", paths: Sequence[str]) -> Dict[str, Owner]:
    """Step 3: one batched query per system package manager. Keys are the given paths."""
    if not paths or ctx.os_name != "linux":
        return {}
    wanted = list(dict.fromkeys(paths))
    reals = {p: files.real(p) for p in wanted}
    out: Dict[str, Owner] = {}

    if ctx.provider_available("pacman"):
        pac = _module("aiup.providers.linux_pacman")
        owners_of_fn = getattr(pac, "owners_of", None)
        if callable(owners_of_fn):
            try:
                found = owners_of_fn(ctx, sorted(set(reals.values())))
            except _ERRORS:
                found = {}
            if isinstance(found, dict) and found:
                foreign: FrozenSet[str] = frozenset()
                if ctx.provider_available("aur"):
                    foreign_fn = getattr(pac, "foreign_names", None)
                    try:
                        foreign = frozenset(foreign_fn(ctx)) if callable(foreign_fn) else frozenset()
                    except _ERRORS:
                        foreign = frozenset()
                for path, real_path in reals.items():
                    package = found.get(real_path)
                    if isinstance(package, str) and package:
                        manager = "aur" if package in foreign else "pacman"
                        out[path] = _owner(manager, package, True, "pacman -Qo")
        return out

    # apt, dnf and zypper: the provider's batched owns_many (dpkg-query -S, rpm -qf).
    for name, evidence in (("apt", "dpkg-query -S"), ("dnf", "rpm -qf"), ("zypper", "rpm -qf")):
        if not ctx.provider_available(name):
            continue
        provider = ctx.provider(name)
        if provider is None:
            continue
        try:
            found_many = provider.owns_many(ctx, wanted)
        except _ERRORS:
            found_many = {}
        for path, found_one in found_many.items():
            if found_one.package:
                out[path] = _owner(name, found_one.package, found_one.confidence == "exact", evidence)
        break
    return out


# ----- Windows: Uninstall entries ----------------------------------------------------------------

def registry_owner(ctx: "Context", resolved: str) -> Optional[Owner]:
    """Step 4: the Uninstall entry whose install folder holds the file."""
    if not files.is_windows(ctx):
        return None
    from aiup.detect import registry

    entry = registry.entry_for_path(ctx, resolved)
    if entry is None:
        return None
    return _owner("arp", entry.id, False, "install folder", "Programs and Features")


# ----- public: owner_of -----------------------------------------------------------------------------

def owner_of(path: str, ctx: "Context") -> Optional[Ownership]:
    """The owner of one file, exact answers first (design 8.2). None when unknown."""
    found = attribute(ctx, (path,), system=True).get(path)
    return found.owner if found is not None else None


def attribute(ctx: "Context", paths: Sequence[str], system: bool = True,
              heads: Optional[Mapping[str, bytes]] = None) -> Dict[str, Found]:
    """Owners for many paths at once: layout rules, providers, one system batch, registry."""
    out: Dict[str, Found] = {}
    weak: Dict[str, Found] = {}
    unknown: List[str] = []
    home = str(files.home(ctx))
    for path in paths:
        resolved = files.real(path)
        found = layout_owner(ctx, path, resolved, heads.get(path) if heads else None)
        if found is not None and found.owner.confidence == "exact":
            out[path] = found
            continue
        owner = provider_owner(ctx, path, resolved)
        if owner is not None:
            out[path] = Found(owner, version=found.version if found else "")
            continue
        if found is not None:
            weak[path] = found
        if system and not files.inside(resolved, home):
            unknown.append(path)
    if unknown:
        for path, owner in system_owners(ctx, unknown).items():
            out[path] = Found(owner)
    for path in paths:
        if path in out:
            continue
        owner = registry_owner(ctx, files.real(path))
        if owner is not None:
            out[path] = Found(owner, version=weak[path].version if path in weak else "")
        elif path in weak:
            out[path] = weak[path]
    return out


# ----- catalog matching -------------------------------------------------------------------------------

def loose(text: str) -> str:
    """A matching key: lower case, trailing versions dropped, only letters, digits and +."""
    return re.sub(r"[^a-z0-9+]", "", files.strip_version_words(text).lower())


def command_key(ctx: "Context", name: str) -> str:
    """A command name without PATHEXT suffix, lower case on Windows."""
    if files.is_windows(ctx):
        lowered = name.lower()
        for ext in (".exe", ".cmd", ".bat", ".com", ".ps1"):
            if lowered.endswith(ext):
                return lowered[:-len(ext)]
        return lowered
    return name


# Identity aliases from research section 11; the catalog adds its own.
_IDENTITY_ALIASES: Dict[str, str] = {
    "nodejs": "node", "node": "node", "openjsnodejs": "node", "openjsnodejslts": "node", "nodejslts": "node",
    "githubcli": "gh", "gh": "gh",
    "git": "git", "gitgit": "git", "gitforwindows": "git",
    "python": "python", "python3": "python", "pythoncore": "python", "pythonpython": "python",
    "code": "code", "visualstudiocode": "code", "microsoftvisualstudiocode": "code",
    "microsoftvisualstudiocodeuser": "code", "comvisualstudiocode": "code", "microsoftvisualstudiocodeinsiders": "code-insiders",
    "docker": "docker", "dockerdesktop": "docker",
    "rustc": "rust", "rustup": "rust",
    "go": "go", "golang": "go", "golanggo": "go",
}


@dataclass(frozen=True)
class CatalogIndex:
    entries: Mapping[str, "CatalogEntry"]
    by_command: Mapping[str, Tuple[str, ...]]
    by_key: Mapping[str, Tuple[str, ...]]
    covered: FrozenSet[Tuple[str, str]]


_CATALOG_LOCK = threading.Lock()
_EMPTY_INDEX = CatalogIndex({}, {}, {}, frozenset())


def catalog_index(ctx: "Context") -> CatalogIndex:
    """The catalog's commands, names and covered packages, loaded once per process."""
    key = "aiup.detect.catalog-index"
    with _CATALOG_LOCK:
        done = ctx.cache.recall(key)
        if isinstance(done, CatalogIndex):
            return done
        index = _EMPTY_INDEX
        try:
            from aiup.catalog import load

            index = _build_index(ctx, load(ctx.env))
        except _ERRORS:
            index = _EMPTY_INDEX
        ctx.cache.remember(key, index)
        return index


def _build_index(ctx: "Context", catalog: "Catalog") -> CatalogIndex:
    entries: Dict[str, "CatalogEntry"] = {}
    by_command: Dict[str, List[str]] = {}
    by_key: Dict[str, List[str]] = {}
    covered = set()
    for entry in catalog.entries:
        if not entry.available_on(ctx.os_name):
            continue
        entries[entry.id] = entry
        for command in entry.commands:
            ids = by_command.setdefault(command_key(ctx, command), [])
            if entry.id not in ids:
                ids.append(entry.id)
        for word in (entry.id, entry.label) + tuple(entry.aliases):
            ids = by_key.setdefault(loose(word), [])
            if word and entry.id not in ids:
                ids.append(entry.id)
        for target in entry.targets_for(ctx.os_name):
            covered.add((target.channel, target.package))
    return CatalogIndex(
        entries, {k: tuple(v) for k, v in by_command.items()},
        {k: tuple(v) for k, v in by_key.items() if k}, frozenset(covered),
    )


def identity_for(ctx: "Context", name: str) -> str:
    """One identity per tool, for duplicate grouping (research section 11)."""
    key = loose(command_key(ctx, name))
    if not key:
        return ""
    index = catalog_index(ctx)
    ids = index.by_key.get(key) or index.by_command.get(command_key(ctx, name))
    if ids and len(ids) == 1:
        return ids[0]
    return _IDENTITY_ALIASES.get(key, key)


def match_tool(ctx: "Context", item: InventoryItem) -> str:
    """The catalog id an item stands for, or "" (ambiguous names never match)."""
    index = catalog_index(ctx)
    if not index.entries:
        return ""
    if item.kind == "command":
        ids = index.by_command.get(command_key(ctx, item.name), ())
        return ids[0] if len(ids) == 1 else ""
    command = fact(item, "command")
    if command:
        ids = index.by_command.get(command_key(ctx, command), ())
        if len(ids) == 1:
            return ids[0]
    ids = index.by_key.get(loose(item.name), ())
    return ids[0] if len(ids) == 1 else ""


def entry_channels(ctx: "Context", tool: str) -> Tuple[str, ...]:
    entry = catalog_index(ctx).entries.get(tool)
    if entry is None:
        return ()
    return tuple(dict.fromkeys(t.channel for t in entry.targets_for(ctx.os_name)))


def classify(ctx: "Context", item: InventoryItem) -> InventoryItem:
    """Population, catalog tool, identity and default guidance for one detected item.

    - a catalog match whose copy belongs to one of the entry's channels (or to
      no known manager) is "managed": the catalog row already shows it;
    - a catalog match owned by another manager stays "detected" and offers "adopt";
    - an exact owner that is an available provider channel is "package": the
      provider's own inventory lists it;
    - everything else is "detected".
    """
    if item.population != "detected":
        return item
    tool = item.tool or match_tool(ctx, item)
    owner = item.owner
    population = "detected"
    if tool:
        channels = entry_channels(ctx, tool)
        if owner is None or owner.manager in channels or owner.manager in NO_PATH_ACTIONS:
            population = "managed"
    elif owner is not None and owner.confidence == "exact" and _is_channel(owner.manager) \
            and owner.manager not in NO_PATH_ACTIONS and ctx.provider_available(owner.manager):
        population = "package"
    changes: Dict[str, object] = {"population": population, "tool": tool}
    if not item.identity:
        changes["identity"] = tool or identity_for(ctx, fact(item, "command") or item.name)
    if not item.docs and tool:
        entry = catalog_index(ctx).entries.get(tool)
        if entry is not None and entry.docs:
            changes["docs"] = entry.docs
    actionable = _provider_target(ctx, replace(item, **changes)) is not None  # type: ignore[arg-type]
    if not actionable and not item.remove_argv and not item.quiet_remove_argv:
        changes["manual"] = True
        if not item.guidance:
            changes["guidance"] = DEFAULT_GUIDANCE if owner is None else \
                "Use " + str(owner) + " to update or remove it."
    if not item.description and item.kind == "command":
        changes["description"] = DEFAULT_DESCRIPTION
    return replace(item, **changes)  # type: ignore[arg-type]


def _is_channel(manager: str) -> bool:
    try:
        from aiup.providers import CHANNEL_MODULES
    except ImportError:
        return False
    return manager in CHANNEL_MODULES


# ----- actions ---------------------------------------------------------------------------------------

def _provider_target(ctx: "Context", item: InventoryItem) -> Optional[Target]:
    winget_id = fact(item, "winget_id")
    if winget_id and ctx.provider("winget") is not None and ctx.provider_available("winget"):
        return Target(channel="winget", package=winget_id)
    owner = item.owner
    if owner is None or not owner.package or item.confidence not in ACTIONABLE:
        return None
    if owner.manager in NO_PATH_ACTIONS or not _is_channel(owner.manager):
        return None
    if ctx.provider(owner.manager) is None or not ctx.provider_available(owner.manager):
        return None
    return Target(channel=owner.manager, package=owner.package)


def target_for(item: InventoryItem, ctx: "Context") -> Optional[Target]:
    """The provider target that updates and removes ``item``, or None."""
    return _provider_target(ctx, item)


def adopt_channel(item: InventoryItem, ctx: "Context") -> str:
    """The catalog channel to move a matched copy to, or "" when there is nothing to adopt."""
    if not item.tool or item.population == "managed":
        return ""
    channels = entry_channels(ctx, item.tool)
    if not channels:
        return ""
    if item.owner is not None and item.owner.manager in channels:
        return ""
    entry = catalog_index(ctx).entries.get(item.tool)
    default = entry.defaults.get(ctx.os_name, "") if entry is not None else ""
    return default if default in channels else channels[0]


def actions_for(item: InventoryItem, ctx: "Context") -> Tuple[str, ...]:
    """What the user can do with an item: "update", "remove", "adopt", "docs", "search"."""
    out: List[str] = []
    if _provider_target(ctx, item) is not None:
        out.extend(("update", "remove"))
    elif item.remove_argv or item.quiet_remove_argv:
        out.append("remove")
    if adopt_channel(item, ctx):
        out.append("adopt")
    if item.docs:
        out.append("docs")
    if item.population == "detected":
        out.append("search")
    return tuple(out)


def action_for(item: InventoryItem, op: str, ctx: "Context") -> Optional[Action]:
    """The engine Action for "update" or "remove", or None when there is none.

    Owners found by a path rule are checked live with the provider first, as
    the engine does before any change; when the provider does not confirm it,
    the Action has no steps and says why. "adopt" is ``aiup channel TOOL
    <channel>`` (see :func:`adopt_channel`); it has no Action here.
    """
    if op not in ("update", "remove"):
        return None
    target = _provider_target(ctx, item)
    if target is not None:
        provider = ctx.provider(target.channel)
        if provider is None:
            return None
        if item.kind == "command" and item.paths and not fact(item, "winget_id"):
            try:
                live = provider.owns(ctx, item.paths[0])
            except _ERRORS:
                live = None
            if live is None:
                return Action(tool=item.name, op=op, channel=target.channel, steps=(),
                              note="aiup could not confirm that {} owns {}. Nothing was changed.".format(
                                  target.channel, item.paths[0]))
            if live.package and live.package != target.package:
                target = Target(channel=target.channel, package=live.package)
        return provider.update(ctx, target) if op == "update" else provider.remove(ctx, target)
    if op == "remove" and (item.remove_argv or item.quiet_remove_argv):
        return _uninstaller_action(ctx, item)
    return None


def _uninstaller_action(ctx: "Context", item: InventoryItem) -> Action:
    quiet = item.quiet_remove_argv
    argv = item.remove_argv if (ctx.interactive or not quiet) and item.remove_argv else quiet
    interactive = argv is item.remove_argv
    privilege = "uac-possible" if item.scope == "system" else "none"
    step = Step(argv=tuple(argv), label="uninstall " + item.name, privilege=privilege, interactive=interactive)
    return Action(tool=item.name, op="remove", channel="arp", steps=(step,),
                  note="This runs the app's own uninstaller.")


