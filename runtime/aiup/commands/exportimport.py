"""aiup export [FILE] and aiup import FILE (macOS: cmd_export, cmd_import).

The export holds the installed catalog tools, the packages you installed
yourself that no catalog tool covers, and your preferences, as JSON (schema
``aiup-export-v1`` with the additive ``platform`` and ``packages`` keys of
section 9.4). No paths, host names or account details. An existing FILE is
never overwritten. Listing scans skip winget because its list may contact
its sources; export is a command you ask for, so it reads winget once.

The import shows what the file adds here, asks once, then adds the
preferences, installs the missing packages and installs the missing tools.
Tools already here are left alone; a tool excluded or held in either place
is not installed. ``--dry-run`` shows the plan only.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from aiup.commands import _common
from aiup.engine.prefs import IdRules, Preferences, edit_preferences, load_preferences, merge, policy_reason
from aiup.errors import EXIT_FAILED, EXIT_INTERRUPTED, EXIT_OK, AiupError, UsageError
from aiup.version import AIUP_VERSION

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.cli import Args
    from aiup.engine.context import Context
    from aiup.providers.base import Provider

SCHEMA = "aiup-export-v1"
FILE_LIMIT = 1048576
IMPORT_LOG = "import.log"
_WINGET = "winget"
_TOOL_ID = re.compile(r"[A-Za-z0-9:@._/+-]+")
_MANAGER = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
_PACKAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9@+._/:~-]{0,199}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_EMPTY_PREFS: Dict[str, object] = {"excluded": [], "holds": {}, "groups": {}, "cleanup": ""}


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """``aiup export`` or ``aiup import``."""
    ctx, catalog = _common.need(args, ctx)
    if args.command == "import":
        return _import(args, ctx, catalog)
    return _export(args, ctx, catalog)


# ----- export ------------------------------------------------------------------------


def _export(args: "Args", ctx: "Context", catalog: "Catalog") -> int:
    words = list(args.words)
    target = words[0] if words else ""
    if target.startswith("-"):
        raise UsageError("expected: aiup export [FILE]")
    if target and os.path.lexists(target):
        raise AiupError(target + " already exists; choose a new file name")
    tools = sorted(_common.installed_copies(ctx, catalog))
    packages: Dict[str, Set[str]] = {}
    for record in _scan_packages(ctx, catalog):
        if record.source and record.name and record.source != _WINGET:
            packages.setdefault(record.source, set()).add(record.name)
    winget = _winget_packages(ctx, catalog)
    if winget:
        packages[_WINGET] = winget
    try:
        prefs = load_preferences(ctx.dirs, IdRules(set(catalog.ids())))
    except AiupError:
        prefs = Preferences()
    doc: Dict[str, object] = {
        "schema": SCHEMA,
        "exported": datetime.date.today().isoformat(),
        "aiup": AIUP_VERSION,
        "platform": ctx.os_name,
        "tools": tools,
        "packages": {manager: sorted(names) for manager, names in sorted(packages.items())},
        "preferences": {"excluded": list(prefs.excluded), "holds": dict(prefs.holds),
                        "groups": {name: list(members) for name, members in prefs.groups.items()},
                        "cleanup": prefs.cleanup},
    }
    text = json.dumps(doc, indent=2) + "\n"
    out = _common.stdout()
    if not target:
        out.write(text)
        out.flush()
        return EXIT_OK
    try:
        handle = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        raise AiupError("could not write " + target + ": " + (exc.strerror or str(exc))) from exc
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
    except OSError as exc:
        # The file is ours (O_EXCL made it): never leave half an export behind.
        try:
            os.unlink(target)
        except OSError:
            pass
        raise AiupError("could not write " + target + ": " + (exc.strerror or str(exc))) from exc
    count = sum(len(names) for names in packages.values())
    out.write("Saved " + _common.plural(len(tools), "tool") + ", " + _common.plural(count, "package")
              + ", and your preferences to " + target + ". On another computer: aiup import " + target + "\n")
    out.flush()
    return EXIT_OK


def _scan_packages(ctx: "Context", catalog: "Catalog") -> List[object]:
    from aiup.commands import listing

    try:
        return list(listing.scan_packages(ctx, catalog))
    except (OSError, ValueError, AiupError):
        return []


def _winget_packages(ctx: "Context", catalog: "Catalog") -> Set[str]:
    """winget packages you installed that no catalog tool covers (macOS: brew leaves).

    The listing scan never runs winget, so export reads the provider here,
    once, and keeps the same rows a scan would: explicit installs only, and
    no package a catalog tool installs. winget ids compare without case.
    """
    provider = ctx.provider(_WINGET)
    if provider is None or not ctx.provider_available(_WINGET):
        return set()
    try:
        records = list(provider.inventory(ctx) or ())
    except (OSError, ValueError, NotImplementedError, AiupError):
        return set()
    covered = {target.package.strip().lower()
               for entry in catalog.entries for target in entry.targets_for(ctx.os_name)
               if target.channel == _WINGET}
    return {record.name for record in records
            if record.name and record.explicit and record.name.lower() not in covered}


# ----- import: reading the file ------------------------------------------------------


def _read_export(name: str) -> Dict[str, object]:
    source = Path(name)
    if source.is_symlink() or not source.is_file():
        raise AiupError("Not a regular file: " + name)
    try:
        if source.stat().st_size > FILE_LIMIT:
            raise AiupError(name + " is larger than 1 MiB; it is not an aiup export")
        with open(source, "r", encoding="utf-8") as handle:
            doc = json.loads(handle.read(FILE_LIMIT + 1))
    except (OSError, ValueError, UnicodeError) as exc:
        raise AiupError(name + " is not valid JSON") from exc
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise AiupError(name + " is not an aiup export (schema " + SCHEMA + ")")
    return doc


def _strings(value: object) -> List[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _mapping(value: object) -> Dict[str, object]:
    return {str(k): v for k, v in value.items()} if isinstance(value, dict) else {}


def _tool_ids(value: object) -> List[str]:
    return [v for v in _strings(value) if _TOOL_ID.fullmatch(v)]


def _clean_prefs(doc: Dict[str, object]) -> Dict[str, object]:
    """The preferences part, with only well-formed ids and dates (macOS cmd_import)."""
    prefs = _mapping(doc.get("preferences"))
    holds: Dict[str, str] = {}
    for tool, until in _mapping(prefs.get("holds")).items():
        if not _TOOL_ID.fullmatch(tool):
            continue
        try:
            holds[tool] = datetime.date.fromisoformat(str(until)).isoformat()
        except ValueError:
            continue
    groups = {name: _tool_ids(members) for name, members in _mapping(prefs.get("groups")).items()
              if _TOOL_ID.fullmatch(name)}
    cleanup = prefs.get("cleanup")
    return {"excluded": _tool_ids(prefs.get("excluded")), "holds": holds, "groups": groups,
            "cleanup": cleanup if cleanup in ("auto", "review") else ""}


def _wanted_packages(doc: Dict[str, object]) -> Dict[str, List[str]]:
    """Manager -> package names from ``packages``, plus Homebrew formulae for Linuxbrew."""
    out: Dict[str, List[str]] = {}

    def add(manager: str, name: str) -> None:
        if _MANAGER.fullmatch(manager) and _PACKAGE.fullmatch(name) and ".." not in name:
            names = out.setdefault(manager, [])
            if name not in names:
                names.append(name)

    for manager, names in _mapping(doc.get("packages")).items():
        for name in _strings(names):
            add(manager, name)
    for name in _strings(_mapping(doc.get("homebrew")).get("formulae")):
        add("brew", name)
    return out


# ----- import: the plan --------------------------------------------------------------


def _import(args: "Args", ctx: "Context", catalog: "Catalog") -> int:
    words = list(args.words)
    if len(words) != 1 or not words[0] or words[0].startswith("-"):
        raise UsageError("expected: aiup import FILE")
    name = words[0]
    doc = _read_export(name)
    ids = IdRules(set(catalog.ids()))
    clean = _clean_prefs(doc)
    local = load_preferences(ctx.dirs, ids)
    present_ids = set(_common.installed_copies(ctx, catalog))
    excluded = _strings(clean["excluded"])
    holds = _mapping(clean["holds"])

    tools: List[str] = []
    present: List[str] = []
    unknown: List[str] = []
    elsewhere: List[str] = []
    for raw in _strings(doc.get("tools")):
        tool = catalog.resolve(raw) or ""
        entry = catalog.get(tool) if tool else None
        if entry is None:
            unknown.append(_CONTROL.sub("", raw))
        elif not entry.available_on(ctx.os_name):
            elsewhere.append(entry.id)
        elif entry.id in present_ids:
            present.append(entry.id)
        elif entry.id in excluded or _held(holds, entry.id) or policy_reason(local, entry.id):
            continue
        elif entry.id not in tools:
            tools.append(entry.id)

    packages, unavailable = _missing_packages(ctx, _wanted_packages(doc))
    casks = _strings(_mapping(doc.get("homebrew")).get("casks"))

    out = _common.stdout()
    lines = ["", "  " + _common.ink("aiup import", "81", out) + " · " + _common.clean(name)]
    if tools:
        lines.append("  Install " + _common.plural(len(tools), "tool") + ": " + " ".join(tools))
    for manager, names in packages:
        lines.append("  Install " + _common.plural(len(names), manager + " package") + ": " + " ".join(names))
    lines.append("  Preferences: " + _prefs_summary(clean))
    if present:
        lines.append("  Already here: " + _common.plural(len(present), "tool"))
    if unknown:
        lines.append("  Not in this version of aiup, skipped: " + " ".join(unknown))
    if elsewhere:
        lines.append("  Not offered on this system, skipped: " + " ".join(elsewhere))
    if unavailable:
        lines.append("  No package manager for these here, skipped: " + ", ".join(unavailable))
    if casks:
        lines.append("  Homebrew apps are for macOS, skipped: " + _common.plural(len(casks), "app"))
    out.write("\n".join(lines) + "\n")
    out.flush()

    count = len(tools) + sum(len(names) for _, names in packages)
    if ctx.dry_run:
        out.write("\n  Dry run: nothing changed.\n")
        out.flush()
        return EXIT_OK
    if count == 0 and clean == _EMPTY_PREFS:
        out.write("\n  Nothing to import.\n")
        out.flush()
        return EXIT_OK
    if not ctx.interactive:
        raise AiupError("aiup import asks before it installs anything; run it in a terminal")
    out.write("\n")
    out.flush()
    if not _common.ask("  Install these and add the preferences? [y/N] "):
        out.write("  Nothing changed.\n")
        out.flush()
        return EXIT_OK
    edit_preferences(ctx.dirs, ids, lambda prefs: merge(prefs, ids, clean))

    from aiup.engine.run import install_packages

    failed, interrupted = install_packages(ctx, [(manager, name) for manager, names in packages for name in names],
                                           IMPORT_LOG, "aiup import")
    if interrupted:
        return EXIT_INTERRUPTED
    if not tools:
        return EXIT_FAILED if failed else EXIT_OK
    from aiup.engine.run import RunRequest, run as run_update

    # macOS: main_update with NO_INSTALL=0, the same request as aiup only.
    code = run_update(ctx, catalog, RunRequest(tools=tuple(tools), op="update", explicit=True))
    if code == EXIT_OK and failed:
        return EXIT_FAILED
    return code


def _held(holds: Dict[str, object], tool: str) -> bool:
    """True when the imported file holds ``tool`` through today or later."""
    until = holds.get(tool)
    return isinstance(until, str) and until >= datetime.date.today().isoformat()


def _missing_packages(ctx: "Context", wanted: Dict[str, List[str]]
                      ) -> Tuple[List[Tuple[str, List[str]]], List[str]]:
    """(manager, names not installed here) for managers available here, and the managers that are not."""
    missing: List[Tuple[str, List[str]]] = []
    unavailable: List[str] = []
    for manager in sorted(wanted):
        provider = ctx.provider(manager)
        if provider is None or not ctx.provider_available(manager):
            unavailable.append(manager)
            continue
        have = _installed_names(ctx, provider)
        names = [name for name in wanted[manager] if name not in have and name.rsplit("/", 1)[-1] not in have]
        if names:
            missing.append((manager, names))
    return missing, unavailable


def _installed_names(ctx: "Context", provider: "Provider") -> Set[str]:
    """Every package the manager has, explicit or not, so a dependency is not installed again."""
    try:
        return {record.name for record in provider.inventory(ctx) or () if record.name}
    except (OSError, ValueError, NotImplementedError, AiupError):
        return set()


def _prefs_summary(clean: Dict[str, object]) -> str:
    parts: List[str] = []
    excluded = clean["excluded"]
    holds = clean["holds"]
    groups = clean["groups"]
    if isinstance(excluded, list) and excluded:
        parts.append("excluded " + ", ".join(excluded))
    if isinstance(holds, dict) and holds:
        parts.append("held " + ", ".join(t + " through " + d for t, d in holds.items()))
    if isinstance(groups, dict) and groups:
        parts.append("groups " + ", ".join(groups))
    if clean["cleanup"]:
        parts.append("cleanup " + str(clean["cleanup"]))
    return "; ".join(parts) + " (added to yours)" if parts else "none"
