"""Slow, on-demand sources (research 4.14 to 4.16 and 5.3).

These run only when a caller asks for slow sources (``run_batch(ctx, "slow")``),
never on the first paint of a listing:

- ``models``: Ollama manifests and LM Studio model folders;
- ``containers``: ``docker image ls`` and ``podman image ls`` (local daemon only);
- ``mcp``: MCP servers in agent and editor configs. Only the server name, the
  launcher's file name, a package spec and a URL host are kept: never
  arguments, environment values or headers, which may hold secrets;
- ``extensions``: VS Code family extensions from ``extensions.json``.

The winget correlation (which Uninstall entries winget can manage) is never
part of a scan because ``winget list`` may contact its sources. It runs only
through :func:`winget_correlation` with ``allow_run=True``; scans read its
cached answer for up to a day.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from aiup.detect import files, owners
from aiup.detect.items import InventoryItem, Owner, det_id
from aiup.detect.sources import HARD_TIMEOUT, DetectionSource, cache_dir, register
from aiup.engine.cache import atomic_write_json, read_json
from aiup.errors import AiupError
from aiup.platform.base import split_path

if TYPE_CHECKING:
    from aiup.engine.context import Context

OUTPUT_MAX = 1024 * 1024
MAX_ROWS = 2000
CORRELATION_TTL = 24 * 3600
CORRELATION_VERSION = 1
_ERRORS = (OSError, ValueError, NotImplementedError, AiupError)


def _item(item_id: str, name: str, version: str, source: str, path: str, kind: str, owner: Owner,
          scope: str, guidance: str, description: str = "",
          facts: Tuple[Tuple[str, str], ...] = ()) -> InventoryItem:
    return InventoryItem(
        id=item_id, name=name, version=version, population="detected", source=source,
        paths=(path,) if path else (), owner=owner, kind=kind, scope=scope, confidence="exact",
        evidence=owner.evidence, manual=True, guidance=guidance, description=description, facts=facts,
    )


def _which(ctx: "Context", command: str) -> str:
    found = shutil.which(command, path=os.pathsep.join(split_path(files.env_get(ctx, "PATH"))))
    return found or ""


def _dirs(folder: object) -> List[os.DirEntry]:
    out: List[os.DirEntry] = []
    for entry in files.scandir(folder):
        try:
            if entry.is_dir() and not entry.name.startswith("."):
                out.append(entry)
        except OSError:
            continue
    return out


# ----- local models --------------------------------------------------------------------------


def ollama_dirs(ctx: "Context") -> List[Path]:
    custom = files.env_dir(ctx, "OLLAMA_MODELS")
    out = [custom] if custom is not None else []
    out.append(files.home(ctx) / ".ollama" / "models")
    if not files.is_windows(ctx):
        out.append(Path("/usr/share/ollama/.ollama/models"))
        out.append(Path("/var/lib/ollama/.ollama/models"))
    return out


def _ollama_name(host: str, namespace: str, model: str) -> str:
    if host == "registry.ollama.ai":
        return model if namespace == "library" else namespace + "/" + model
    return host + "/" + namespace + "/" + model


def ollama_models(ctx: "Context") -> List[InventoryItem]:
    out: List[InventoryItem] = []
    seen: Dict[str, bool] = {}
    for root in ollama_dirs(ctx):
        manifests = root / "manifests"
        for host in _dirs(manifests):
            for namespace in _dirs(host.path):
                for model in _dirs(namespace.path):
                    for tag in files.scandir(model.path):
                        name = _ollama_name(host.name, namespace.name, model.name) + ":" + tag.name
                        if name in seen or len(out) >= MAX_ROWS:
                            continue
                        seen[name] = True
                        data = files.read_json(tag.path)
                        size = 0
                        if isinstance(data, dict):
                            layers = data.get("layers")
                            for layer in (layers if isinstance(layers, list) else []) + [data.get("config")]:
                                if isinstance(layer, dict) and isinstance(layer.get("size"), int):
                                    size += layer["size"]
                        owner = Owner(manager="ollama", package=name, confidence="exact", label="Ollama",
                                      evidence="Ollama manifest")
                        out.append(_item(
                            det_id("models", "ollama:" + name), name, "", "models", tag.path, "model", owner,
                            _scope(ctx, str(root)),
                            "Update it with: ollama pull {0}. Remove it with: ollama rm {0}.".format(name),
                            description="Ollama model", facts=(("size", str(size)),) if size else (),
                        ))
    return out


def lmstudio_dirs(ctx: "Context") -> List[Path]:
    home = files.home(ctx)
    return [home / ".lmstudio" / "models", home / ".cache" / "lm-studio" / "models"]


def lmstudio_models(ctx: "Context") -> List[InventoryItem]:
    out: List[InventoryItem] = []
    for root in lmstudio_dirs(ctx):
        for publisher in _dirs(root):
            for model in _dirs(publisher.path):
                if len(out) >= MAX_ROWS:
                    return out
                name = publisher.name + "/" + model.name
                owner = Owner(manager="lmstudio", package=name, confidence="exact", label="LM Studio",
                              evidence="LM Studio models folder")
                out.append(_item(
                    det_id("models", "lmstudio:" + name.lower()), name, "", "models", model.path, "model", owner,
                    "user", "Manage it in LM Studio.", description="LM Studio model",
                ))
    return out


def _scope(ctx: "Context", path: str) -> str:
    return "user" if files.inside(path, str(files.home(ctx))) else "system"


class ModelsSource(DetectionSource):
    name = "models"
    oses = frozenset(("linux", "windows"))
    cost = "slow"

    def fingerprint(self, ctx: "Context") -> str:
        parts: List[str] = []
        for root in ollama_dirs(ctx):
            manifests = root / "manifests"
            parts.append(str(manifests) + "=" + files.stat_stamp(manifests))
            for host in _dirs(manifests):
                for namespace in _dirs(host.path):
                    for model in _dirs(namespace.path):
                        parts.append(model.path + "=" + files.stat_stamp(model.path))
        for root in lmstudio_dirs(ctx):
            parts.append(str(root) + "=" + files.stat_stamp(root))
            for publisher in _dirs(root):
                parts.append(publisher.path + "=" + files.stat_stamp(publisher.path))
        return files.stamp(parts)

    def read(self, ctx: "Context") -> List[InventoryItem]:
        return ollama_models(ctx) + lmstudio_models(ctx)


# ----- container images --------------------------------------------------------------------------


def _image_rows(text: str) -> List[Tuple[str, str, str]]:
    """``(repository, tag, id)`` from ``image ls --format '{{json .}}'`` lines (Docker or Podman)."""
    out: List[Tuple[str, str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        repo = data.get("Repository")
        tag = data.get("Tag")
        ident = data.get("ID") or data.get("Id") or ""
        if not isinstance(repo, str):
            names = data.get("Names")
            first = names[0] if isinstance(names, list) and names and isinstance(names[0], str) else ""
            repo, _sep, tag = first.rpartition(":") if ":" in first.rsplit("/", 1)[-1] else (first, "", "")
        if not repo or repo == "<none>":
            continue
        out.append((repo, tag if isinstance(tag, str) and tag != "<none>" else "", str(ident)[:19]))
    return out


class ContainersSource(DetectionSource):
    name = "containers"
    oses = frozenset(("linux", "windows"))
    cost = "slow"

    def probe(self, ctx: "Context") -> bool:
        return any(_which(ctx, c) for c in ("docker", "podman"))

    def read(self, ctx: "Context") -> List[InventoryItem]:
        out: List[InventoryItem] = []
        for runtime, label in (("docker", "Docker"), ("podman", "Podman")):
            exe = _which(ctx, runtime)
            if not exe:
                continue
            result = ctx.run_read((exe, "image", "ls", "--format", "{{json .}}"), timeout=HARD_TIMEOUT,
                                  max_bytes=OUTPUT_MAX)
            if result.returncode != 0 or result.timed_out:
                continue
            for repo, tag, ident in _image_rows(result.stdout)[:MAX_ROWS]:
                ref = repo + (":" + tag if tag else "")
                owner = Owner(manager=runtime, package=ref, confidence="exact", label=label,
                              evidence=runtime + " image ls")
                out.append(_item(
                    det_id("containers", runtime + ":" + ref), ref, tag, "containers", "", "image", owner,
                    "system" if runtime == "docker" else "user",
                    "Update it with: {0} pull {1}. Remove it with: {0} image rm {1}.".format(runtime, ref),
                    description=label + " image", facts=(("image_id", ident),) if ident else (),
                ))
        return out


# ----- MCP servers -----------------------------------------------------------------------------------

_RUNNERS = frozenset(("npx", "bunx", "uvx", "pnpm", "pipx", "yarn", "deno"))
_SPEC = re.compile(r"^[@A-Za-z0-9][\w@./:+-]{0,199}$")
# Runner flags that take no value (Deno's --allow-* and --deny-* too), and flags
# whose value is the package.
_SWITCHES = frozenset(("-y", "--yes", "-q", "--quiet", "-s", "--silent", "--prefer-offline", "--no-install",
                       "-A", "--allow-all", "--ignore-existing", "--offline", "--isolated", "--refresh",
                       "--bun", "--no", "--no-cache", "--prefer-online"))
_PACKAGE_FLAGS = frozenset(("-p", "--package", "--from", "--spec"))


# ~/.claude.json also holds Claude Code's project history, so it often passes
# the usual 1 MiB limit. Only server names and the launcher, package and host
# facts _server derives are kept; args, env and headers are never stored.
CLAUDE_JSON_MAX = 16 * 1024 * 1024


def mcp_configs(ctx: "Context") -> List[Tuple[str, str, Path, str]]:
    """``(client key, label, file, servers key)``."""
    home = files.home(ctx)
    if files.is_windows(ctx):
        config = files.roaming_appdata(ctx)
    else:
        config = files.env_dir(ctx, "XDG_CONFIG_HOME", ".config") or home / ".config"
    codex = files.env_dir(ctx, "CODEX_HOME") or home / ".codex"
    return [
        ("claude-code", "Claude Code", home / ".claude.json", "mcpServers"),
        ("claude-desktop", "Claude Desktop", config / "Claude" / "claude_desktop_config.json", "mcpServers"),
        ("cursor", "Cursor", home / ".cursor" / "mcp.json", "mcpServers"),
        ("vscode", "VS Code", config / "Code" / "User" / "mcp.json", "servers"),
        ("windsurf", "Windsurf", home / ".codeium" / "windsurf" / "mcp_config.json", "mcpServers"),
        ("gemini", "Gemini CLI", home / ".gemini" / "settings.json", "mcpServers"),
        ("codex", "Codex", codex / "config.toml", "mcp_servers"),
    ]


def _package_spec(launcher: str, args: Sequence[str]) -> str:
    base = os.path.basename(launcher).lower()
    if base.endswith((".cmd", ".exe")):
        base = base[:-4]
    if base not in _RUNNERS:
        return ""
    # After an unknown flag, aiup cannot tell whether the next word is that
    # flag's value or the package. Guessing wrong would keep an argument,
    # which may be a token (bunx --bun server TOKEN), so no spec is kept then.
    uncertain = False
    for arg in args:
        if arg in _PACKAGE_FLAGS:
            continue         # the next word names the package
        if arg.startswith("-"):
            if "=" not in arg and arg not in _SWITCHES and not arg.startswith(("--allow-", "--deny-")):
                uncertain = True
            continue
        if arg in ("dlx", "run", "exec", "x"):
            continue
        if uncertain:
            return ""
        # A URL spec (git+https://user:token@host/...) can carry credentials.
        return arg if _SPEC.match(arg) and "://" not in arg else ""
    return ""


def _host(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


def _server(name: str, command: str, args: Sequence[str], url: str) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
    facts: List[Tuple[str, str]] = []
    if command:
        facts.append(("launcher", os.path.basename(command)))
        spec = _package_spec(command, args)
        if spec:
            facts.append(("package", spec))
    host = _host(url) if url else ""
    if host:
        facts.append(("host", host))
    detail = dict(facts).get("package") or dict(facts).get("host") or dict(facts).get("launcher") or ""
    return detail, tuple(facts)


def _json_servers(data: object, key: str) -> List[Tuple[str, str, List[str], str]]:
    servers = data.get(key) if isinstance(data, dict) else None
    out: List[Tuple[str, str, List[str], str]] = []
    if not isinstance(servers, dict):
        return out
    for name, spec in servers.items():
        if not isinstance(name, str) or not isinstance(spec, dict):
            continue
        command = spec.get("command")
        args = spec.get("args")
        url = spec.get("url") or spec.get("serverUrl") or spec.get("httpUrl")
        out.append((name, command if isinstance(command, str) else "",
                    [a for a in args if isinstance(a, str)] if isinstance(args, list) else [],
                    url if isinstance(url, str) else ""))
    return out




_TOML_TABLE = re.compile(r"^\[\s*mcp_servers\.(\"[^\"]+\"|[A-Za-z0-9_-]+)\s*\]\s*(?:#.*)?$")
_TOML_STRING = re.compile(r"^(command|url)\s*=\s*\"((?:[^\"\\]|\\.)*)\"")
_TOML_ARGS = re.compile(r"^args\s*=\s*\[(.*)\]\s*(?:#.*)?$")
_TOML_QUOTED = re.compile(r"\"((?:[^\"\\]|\\.)*)\"")


class _TomlServer:
    def __init__(self, name: str) -> None:
        self.name = name
        self.command = ""
        self.url = ""
        self.args: List[str] = []


def toml_servers(text: str) -> List[Tuple[str, str, List[str], str]]:
    """``[mcp_servers.NAME]`` tables from a Codex config (one-line values only)."""
    found: List[_TomlServer] = []
    current: Optional[_TomlServer] = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            match = _TOML_TABLE.match(line)
            current = _TomlServer(match.group(1).strip('"')) if match else None
            if current is not None:
                found.append(current)
            continue
        if current is None:
            continue
        match = _TOML_STRING.match(line)
        if match:
            if match.group(1) == "command":
                current.command = match.group(2)
            else:
                current.url = match.group(2)
            continue
        match = _TOML_ARGS.match(line)
        if match:
            current.args = _TOML_QUOTED.findall(match.group(1))
    return [(s.name, s.command, s.args, s.url) for s in found]


def mcp_servers(ctx: "Context") -> List[InventoryItem]:
    out: List[InventoryItem] = []
    for client, label, path, key in mcp_configs(ctx):
        if path.suffix == ".toml":
            text = files.read_text(path)
            servers = toml_servers(text) if text else []
        else:
            limit = CLAUDE_JSON_MAX if client == "claude-code" else files.JSON_MAX
            servers = _json_servers(files.read_json(path, limit), key)
        for name, command, args, url in servers[:MAX_ROWS]:
            detail, facts = _server(name, command, args, url)
            owner = Owner(manager="mcp-config", package=client + ":" + name, confidence="exact", label=label,
                          evidence=path.name)
            out.append(_item(
                det_id("mcp", client + ":" + name), name, "", "mcp", str(path), "integration", owner, "user",
                "Change or remove it in the " + label + " MCP settings.",
                description=("MCP server: " + detail) if detail else "MCP server",
                facts=(("client", client),) + facts,
            ))
    return out


class McpSource(DetectionSource):
    name = "mcp"
    oses = frozenset(("linux", "windows"))
    cost = "slow"

    def fingerprint(self, ctx: "Context") -> str:
        return files.stamp_paths(path for _c, _l, path, _k in mcp_configs(ctx))

    def read(self, ctx: "Context") -> List[InventoryItem]:
        return mcp_servers(ctx)


# ----- editor extensions -----------------------------------------------------------------------------


def extension_dirs(ctx: "Context") -> List[Tuple[str, str, Path]]:
    home = files.home(ctx)
    return [
        ("vscode", "VS Code", home / ".vscode" / "extensions"),
        ("vscode-insiders", "VS Code Insiders", home / ".vscode-insiders" / "extensions"),
        ("vscodium", "VSCodium", home / ".vscode-oss" / "extensions"),
        ("cursor", "Cursor", home / ".cursor" / "extensions"),
        ("windsurf", "Windsurf", home / ".windsurf" / "extensions"),
    ]


_EXTENSION_FOLDER = re.compile(r"^([A-Za-z0-9][\w-]*\.[\w.-]+?)-(\d[\w.+-]*?)(?:-(?:linux|win32|darwin|alpine|web)[\w-]*)?$")


def _extensions_from_json(data: object) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for row in data if isinstance(data, list) else ():
        if not isinstance(row, dict):
            continue
        identifier = row.get("identifier")
        ident = identifier.get("id") if isinstance(identifier, dict) else None
        version = row.get("version")
        if isinstance(ident, str) and ident:
            out.append((ident, version if isinstance(version, str) else ""))
    return out


def editor_extensions(ctx: "Context") -> List[InventoryItem]:
    out: List[InventoryItem] = []
    for editor, label, folder in extension_dirs(ctx):
        if not files.exists_dir(folder):
            continue
        found = _extensions_from_json(files.read_json(folder / "extensions.json"))
        if not found:
            for entry in _dirs(folder):
                match = _EXTENSION_FOLDER.match(entry.name)
                if match:
                    found.append((match.group(1), match.group(2)))
        seen: Dict[str, bool] = {}
        for ident, version in found[:MAX_ROWS]:
            key = ident.lower()
            if key in seen:
                continue
            seen[key] = True
            owner = Owner(manager="editor-extension", package=editor + ":" + ident, confidence="exact",
                          label=label, evidence="extensions.json")
            out.append(_item(
                det_id("extensions", editor + ":" + key), ident, version, "extensions", str(folder), "extension",
                owner, "user", "Update or remove it in the " + label + " Extensions view.",
                description=label + " extension", facts=(("editor", editor),),
            ))
    return out


class ExtensionsSource(DetectionSource):
    name = "extensions"
    oses = frozenset(("linux", "windows"))
    cost = "slow"

    def fingerprint(self, ctx: "Context") -> str:
        parts: List[str] = []
        for _editor, _label, folder in extension_dirs(ctx):
            parts.append(str(folder) + "=" + files.stat_stamp(folder))
            parts.append("json=" + files.stat_stamp(folder / "extensions.json"))
        return files.stamp(parts)

    def read(self, ctx: "Context") -> List[InventoryItem]:
        return editor_extensions(ctx)


# ----- winget correlation ------------------------------------------------------------------------------


def _correlation_path(ctx: "Context") -> Path:
    return cache_dir(ctx) / "winget-correlation.json"


def _read_correlation(ctx: "Context") -> Optional[Dict[str, str]]:
    """The cached map when it is younger than a day; None otherwise."""
    data = read_json(_correlation_path(ctx), OUTPUT_MAX)
    if not isinstance(data, dict) or data.get("v") != CORRELATION_VERSION:
        return None
    at = data.get("at")
    ids = data.get("ids")
    if not isinstance(at, (int, float)) or not isinstance(ids, dict):
        return None
    if not 0 <= time.time() - float(at) < CORRELATION_TTL:
        return None
    return {k: v for k, v in ids.items() if isinstance(k, str) and isinstance(v, str)}


def cached_winget_ids(ctx: "Context") -> Mapping[str, str]:
    """Uninstall entry id -> winget id, from the last explicit correlation (never runs winget)."""
    if not files.is_windows(ctx):
        return {}
    return _read_correlation(ctx) or {}


def correlate(rows: Sequence[Tuple[str, str, str, str]], entries: Sequence[Tuple[str, str, str]]) -> Dict[str, str]:
    """Match ``winget list`` rows ``(name, id, version, source)`` to entries ``(entry id, name, version)``.

    A row matches when its name equals the entry's display name (loosely,
    or as a prefix when winget shortened it) and the versions agree when
    both are known. Rows that would match more than one entry are dropped.
    """
    out: Dict[str, str] = {}
    for name, ident, version, source in rows:
        if source.lower() != "winget" or not ident:
            continue
        shortened = name.endswith("…")
        key = owners.loose(name.rstrip("…"))
        if not key:
            continue
        hits = [
            entry_id for entry_id, entry_name, entry_version in entries
            if (owners.loose(entry_name).startswith(key) if shortened else owners.loose(entry_name) == key)
            and (not version or not entry_version or version == entry_version)
        ]
        if len(hits) == 1 and hits[0] not in out:
            out[hits[0]] = ident
    return out


def winget_correlation(ctx: "Context", allow_run: bool = False) -> Mapping[str, str]:
    """Uninstall entry id -> winget id.

    Reads the day-old cache. With ``allow_run`` (an explicit user request)
    and no fresh cache, runs ``winget list`` once, which may contact winget's
    sources, and caches the answer.
    """
    if not files.is_windows(ctx):
        return {}
    cached = None if ctx.refresh and allow_run else _read_correlation(ctx)
    if cached is not None or not allow_run:
        return cached or {}
    from aiup.providers.win_winget import AGREE, WingetProvider, parse_table

    provider = WingetProvider()
    try:
        if not provider.available(ctx):
            return {}
        # The provider's read marks winget unavailable for the run when it hangs.
        result = provider._run(ctx, (provider.exe(ctx), "list") + tuple(AGREE), 60.0, 8 * OUTPUT_MAX)
    except _ERRORS:
        return {}
    if result.code != 0:
        return {}
    try:
        parsed, _found = parse_table(result.out, True)
    except _ERRORS:
        return {}
    # A shortened id cannot be passed back to winget.
    # A shortened version counts as unknown.
    rows = [(str(r.name), str(r.id), "" if str(r.version).endswith("\u2026") else str(r.version), str(r.source))
            for r in parsed if not str(r.id).endswith("\u2026")]
    from aiup.detect import registry

    entries = [(e.id, e.name, e.version) for e in registry.entries(ctx)]
    ids = correlate(rows, entries)
    try:
        atomic_write_json(_correlation_path(ctx), {"v": CORRELATION_VERSION, "at": time.time(), "ids": ids})
    except _ERRORS:
        pass
    return ids


for _source in (ModelsSource(), ContainersSource(), McpSource(), ExtensionsSource()):
    register(_source)
