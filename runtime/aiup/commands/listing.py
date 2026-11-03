"""aiup list, aiup install and aiup preview TOOL (macOS: cmd_catalog_browse,
cmd_install_interactive, print_list, print_inventory_definition --plain and
print_catalog_preview).

On a terminal, ``aiup list`` opens the picker and loops: pick, act, pick
again, until the person closes it. ``--plain``, ``--detected`` or no terminal
print tables. ``aiup install`` opens the picker once and acts on the choice.

Picker actions run as a separate aiup process (``aiup only``, ``aiup
--no-install only`` and ``aiup remove``), so they follow exactly the rules
those commands follow when typed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Mapping, Optional, Sequence, Set, TextIO, Tuple

from aiup.engine.channels import Resolution, channel_label, resolve
from aiup.engine.latest import classify, read_latest
from aiup.engine.prefs import (
    IdRules, Preferences, channels_path, load_channels, load_preferences, policy_reason,
    preferences_path,
)
from aiup.errors import EXIT_FAILED, EXIT_INTERRUPTED, EXIT_OK, AiupError, UsageError
from aiup.platform import term
from aiup.tui import session as tui_session
from aiup.tui.picker import (
    PickerRun, PickerUnavailable, PickResult, find_fzf, make_launch, run_picker, session_actions,
)
from aiup.tui.preview import print_catalog_preview
from aiup.tui.rows import (
    CategoryInfo, InventoryRecord, Style, ToolRecord, clean, make_style, pad, source_summary,
)
from aiup.tui.session import InstalledTool, SessionData, populations
from aiup.version import AIUP_VERSION

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.cli import Args
    from aiup.engine.context import Context
    from aiup.model import CatalogEntry, Target

PACKAGES_BLURB = "Packages you installed with a package manager that are not catalog tools."
DETECTED_BLURB = "Found on this computer. aiup does not change these."
PREFS_UNREADABLE = "Preferences could not be read; fix preferences.json before updating"
FAST_REPEAT = 0.5   # seconds: a picker that closes this fast with no choice twice is not interactive

Job = Tuple[InstalledTool, "Target"]


# ----- entry point ------------------------------------------------------------------


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """``aiup list``, ``aiup install`` and ``aiup preview TOOL``."""
    if ctx is None or args.catalog is None:
        raise AiupError("aiup {} needs the catalog and this computer's context".format(args.command))
    catalog = args.catalog
    if args.command == "preview":
        return run_preview(args, ctx, catalog)
    if args.command == "install":
        if not ctx.interactive:
            raise AiupError("aiup install needs a terminal. Name the tools instead: aiup only TOOL")
        try:
            return browse(args, ctx, catalog, mode="install", loop=False)
        except PickerUnavailable as exc:
            ctx.say("aiup: " + exc.message)
            return EXIT_FAILED
    if args.list_mode == "detected":
        print_detected(ctx, _stdout())
        return EXIT_OK
    if args.list_mode == "plain" or not ctx.interactive:
        print_list(args, ctx, catalog, _stdout())
        return EXIT_OK
    try:
        return browse(args, ctx, catalog, mode="browse", loop=True)
    except PickerUnavailable as exc:
        ctx.say("aiup: " + exc.message)
        ctx.say("aiup: here is the plain list instead (aiup list --plain).")
        print_list(args, ctx, catalog, _stdout())
        return EXIT_OK


def _stdout() -> TextIO:
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError, OSError):
        pass
    return sys.stdout


# ----- reading this computer ----------------------------------------------------------


@dataclass
class Scan:
    """Catalog tool states and the jobs the Updates prefetch runs."""

    tools: List[ToolRecord] = field(default_factory=list)
    installed: List[InstalledTool] = field(default_factory=list)
    jobs: List[Job] = field(default_factory=list)


def _preferences(ctx: "Context", catalog: "Catalog") -> Optional[Preferences]:
    try:
        return load_preferences(ctx.dirs, IdRules(set(catalog.ids())))
    except AiupError:
        return None


def _reason(prefs: Optional[Preferences], tool: str) -> str:
    if prefs is None:
        return PREFS_UNREADABLE
    return policy_reason(prefs, tool)


def _resolution(ctx: "Context", entry: "CatalogEntry", policy: str,
                picks: Mapping[str, str]) -> Optional[Resolution]:
    try:
        return resolve(entry, ctx.os_name, policy, picks, ctx)
    except (OSError, ValueError, NotImplementedError, AiupError):
        return None


def tool_record(entry: "CatalogEntry", category: str, res: Optional[Resolution], reason: str,
                os_name: str) -> Tuple[ToolRecord, Optional[Job]]:
    """One catalog tool's row data, plus its prefetch job when it is installed.

    States follow macOS catalog_action_for_state: a copy on the active
    channel is installed, a copy only on other channels is on-disk (enter
    switches it), and no copy is absent.
    """
    active = res.active if res is not None else None
    copy = res.copy_on(active.channel) if (res is not None and active is not None) else None
    notes: List[Tuple[str, str]] = []
    version = ""
    found_via = ""
    if copy is not None and active is not None:
        state = "installed"
        version = copy.version
        found_via = channel_label(copy.channel or active.channel)
        action = "update" if entry.lifecycle == "active" else entry.lifecycle
    elif res is not None and res.installed:
        state = "on-disk"
        target, other = res.installed[0]
        version = other.version
        found_via = channel_label(target.channel)
        action = "switch to " + channel_label(active.channel) if active is not None else "inspect"
    else:
        state = "absent"
        action = "install"
    targets = entry.targets_for(os_name)
    if not targets:
        notes.append(("platform", "not offered on this system"))
    elif active is None:
        labels = sorted({channel_label(t.channel) for t in targets})
        notes.append(("needs", "one of: " + ", ".join(labels)))
    if reason:
        notes.append(("policy", reason))
    if res is not None and res.kept_note:
        notes.append(("other copies", res.kept_note))
    if entry.notes:
        notes.append(("notes", entry.notes))
    search = [t.package for t in targets] + list(entry.commands)
    record = ToolRecord(
        id=entry.id, category=category, label=entry.label, state=state,
        lifecycle=entry.lifecycle, version=version, docs=entry.docs,
        aliases=tuple(entry.aliases), search_extra=" ".join(search),
        channel=channel_label(active.channel) if active is not None else "",
        installed_channel=found_via, action=action, notes=tuple(notes),
    )
    job: Optional[Job] = None
    if state == "installed" and active is not None:
        tool = InstalledTool(entry.id, active.channel, version, entry.label, entry.lifecycle, not reason)
        job = (tool, active)
    return record, job


def scan_tools(ctx: "Context", catalog: "Catalog") -> Scan:
    """Every catalog tool offered here, read in parallel."""
    choices = load_channels(ctx.dirs, ctx.os_name)
    prefs = _preferences(ctx, catalog)
    entries = list(catalog.available_on(ctx.os_name))
    workers = max(1, min(len(entries) or 1, ctx.config.check_workers))

    def one(entry: "CatalogEntry") -> Tuple[ToolRecord, Optional[Job]]:
        res = _resolution(ctx, entry, choices.policy, choices.picks)
        return tool_record(entry, entry.category, res, _reason(prefs, entry.id), ctx.os_name)

    scan = Scan()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for record, job in pool.map(one, entries):
            scan.tools.append(record)
            if job is not None:
                scan.installed.append(job[0])
                scan.jobs.append(job)
    return scan


_INVENTORY_KEY = "aiup.listing.inventory:"


def _inventory(ctx: "Context", include_slow: bool) -> Optional[object]:
    """One merged detection pass per process (aiup.detect.merge), or None without that module.

    Every listing reads this one pass: packages and detected rows come from
    the same inventory, and it never runs winget or any other network read.
    """
    key = _INVENTORY_KEY + ("slow" if include_slow else "cheap")
    done = ctx.cache.recall(key)
    if done is not None:
        return done
    try:
        from aiup.detect import merge as detect_merge  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        if exc.name in ("aiup.detect", "aiup.detect.merge"):
            return None
        raise
    generation = ctx.cache.generation()
    inv = detect_merge.inventory(ctx, include_slow=include_slow)
    ctx.cache.remember_from(generation, key, inv)
    return inv


def forget_scans(ctx: "Context") -> None:
    """Drop this process's remembered passes after an action changed what is installed."""
    # engine.latest keeps each provider's bulk outdated list for the process;
    # after an update it would still offer the update just made. A new
    # generation also stops a prefetch still running from storing an old list.
    keys = [_INVENTORY_KEY + cost for cost in ("cheap", "slow")]
    keys += ["outdated:" + provider.name for provider in ctx.providers()]
    ctx.cache.forget_scans(keys)
    try:
        from aiup.detect import forget  # type: ignore[import-not-found]
    except ImportError:
        return
    forget(ctx)


def scan_packages(ctx: "Context", catalog: "Catalog", include_slow: bool = False) -> List[InventoryRecord]:
    """Packages installed on request that no catalog tool covers (``pkg:<manager>:<name>``)."""
    inv = _inventory(ctx, include_slow)
    out: List[InventoryRecord] = []
    seen: Set[str] = set()
    for item in getattr(inv, "packages", ()) if inv is not None else ():
        record = _package_record(item)
        if record is not None and record.id not in seen:
            seen.add(record.id)
            out.append(record)
    return out


def scan_detected(ctx: "Context", cheap_only: bool) -> List[InventoryRecord]:
    """Detected-only items (``det:<source>:<key>``) from the merged inventory.

    The picker reads only the cheap sources, so it opens fast; the plain
    ``--detected`` table reads them all.
    """
    inv = _inventory(ctx, not cheap_only)
    out: List[InventoryRecord] = []
    seen: Set[str] = set()
    for item in getattr(inv, "detected", ()) if inv is not None else ():
        record = _detected_record(item)
        if record is not None and record.id not in seen:
            seen.add(record.id)
            out.append(record)
    return out


def _first_path(item: object) -> str:
    paths = tuple(getattr(item, "paths", ()) or ())
    return str(paths[0]) if paths else ""


def _usable_id(row_id: str) -> bool:
    """False for an id fzf rows cannot carry.

    Ids come from file names, config keys and package names. A tab or line
    break would add a field or a row to the fzf list, and an id that starts
    or ends with spaces would not match after the helper strips it.
    """
    return bool(row_id) and row_id == row_id.strip() and \
        not any(ord(ch) < 32 or 0x7F <= ord(ch) < 0xA0 for ch in row_id)


def _package_record(item: object) -> Optional[InventoryRecord]:
    """A package row. A detected copy an available manager owns gets that manager's ``pkg:`` id."""
    owner = getattr(item, "owner", None)
    manager = str(getattr(owner, "manager", "") or "")
    package = str(getattr(owner, "package", "") or "")
    row_id = str(getattr(item, "id", "") or "")
    if not row_id.startswith("pkg:"):
        if not manager or not package:
            return None
        row_id = "pkg:" + manager + ":" + package
    if not _usable_id(row_id):
        return None
    source = manager or str(getattr(item, "source", "") or "")
    return InventoryRecord(
        id=row_id, population="package", name=str(getattr(item, "name", "") or package),
        version=str(getattr(item, "version", "") or ""), source=source, path=_first_path(item),
        owner=source, docs=str(getattr(item, "docs", "") or ""),
    )


def _detected_record(item: object) -> Optional[InventoryRecord]:
    row_id = str(getattr(item, "id", "") or "")
    if not row_id.startswith("det:") or not _usable_id(row_id):
        return None
    owner = getattr(item, "owner", None)
    return InventoryRecord(
        id=row_id, population="detected", name=str(getattr(item, "name", "") or row_id),
        version=str(getattr(item, "version", "") or ""), source=str(getattr(item, "source", "") or ""),
        path=_first_path(item), manual=bool(getattr(item, "manual", False)),
        owner=str(owner) if owner is not None else "", docs=str(getattr(item, "docs", "") or ""),
        guidance=str(getattr(item, "guidance", "") or ""),
    )


def categories(catalog: "Catalog") -> List[CategoryInfo]:
    """Catalog categories in display order, then packages and detected."""
    out = [CategoryInfo(c.id, c.name, c.order, c.emoji, c.blurb)
           for c in catalog.categories if c.id != "updates"]
    known = {c.id for c in out}
    if "packages" not in known:
        out.append(CategoryInfo("packages", "Packages", 9998, "", PACKAGES_BLURB))
    if "detected" not in known:
        out.append(CategoryInfo("detected", "Detected", 9999, "", DETECTED_BLURB))
    return out


# ----- session data and the snapshot cache ----------------------------------------------


def _snapshot_key(args: "Args", ctx: "Context", catalog: "Catalog", style: Style, mode: str) -> str:
    return tui_session.snapshot_key([
        AIUP_VERSION, ctx.os_name, mode, args.view, args.sort, args.category,
        "color" if style.color else "bw", style.glyphs.installed, catalog.version,
        tui_session.file_stamp(channels_path(ctx.dirs)),
        tui_session.file_stamp(preferences_path(ctx.dirs)),
    ])


def _jobs(catalog: "Catalog", os_name: str, installed: Iterable[InstalledTool]) -> List[Job]:
    """Prefetch jobs for a snapshot: each installed tool with its active target."""
    out: List[Job] = []
    for tool in installed:
        entry = catalog.get(tool.id)
        if entry is None:
            continue
        target = next((t for t in entry.targets_for(os_name) if t.channel == tool.channel), None)
        if target is not None:
            out.append((tool, target))
    return out


def session_data(args: "Args", ctx: "Context", catalog: "Catalog", style: Style,
                 mode: str = "browse") -> Tuple[SessionData, List[Job]]:
    """The rows for one picker window, from the snapshot cache when it is fresh.

    ``remove`` mode keeps only what aiup can remove: installed catalog tools,
    packages, and detected items with a verified remover.
    """
    key = _snapshot_key(args, ctx, catalog, style, mode)
    data = None if ctx.refresh else tui_session.load_snapshot(ctx.dirs, key, ctx.config.tui_cache_ttl)
    if data is not None:
        return data, _jobs(catalog, ctx.os_name, data.installed)
    _progress(style, True)
    try:
        want_catalog, want_packages, want_detected = populations(args.view, args.category)
        scan = scan_tools(ctx, catalog) if want_catalog else Scan()
        packages = scan_packages(ctx, catalog) if want_packages else []
        detected = scan_detected(ctx, cheap_only=True) if want_detected else []
    finally:
        _progress(style, False)
    if mode == "remove":
        detected = [d for d in detected if not d.manual]
    names = {p.source: channel_label(p.source) for p in packages}
    data = tui_session.assemble(
        categories(catalog), scan.tools, packages, detected, scan.installed, style, ctx.os_name,
        view=args.view, sort_mode=args.sort, category_filter=args.category, manager_names=names,
        mode=mode,
    )
    tui_session.save_snapshot(ctx.dirs, key, data)
    return data, scan.jobs


def _progress(style: Style, start: bool) -> None:
    """A one-line note on stderr while the first scan runs."""
    text = "Reading installed tools" + style.glyphs.ellipsis
    try:
        if start:
            sys.stderr.write(text + "\r")
        else:
            sys.stderr.write(" " * len(text) + "\r")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def _style(ctx: "Context", stream: TextIO) -> Style:
    color = not ctx.config.no_color and term.color_enabled(stream)
    unicode = not ctx.config.ascii and term.use_unicode(stream)
    return make_style(color, unicode)


def _first_open(data: SessionData, selected: str) -> Set[str]:
    """Categories to open in the first window: only the one holding the saved row.

    macOS starts with every category closed; opening the saved row's
    category puts the cursor back where the person left it.
    """
    parents: Dict[str, str] = {}
    for row in data.rows:
        if row.get("kind") == "header":
            parents[str(row.get("cat", ""))] = str(row.get("parent", "") or "")
    for row in data.rows:
        if row.get("id") == selected and row.get("kind") != "header":
            cat = str(row.get("cat", ""))
            return {c for c in (cat, parents.get(cat, "")) if c}
    return set()


# ----- the picker loop ------------------------------------------------------------------


def _fzf_hint(catalog: "Catalog", os_name: str) -> str:
    entry = catalog.get("fzf")
    if entry is not None and entry.available_on(os_name):
        return "aiup only fzf"
    return "your package manager"


def browse(args: "Args", ctx: "Context", catalog: "Catalog", *, mode: str, loop: bool) -> int:
    """Open the picker. With ``loop``, act and reopen until it is closed.

    Raises PickerUnavailable when fzf is missing or too old.
    """
    fzf = find_fzf(ctx.platform, _fzf_hint(catalog, ctx.os_name))
    launch = make_launch(ctx.os_name)
    style = _style(ctx, sys.stderr)
    palette = ctx.os_name != "windows"
    tui_session.cleanup_stale(ctx.dirs, ctx.platform, ctx.config.tui_session_ttl)
    saved = tui_session.load_ui_state(ctx.dirs)
    query, selected = saved.query, saved.selected
    expanded: Optional[Set[str]] = None
    done: List[Tuple[str, Tuple[str, ...], int]] = []
    quick = 0
    while True:
        data, jobs = session_data(args, ctx, catalog, style, mode)
        opened = expanded if expanded is not None else _first_open(data, selected)
        live = tui_session.create(
            ctx.dirs, data, style, expanded=opened, actions=session_actions(launch),
            fzf_path=fzf.path, palette=palette, platform_name=ctx.os_name,
            view=args.view, sort_mode=args.sort, category_filter=args.category, mode=mode,
        )
        started = time.monotonic()
        try:
            result = run_picker(ctx, live, PickerRun(
                fzf=fzf, launch=launch, style=style, query=query, selected=selected,
                palette=palette, timings=args.timings, mode=mode, jobs=jobs,
            ), term.columns())
            state = tui_session.read_back(live)
        finally:
            live.close()
        tui_session.save_ui_state(ctx.dirs, state)
        query, selected, expanded = state.query, state.selected, state.expanded
        if result.action == "cancel":
            if not loop:
                return EXIT_FAILED
            break
        if result.action == "none":
            if not loop:
                return EXIT_FAILED
            quick = quick + 1 if time.monotonic() - started < FAST_REPEAT else 0
            if quick >= 2:
                ctx.say("aiup: fzf keeps closing on its own; check FZF_DEFAULT_OPTS.")
                break
            continue
        quick = 0
        status = act(args, ctx, catalog, result)
        done.append((result.action, result.ids, status))
        tui_session.drop_snapshots(ctx.dirs)
        forget_scans(ctx)
        if not loop:
            return status
        if not _pause():
            break
    _summary(ctx, done)
    return EXIT_OK


def _main_command() -> List[str]:
    """How to start this aiup again in a child process."""
    runtime = Path(__file__).resolve().parents[2]
    script = runtime / "aiup_main.py"
    if script.is_file():
        return [sys.executable, "-B", str(script)]
    return [sys.executable, "-B", "-m", "aiup"]


def action_argv(args: "Args", ctx: "Context", result: PickResult, ids: Sequence[str]) -> List[str]:
    """The aiup command line for a picker action (macOS apply_catalog_action)."""
    flags: List[str] = []
    if ctx.dry_run:
        flags.append("--dry-run")
    if ctx.verbose:
        flags.append("--verbose")
    if args.plain:
        flags.append("--plain")
    if result.action == "remove":
        words = ["remove"]
    elif result.action == "update":
        words = ["--no-install", "only"]
    else:
        words = ["only"]
    return _main_command() + flags + words + list(ids)


def act(args: "Args", ctx: "Context", catalog: "Catalog", result: PickResult) -> int:
    """Run the chosen action in a child aiup and return its exit status."""
    ids = list(result.ids)
    if result.action == "apply":
        ids = _confirm_sunset(catalog, ids)
    if not ids:
        return EXIT_OK
    argv = action_argv(args, ctx, result, ids)
    env = dict(os.environ)
    if "-m" in argv[:4]:
        root = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        process = subprocess.Popen(argv, env=env)
    except OSError as exc:
        ctx.say("aiup: could not start the action: {}".format(exc.strerror or exc))
        return EXIT_FAILED
    try:
        return process.wait()
    except KeyboardInterrupt:
        while True:
            try:
                process.wait()
                break
            except KeyboardInterrupt:
                continue
        return EXIT_INTERRUPTED


def _ask(prompt: str) -> bool:
    try:
        sys.stderr.write(prompt)
        sys.stderr.flush()
        line = sys.stdin.readline()
    except (OSError, ValueError, KeyboardInterrupt):
        return False
    return line.strip().casefold() in ("y", "yes")


def _confirm_sunset(catalog: "Catalog", ids: Sequence[str]) -> List[str]:
    """Ask before installing or updating a tool whose lifecycle is not active."""
    keep: List[str] = []
    for tool in ids:
        entry = catalog.get(tool)
        if entry is None or entry.lifecycle == "active":
            keep.append(tool)
            continue
        sys.stderr.write("{}: {} ({})\n".format(tool, clean(entry.label), entry.lifecycle))
        if _ask("Install or update {} tool '{}' anyway? [y/N] ".format(entry.lifecycle, tool)):
            keep.append(tool)
    return keep


def _pause() -> bool:
    """Let the person read the action's output before the list comes back."""
    try:
        sys.stderr.write("\nPress enter to go back to the list, or q and enter to quit. ")
        sys.stderr.flush()
        line = sys.stdin.readline()
    except (OSError, ValueError, KeyboardInterrupt):
        return False
    if not line:
        return False
    return line.strip().casefold() not in ("q", "quit", "exit")


_ACTION_WORDS = {"apply": "install or update", "update": "update", "remove": "remove"}


def _summary(ctx: "Context", done: Sequence[Tuple[str, Tuple[str, ...], int]]) -> None:
    """What the picker did this time (macOS print_result_summary, short form)."""
    if not done:
        return
    ctx.say("Picker actions:")
    for action, ids, status in done:
        if status == EXIT_OK:
            outcome = "done"
        elif status == EXIT_INTERRUPTED:
            outcome = "stopped"
        else:
            outcome = "failed (exit {})".format(status)
        ctx.say("  {} {}: {}".format(_ACTION_WORDS.get(action, action), ", ".join(ids), outcome))


# ----- plain tables ------------------------------------------------------------------------


def _line(cells: Sequence[str], widths: Sequence[int]) -> str:
    """Columns padded by display width (wide characters line up); the last is free."""
    parts = [pad(clean(c), w) for c, w in zip(cells, widths)]
    parts.extend(clean(c) for c in cells[len(widths):])
    return " ".join(parts).rstrip() + "\n"


def print_list(args: "Args", ctx: "Context", catalog: "Catalog", out: TextIO) -> None:
    """The categorized table (macOS print_list)."""
    want_catalog, want_packages, want_detected = populations(args.view, args.category)
    installed_view = args.view == "installed"
    if want_catalog:
        scan = scan_tools(ctx, catalog)
        by_category: Dict[str, List[ToolRecord]] = {}
        for record in scan.tools:
            by_category.setdefault(record.category, []).append(record)
        for cat in catalog.tool_categories():
            if args.category and cat.id != args.category:
                continue
            members = by_category.get(cat.id, [])
            present = sorted((r for r in members if r.state != "absent"), key=lambda r: r.id)
            absent = sorted((r for r in members if r.state == "absent"), key=lambda r: r.id)
            if (installed_view and not present) or not members:
                continue
            out.write("\n== {} ({}) ==\n".format(clean(cat.name), cat.id))
            out.write(_line(("tool", "state/action", "label"), (18, 18)))
            for record in present:
                out.write(_line((record.id, record.action, record.label), (18, 18)))
            if not installed_view:
                for record in absent:
                    out.write(_line((record.id, "install", record.label), (18, 18)))
    if want_packages:
        _print_packages(args, ctx, catalog, out)
    if want_detected:
        records = scan_detected(ctx, cheap_only=False)
        if records:
            info = next((c for c in categories(catalog) if c.id == "detected"), None)
            out.write("\n== {} (detected) ==\n".format(clean(info.name) if info else "Detected"))
            if ctx.verbose:
                dot = "·" if term.use_unicode(out) else "|"
                out.write("Detected-only inventory {} {}.\n".format(dot, source_summary(records, dot)))
                out.write("aiup will not change these without a verified updater or remover; "
                          "use ctrl-o in the picker or aiup docs for a web search.\n")
            _detected_table(records, out)
    out.flush()


def _print_packages(args: "Args", ctx: "Context", catalog: "Catalog", out: TextIO) -> None:
    records = scan_packages(ctx, catalog)
    if args.category.startswith("packages/"):
        manager = args.category.split("/", 1)[1]
        records = [r for r in records if r.source == manager]
    if not records:
        return
    info = next((c for c in categories(catalog) if c.id == "packages"), None)
    out.write("\n== {} (packages) ==\n".format(clean(info.name) if info else "Packages"))
    out.write(_line(("tool", "state/action", "label"), (18, 18)))
    if ctx.verbose:
        out.write(PACKAGES_BLURB + "\n")
    by_manager: Dict[str, List[InventoryRecord]] = {}
    for record in records:
        by_manager.setdefault(record.source or "other", []).append(record)
    for manager in sorted(by_manager):
        out.write("\n-- {} (packages/{}) --\n".format(channel_label(manager), manager))
        for record in sorted(by_manager[manager], key=lambda r: clean(r.name).casefold()):
            out.write(_line((record.name, "installed", record.version or "version unknown"), (18, 18)))


def _detected_table(records: Sequence[InventoryRecord], out: TextIO) -> None:
    widths = (26, 12, 18)
    out.write(_line(("item", "version", "found via", "location"), widths))
    for record in sorted(records, key=lambda r: (clean(r.name).casefold(), r.id)):
        out.write(_line((record.name, record.version or "unknown", record.source, record.path), widths))


def print_detected(ctx: "Context", out: TextIO) -> None:
    """``aiup list --detected``: the detected table alone (macOS print_inventory_definition --plain)."""
    _detected_table(scan_detected(ctx, cheap_only=False), out)
    out.flush()


# ----- aiup preview TOOL ----------------------------------------------------------------------


def _available_text(ctx: "Context", entry: "CatalogEntry", res: Optional[Resolution], record: ToolRecord) -> str:
    """The available line for one installed tool, read through the version cache."""
    if record.state != "installed" or res is None or res.active is None:
        return ""
    provider = ctx.provider(res.active.channel)
    if provider is None:
        return ""
    latest = read_latest(ctx, provider, res.active, entry.id, record.version)
    verdict = classify(record.version, latest)
    if verdict == "skipped":
        return latest.managed   # another updater owns this copy (Microsoft Store)
    if verdict == "update" and not latest.version:
        return "unknown (an update is waiting)"   # Latest.pending: no version named
    if verdict == "update":
        return latest.version + " (update available)"
    if verdict == "current":
        return latest.version + " (current)"
    if verdict == "self-updated":
        return "{} (yours is newer)".format(latest.version)
    return latest.unverified_reason or "could not check"


def run_preview(args: "Args", ctx: "Context", catalog: "Catalog") -> int:
    """``aiup preview TOOL``: the picker preview for one catalog tool."""
    word = args.words[0] if args.words else ""
    tool = catalog.resolve(word)
    entry = catalog.get(tool) if tool else None
    if entry is None:
        raise UsageError("'{}' is not a catalog tool. aiup list --plain shows them all".format(clean(word)))
    choices = load_channels(ctx.dirs, ctx.os_name)
    res = _resolution(ctx, entry, choices.policy, choices.picks) if entry.available_on(ctx.os_name) else None
    reason = _reason(_preferences(ctx, catalog), entry.id)
    record, _ = tool_record(entry, entry.category, res, reason, ctx.os_name)
    category = catalog.category(entry.category)
    out = _stdout()
    style = _style(ctx, out)
    out.write(print_catalog_preview(record, category.name if category else entry.category, style,
                                    _available_text(ctx, entry, res, record)))
    out.flush()
    return EXIT_OK
