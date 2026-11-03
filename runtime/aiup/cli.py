"""Argument parsing and dispatch (macOS ``parse_args`` and ``usage``).

Global flags may appear anywhere. Every value is checked before anything
runs, and a mistake exits 2 with one line. Each command then goes to
``aiup.commands.<module>.run(args, ctx) -> int``; a module that is not part
of this runtime yet prints one line and exits 1.

With ``--json``, the JSON document goes to the original stdout and
everything a person reads goes to stderr, as macOS does with
``exec 6>&1 1>&2``. Command code writes JSON to ``args.json_stream``.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, replace
from typing import IO, TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

from aiup import commands
from aiup.config import Config, load_config
from aiup.errors import (
    EXIT_FAILED, EXIT_INTERRUPTED, EXIT_OK, AiupError, NotImplementedOnSystem,
    PlatformUnsupported, UsageError,
)
from aiup.version import AIUP_VERSION

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.engine.context import Context

VIEWS = ("overview", "all", "installed", "managed", "detected", "available")
SORTS = ("id", "label")
PLATFORMS = ("linux", "windows", "all")
SYSTEM_SETTINGS = ("report", "ask", "auto")
AUR_SETTINGS = ("review", "trust")
CLEANUP_SETTINGS = ("auto", "review")
ISSUES_URL = "https://github.com/travisjneuman/aiup/issues"
# Inventory managers that can follow `packages/` in --category.
NOT_PACKAGE_MANAGERS = ("vendor", "script")

_BOOL_FLAGS = ("--dry-run", "--json", "--verbose", "--show-unchanged", "--force", "--no-install",
               "--plain", "--refresh", "--timings")
_VALUE_FLAGS = ("--heartbeat-seconds", "--category", "--view", "--sort", "--platform")

# Commands --json works with (macOS: '', full, core, only, resume, retry,
# check, group run, group check). catalog and inventory use it as their format.
_JSON_RUNS = ("update", "check")
_JSON_FORMATS = ("catalog", "inventory")

# Typed name -> canonical command (section 2.1).
_ALIASES = {"full": "update", "core": "update", "only": "update", "resume": "update",
            "retry": "update", "npm-update": "update", "uninstall": "remove",
            "home": "docs", "open": "docs"}

# Commands that work without the Linux and Windows engine, and on macOS.
_LIGHT = ("version", "help", "catalog")


@dataclass
class Args:
    """The parsed command line."""

    command: str = "update"            # canonical command (see commands.COMMAND_MODULES)
    invoked: str = ""                  # what was typed: "", full, only, uninstall, home, ...
    words: Tuple[str, ...] = ()        # positional words after the command (options removed)
    subcommand: str = ""               # group set|run|check|remove, settings cleanup|system|aur, ...
    # Global flags (section 2.2).
    dry_run: bool = False
    json: bool = False
    verbose: bool = False
    show_unchanged: bool = False
    force: bool = False
    no_install: bool = True            # plain runs never install; only/retry/import may
    no_install_explicit: bool = False
    plain: bool = False
    refresh: bool = False
    timings: bool = False
    heartbeat_seconds: Optional[int] = None
    category: str = ""
    view: str = "overview"
    sort: str = "id"
    # Command options.
    print_only: bool = False           # docs --print
    details: bool = False              # doctor --details
    always: bool = False               # notify --always
    all_rows: bool = False             # coverage --all, plan --all
    apply: bool = False                # cleanup --apply (macOS only)
    catalog_format: str = "json"       # catalog --json|--markdown
    platform: str = ""                 # catalog --platform linux|windows|all
    list_mode: str = ""                # list: "" (picker), "plain", "detected"
    inventory_mode: str = "json"       # inventory: json|plain
    policy: Optional[str] = None       # channel --policy [VALUE]: "" when no value
    # Filled in by main().
    os_name: str = ""
    config: Optional[Config] = None
    catalog: Optional["Catalog"] = None
    json_stream: Optional[IO[str]] = field(default=None, repr=False)

    @property
    def tools(self) -> Tuple[str, ...]:
        """The tool words for commands that take tools."""
        return self.words


def current_os() -> str:
    """linux, windows or darwin."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------


def _set_bool(args: Args, flag: str) -> None:
    if flag == "--no-install":
        args.no_install = True
        args.no_install_explicit = True
        return
    attr = flag[2:].replace("-", "_")
    setattr(args, attr, True)


def _set_value(args: Args, flag: str, value: str) -> None:
    if flag == "--heartbeat-seconds":
        if not (value.isdigit() and value.isascii()) or int(value) < 1:
            raise UsageError("--heartbeat-seconds needs a whole number of seconds, 1 or more")
        args.heartbeat_seconds = int(value)
    elif flag == "--category":
        args.category = value
    elif flag == "--view":
        args.view = value
    elif flag == "--sort":
        args.sort = value
    elif flag == "--platform":
        args.platform = value


def split_flags(argv: Sequence[str], args: Args) -> List[str]:
    """Apply global flags from anywhere in argv; return the other words in order."""
    rest: List[str] = []
    index = 0
    while index < len(argv):
        word = argv[index]
        if word in _BOOL_FLAGS:
            _set_bool(args, word)
            if word == "--plain" and rest[:1] == ["inventory"]:
                rest.append(word)
        elif word in _VALUE_FLAGS:
            if index + 1 >= len(argv):
                raise UsageError(word + " needs a value")
            _set_value(args, word, argv[index + 1])
            index += 1
        else:
            rest.append(word)
        index += 1
    return rest


def _check_flag_values(args: Args) -> None:
    if args.view not in VIEWS:
        raise UsageError("unknown list view '{}'".format(args.view))
    if args.sort not in SORTS:
        raise UsageError("unknown list sort '{}'".format(args.sort))
    if args.platform and args.command != "catalog":
        raise UsageError("--platform works with aiup catalog")
    if args.platform and args.platform not in PLATFORMS:
        raise UsageError("unknown platform '{}' (linux, windows or all)".format(args.platform))
    if args.json and args.command not in _JSON_RUNS + _JSON_FORMATS:
        if not (args.command == "group" and args.subcommand in ("run", "check")):
            raise UsageError("--json works with update runs and aiup check")


def check_category(args: Args, catalog: "Catalog") -> None:
    """--category takes a catalog category, packages, packages/<manager> or detected."""
    value = args.category
    if not value:
        return
    from aiup.providers import CHANNEL_MODULES

    names = {c.id for c in catalog.tool_categories()} | {"packages", "detected"}
    managers = {"packages/" + m for m in CHANNEL_MODULES if m not in NOT_PACKAGE_MANAGERS}
    if value not in names and value not in managers:
        raise UsageError("unknown category '{}'".format(value))


# ---------------------------------------------------------------------------
# Command words
# ---------------------------------------------------------------------------


def _take_options(words: List[str], allowed: Sequence[str], command: str) -> List[str]:
    """Remove allowed option words; refuse any other word that starts with '-'."""
    found: List[str] = []
    for word in list(words):
        if word.startswith("-") and len(word) > 1:
            if word not in allowed:
                raise UsageError("unknown option '{}' for aiup {}".format(word, command))
            found.append(word)
            words.remove(word)
    return found


def _expect(condition: bool, text: str) -> None:
    if not condition:
        raise UsageError("expected: " + text)


def _parse_update(args: Args, typed: str, words: List[str]) -> None:
    _take_options(words, (), typed or "update")
    if typed in ("", "full", "core"):
        _expect(not words, "aiup {}".format(typed).strip())
    elif typed == "only":
        _expect(bool(words), "aiup only <tools...>")
        if not args.no_install_explicit:
            args.no_install = False
    elif typed == "npm-update":
        _expect(not words, "aiup npm-update")
        words.append("npm")
        if not args.no_install_explicit:
            args.no_install = False
    elif typed in ("resume", "retry"):
        _expect(not words, "aiup " + typed)
        if typed == "retry" and not args.no_install_explicit:
            args.no_install = False
    args.subcommand = typed


def _parse_group(args: Args, words: List[str]) -> None:
    usage = "aiup group set NAME TOOLS... | run NAME | check NAME | remove NAME"
    _take_options(words, (), "group")
    _expect(bool(words), usage)
    sub = words.pop(0)
    args.subcommand = sub
    if sub == "set":
        _expect(len(words) >= 2, usage)
    elif sub in ("run", "check", "remove"):
        _expect(len(words) == 1, usage)
    else:
        raise UsageError("expected: " + usage)
    if sub == "run":
        args.command = "update"        # never installs: no_install stays on
    elif sub == "check":
        args.command = "check"


def _parse_settings(args: Args, words: List[str]) -> None:
    linux = args.os_name == "linux"
    usage = ("aiup settings [cleanup auto|review | system report|ask|auto"
             + (" | aur review|trust]" if linux else "]"))
    _take_options(words, (), "settings")
    if not words:
        return
    sub = words.pop(0)
    args.subcommand = sub
    choices = {"cleanup": CLEANUP_SETTINGS, "system": SYSTEM_SETTINGS, "aur": AUR_SETTINGS}.get(sub)
    if choices is None:
        raise UsageError("expected: " + usage)
    if sub == "aur" and not linux:
        raise AiupError("AUR is Linux only")
    _expect(len(words) == 1 and words[0] in choices,
            "aiup settings {} {}".format(sub, "|".join(choices)))


def _parse_channel(args: Args, words: List[str]) -> None:
    usage = ("aiup channel [TOOL [CHANNEL|default]] or aiup channel --policy "
             + ("[newest|keep|system|MANAGER]" if args.os_name != "windows" else "[newest|keep|winget|scoop|choco]"))
    if "--policy" in words:
        _expect(words[0] == "--policy" and len(words) <= 2, usage)
        args.policy = words[1] if len(words) == 2 else ""
        words.clear()
        return
    _take_options(words, (), "channel")
    _expect(len(words) <= 2, usage)


def _parse_catalog(args: Args, words: List[str]) -> None:
    found = _take_options(words, ("--markdown", "--md", "--contracts"), "catalog")
    _expect(not words, "aiup catalog [--json|--markdown] [--platform linux|windows|all]")
    if "--contracts" in found:
        raise PlatformUnsupported("catalog --contracts")
    if "--markdown" in found or "--md" in found:
        if args.json:
            raise UsageError("pick one of --json or --markdown")
        args.catalog_format = "markdown"
    if not args.platform:
        from aiup.catalog.export import default_platform

        args.platform = default_platform(args.os_name)


def _parse_cleanup(args: Args, words: List[str]) -> None:
    if words == ["history"]:
        args.subcommand = "history"
        words.clear()
        return
    if words[:1] == ["history"]:
        raise UsageError("expected: aiup cleanup history")
    trash = "Recycle Bin" if args.os_name == "windows" else "Trash"
    raise PlatformUnsupported(
        " ".join(["cleanup"] + words[:1]),
        "Use aiup remove TOOL; it moves the tool's known user data to the {}. "
        "aiup cleanup history works here.".format(trash))


def _parse_list(args: Args, words: List[str]) -> None:
    found = _take_options(words, ("--plain", "--detected"), "list")
    _expect(not words, "aiup list [--plain|--detected]")
    if "--detected" in found:
        args.list_mode = "detected"
    elif "--plain" in found or args.plain:
        args.list_mode = "plain"


# Commands checked only by option words and word counts:
# typed name -> (allowed options, fewest words, most words or None, expected text).
SimpleRule = Tuple[Tuple[str, ...], int, Optional[int], str]
_SIMPLE_RULES: Dict[str, SimpleRule] = {
    "check": ((), 0, None, "aiup check [tools...]"),
    "plan": (("--all",), 0, 0, "aiup plan [--all]"),
    "install": ((), 0, 0, "aiup install"),
    "remove": ((), 0, None, "aiup remove [tools...]"),
    "uninstall": ((), 0, None, "aiup uninstall [tools...]"),
    "preview": ((), 1, 1, "aiup preview <tool>"),
    "explain": ((), 1, 1, "aiup explain <tool>"),
    "docs": (("--print", "-p"), 1, 1, "aiup docs [--print] <tool>"),
    "home": (("--print", "-p"), 1, 1, "aiup home [--print] <tool>"),
    "open": (("--print", "-p"), 1, 1, "aiup open [--print] <tool>"),
    "doctor": (("--details",), 0, 0, "aiup doctor [--details]"),
    "attention": ((), 0, 0, "aiup attention"),
    "owners": ((), 0, 0, "aiup owners"),
    "duplicates": ((), 0, 0, "aiup duplicates"),
    "coverage": (("--all",), 0, 0, "aiup coverage [--all]"),
    "welcome": ((), 0, 0, "aiup welcome"),
    "preferences": ((), 0, 0, "aiup preferences"),
    "exclude": ((), 1, 1, "aiup exclude TOOL"),
    "include": ((), 1, 1, "aiup include TOOL"),
    "unhold": ((), 1, 1, "aiup unhold TOOL"),
    "hold": ((), 2, 2, "aiup hold TOOL YYYY-MM-DD"),
    "system": ((), 0, 0, "aiup system"),
    "export": ((), 0, 1, "aiup export [FILE]"),
    "import": ((), 1, 1, "aiup import FILE"),
    "notify": (("--always",), 0, 0, "aiup notify [--always]"),
    "history": ((), 0, 1, "aiup history [tool]"),
    "logs": ((), 0, 1, "aiup logs [tool]"),
    "inventory": (("--plain",), 0, 0, "aiup inventory [--plain|--refresh]"),
    "project": ((), 1, 1, "aiup project <directory>"),
}


def _parse_simple(args: Args, typed: str, words: List[str]) -> None:
    """Commands checked only by option words and word counts."""
    allowed, low, high, text = _SIMPLE_RULES[typed]
    found = _take_options(words, allowed, typed)
    _expect(len(words) >= low and (high is None or len(words) <= high), text)
    args.print_only = "--print" in found or "-p" in found
    args.details = "--details" in found
    args.always = "--always" in found
    args.all_rows = "--all" in found
    if typed == "inventory":
        if "--plain" in found and args.json:
            raise UsageError("pick one of --json or --plain")
        args.inventory_mode = "plain" if "--plain" in found else "json"


_SIMPLE = tuple(_SIMPLE_RULES)


def parse(argv: Sequence[str], os_name: Optional[str] = None) -> Args:
    """Parse argv (without the program name) into :class:`Args`. Raises UsageError."""
    args = Args(os_name=os_name or current_os())
    words = split_flags(argv, args)
    typed = words.pop(0) if words else ""
    args.invoked = typed
    if typed in ("help", "-h", "--help"):
        args.command = "help"
    elif typed in ("version", "--version"):
        args.command = "version"
    elif typed.startswith("__"):
        args.command = typed
    elif typed in ("", "full", "core", "only", "resume", "retry", "npm-update"):
        args.command = "update"
        _parse_update(args, typed, words)
    elif typed == "group":
        args.command = "group"
        _parse_group(args, words)
    elif typed == "settings":
        args.command = "settings"
        _parse_settings(args, words)
    elif typed == "channel":
        args.command = "channel"
        _parse_channel(args, words)
    elif typed == "catalog":
        args.command = "catalog"
        _parse_catalog(args, words)
    elif typed == "cleanup":
        args.command = "cleanup"
        _parse_cleanup(args, words)
    elif typed == "list":
        args.command = "list"
        _parse_list(args, words)
    elif typed in _SIMPLE:
        args.command = _ALIASES.get(typed, typed)
        _parse_simple(args, typed, words)
    elif typed.startswith("-"):
        raise UsageError("unknown option '{}'".format(typed))
    else:
        raise UsageError("unknown command '{}'".format(typed))
    args.words = tuple(words)
    _check_flag_values(args)
    return args


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def _channel_help(os_name: str) -> Tuple[str, str]:
    if os_name == "windows":
        return ("winget, scoop, choco, npm, uv, vendor, default", "[newest|keep|winget|scoop|choco]")
    return ("pacman, apt, dnf, flatpak, snap, brew, npm, uv, vendor, default",
            "[newest|keep|system|MANAGER]")


def help_text(os_name: str) -> str:
    """The text of ``aiup help`` for this OS."""
    picks, policy = _channel_help(os_name)
    trash = "Recycle Bin" if os_name == "windows" else "Trash"
    schedule = "Task Scheduler entry" if os_name == "windows" else "systemd timer or cron job"
    aur = ("  aiup settings aur review|trust    AUR updates: show the build script and prompts (default),\n"
           "                                 or trust updates of AUR packages already installed\n"
           if os_name == "linux" else "")
    system_cmd = ("winget upgrade --all, and choco upgrade all in an elevated terminal"
                  if os_name == "windows" else "the full upgrade for this distro's package manager")
    approval = ("Windows shows its own approval prompt when an installer needs one"
                if os_name == "windows" else "sudo asks for your password on screen when it needs it")
    return """aiup {version} · keeps the AI and developer tools on this computer current

Everyday:
  aiup                     Update installed catalog tools and other packages (also: full, core)
  aiup list                Interactive catalog: browse, install, update, remove, docs (press ? for keys)
  aiup check [tools...]    Compare installed and latest versions, with what's new; changes nothing
  aiup plan                Preview what a run would do, with release notes for each update
  aiup only <tools...>     Update (or install, where supported) just these tools
  aiup install             Pick catalog tools to install
  aiup remove [tools...]   Pick installed tools to uninstall, or name them
  aiup system              Run {system_cmd}, after asking

After a run:
  aiup attention           Problems and next steps in one place
  aiup resume              Retry pending, deferred, cancelled or failed tools (newest saved result per tool); never installs
  aiup retry               Retry failed, deferred or cancelled tools; may install a missing one
  aiup history [tool]      Recent update results
  aiup logs [tool]         The latest run log, optionally just one tool's part (in a pager)
  aiup cleanup history     Cleaned records from retained run history

Understand a tool:
  aiup explain <tool>      Detection, channel, location, version and next action
  aiup preview <tool>      The picker preview (name, category, versions, docs URL)
  aiup docs <tool>         Open the official repository or website (--print prints the URL)
  aiup owners              Installation ownership and update guidance
  aiup duplicates          Active commands and other copies (review only)
  aiup doctor [--details]  Setup checks and installation conflicts; --details keeps the full inventory
  aiup coverage            Managed coverage and detected-only gaps
  aiup welcome             Friendly guide

Preferences:
  aiup preferences         Show exclusions, holds and named groups
  aiup exclude|include TOOL      Exclude or restore a catalog tool
  aiup hold TOOL YYYY-MM-DD      Hold through a date (inclusive)
  aiup unhold TOOL               Remove a hold
  aiup group set NAME TOOLS...   Save a named group
  aiup group check|run NAME      Check or update a group's installed members
  aiup group remove NAME         Remove a group
  aiup settings system report|ask|auto  System package updates in a plain run: list them only,
                                 ask first (default), or run them without asking
{aur}  aiup settings cleanup auto|review  Stored so exports stay portable; no effect here
  aiup channel [TOOL [CHANNEL]]  Tools with more than one install channel, each channel's
                                 latest version, or pick one: {picks}
  aiup channel --policy {policy}  Where tools without a pick install from: the
                                 newest channel, where each is now, or one manager

Other computers and schedules:
  aiup export [FILE]       Save your tools, other packages and preferences as JSON
  aiup import FILE         Show what an export adds here, ask, then install it
  aiup notify [--always]   Check, then show a desktop notification when updates are ready.
                           It schedules nothing; run it from your own {schedule}
                           (github.com/travisjneuman/aiup, docs/notify.md)

Lists and data:
  aiup list --plain        Print the categorized table plus local detections
  aiup list --category CAT Focus the list on one category (or packages, packages/MANAGER, detected)
  aiup list --view MODE    overview, installed, managed, detected or available rows
  aiup list --sort MODE    Order rows by id (default) or label within each category
  aiup inventory           Every locally detected app/CLI/package as JSON (--plain: a table)
  aiup inventory --refresh Rebuild the local inventory cache now
  aiup catalog             The catalog definition as JSON (--markdown; --platform linux|windows|all)
  aiup project DIRECTORY   Inspect a project's declared npm dependencies (read-only)
  aiup --timings check     Show discovery and provider timings
  aiup version             Print the aiup version
  aiup help                Show this help

Options:
  --dry-run                Print actions without executing them
  --json                   With a run or aiup check: print the results as JSON on stdout
  --verbose                Stream updater output as well as the final report; longer list legends
  --show-unchanged         Include unchanged tools in the final report
  --force                  Run npm, uv and package-manager updates even when versions are current
  --no-install             Do not install missing tools; fails if required fzf is absent
  --plain                  Disable colors; keep readable status words
  --refresh                Rebuild the local inventory; with check, ask every release source again
  --heartbeat-seconds N    Override the heartbeat interval for this run
  --category CAT           Limit aiup list to one category
  --view MODE              Limit list rows: overview, installed, managed, detected, available
  --sort MODE              Order list rows by id (default) or label within each category

Exit status: 0 done, 1 something failed, 2 a mistyped command, 130 stopped
with Ctrl-C.

Settings (environment variables, set to 0 to turn off):
  AIUP_CLEANUP_CACHES      Remove user-level download caches after a run
  AIUP_PARALLEL            Update npm, uv and other user-level tools beside the main run
  AIUP_RELEASE_NOTES       Look up what's new for aiup check and aiup plan
  AIUP_NPM_PROVENANCE_CHECK  Ask before an npm release that lost its provenance record
  AIUP_NO_PAGER=1          Print aiup logs without a pager

Scans are local (PATH, package managers, installed apps); nothing about this
computer is uploaded. Update runs are unattended: updaters receive no terminal
input. System package steps follow aiup settings system, and {approval};
aiup never stores a password. aiup remove moves known user data to the {trash}.
Runs keep required infrastructure (currently fzf) current, then update
installed tools; missing tools are added only by `aiup install` or
`aiup only <tool>`.

aiup on Linux and Windows needs Python 3.9 or newer and fzf. The public
launcher runs the published release, downloads a new one only when it is
published, and runs the last validated release when offline.
""".format(version=AIUP_VERSION, system_cmd=system_cmd, aur=aur, picks=picks, policy=policy,
           schedule=schedule, approval=approval, trash=trash)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _refuse_root(args: Args) -> None:
    """Section 7.1: no runs as root on Linux unless AIUP_ALLOW_ROOT=1."""
    if args.os_name != "linux" or args.command in _LIGHT:
        return
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0:
        return
    if args.config is not None and args.config.allow_root:
        return
    raise AiupError("aiup does not run as root. Run it as your own user, "
                    "or set AIUP_ALLOW_ROOT=1 inside a container")


def _refuse_darwin(args: Args) -> None:
    if args.os_name == "darwin" and args.command not in _LIGHT:
        raise AiupError("on macOS, use the macOS aiup; this runtime only exports the catalog there")


def _shown_name(args: Args) -> str:
    """The command as typed, for messages: "update" for a bare aiup."""
    return args.invoked or "update"


def _context(args: Args, catalog: "Catalog") -> "Context":
    try:
        from aiup.engine.context import create_context
    except ModuleNotFoundError as exc:
        if exc.name in ("aiup.engine", "aiup.engine.context"):
            raise NotImplementedOnSystem(_shown_name(args)) from exc
        raise
    return create_context(args, catalog)


def _dispatch(args: Args) -> int:
    run = commands.load(args.command)
    if run is None:
        raise NotImplementedOnSystem(_shown_name(args))
    catalog = args.catalog
    if catalog is None:
        raise AiupError("the catalog did not load")
    ctx: Optional["Context"] = None
    if args.command != "catalog" and not args.command.startswith("__"):
        ctx = _context(args, catalog)
    return int(run(args, ctx))


def _open_json_stream(args: Args) -> Optional[int]:
    """Keep the real stdout for JSON and send fd 1 to stderr. Returns the saved fd."""
    if not args.json or args.command in _JSON_FORMATS:
        return None
    sys.stdout.flush()
    saved = os.dup(1)
    os.dup2(2, 1)
    args.json_stream = os.fdopen(os.dup(saved), "w", encoding="utf-8")
    return saved


def _close_json_stream(args: Args, saved: Optional[int]) -> None:
    if saved is None:
        return
    try:
        if args.json_stream is not None:
            args.json_stream.close()
        sys.stdout.flush()
    finally:
        os.dup2(saved, 1)
        os.close(saved)


def _load_catalog(args: Args) -> "Catalog":
    from aiup.catalog import load

    catalog = load()
    # The Markdown export prints the notice itself; everything else says it once here.
    embedded = args.command == "catalog" and args.catalog_format == "markdown"
    if catalog.notice and not embedded:
        sys.stderr.write("aiup: " + catalog.notice + "\n")
    return catalog


def run_args(args: Args) -> int:
    """Run a parsed command line and return its exit status."""
    if args.command == "help":
        sys.stdout.write(help_text(args.os_name))
        return EXIT_OK
    if args.command == "version":
        sys.stdout.write(AIUP_VERSION + "\n")
        return EXIT_OK
    if args.plain:
        os.environ["NO_COLOR"] = "1"
    config = load_config()
    if args.heartbeat_seconds is not None:
        config = replace(config, heartbeat_seconds=args.heartbeat_seconds)
    if args.timings:
        config = replace(config, profile=True)
    elif config.profile:
        args.timings = True
    args.config = config
    _refuse_darwin(args)
    _refuse_root(args)
    args.catalog = _load_catalog(args)
    check_category(args, args.catalog)
    saved = _open_json_stream(args)
    try:
        return _dispatch(args)
    finally:
        _close_json_stream(args, saved)


def _quiet_broken_pipe() -> int:
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError):
        pass
    return EXIT_FAILED


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point: parse, run, and turn errors into one line and an exit status."""
    words = list(sys.argv[1:] if argv is None else argv)
    _enable_terminal()
    try:
        args = parse(words)
        status = run_args(args)
        sys.stdout.flush()
        return status
    except KeyboardInterrupt:
        sys.stderr.write("\naiup: stopped\n")
        return EXIT_INTERRUPTED
    except BrokenPipeError:
        return _quiet_broken_pipe()
    except AiupError as exc:
        sys.stderr.write(exc.render() + "\n")
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001  the last stop before a raw traceback
        return _unexpected(exc, words)


def _enable_terminal() -> None:
    """Turn on VT colors and UTF-8 output once; a failure leaves the console as it was."""
    try:
        from aiup.platform import proc, term

        term.enable()
        proc.install_interrupt_handlers()  # Windows Ctrl-Break ends with exit 130 too
    except Exception:  # noqa: BLE001  plain output still works without it
        pass


def _unexpected(exc: Exception, words: Sequence[str]) -> int:
    """One line on stderr for a bug; the traceback only with AIUP_DEBUG=1 or --verbose."""
    try:
        message = " ".join(str(exc).split())[:300]
    except Exception:  # noqa: BLE001  an exception whose str() fails still gets its type named
        message = ""
    line = "aiup: unexpected error: " + type(exc).__name__ + (": " + message if message else "")
    details = os.environ.get("AIUP_DEBUG") == "1" or "--verbose" in words
    report = "aiup: please report it at " + ISSUES_URL
    try:
        if details:
            import traceback

            traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
        else:
            report += " (run it again with AIUP_DEBUG=1 for the details)"
        sys.stderr.write(line + "\n" + report + "\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass
    return EXIT_FAILED
