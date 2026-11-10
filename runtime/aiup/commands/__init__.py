"""Which module runs each command (design doc section 2.1).

Every command module exposes ``run(args, ctx) -> int``. Modules load only when
their command runs, so a module that is not written yet costs nothing until
someone calls it, and then :func:`load` returns None and the CLI prints
"isn't implemented on this system yet".
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Callable, Dict, Optional

# Canonical command name -> module under aiup.commands. The CLI turns aliases
# (uninstall, home, open, npm-update, bare aiup) into these names first.
COMMAND_MODULES: Dict[str, str] = {
    "update": "update",          # aiup, full, core, only, resume, retry, npm-update, group run
    "check": "check",            # check, group check
    "plan": "plan",
    "list": "listing",
    "install": "listing",
    "preview": "listing",
    "remove": "remove",          # remove, uninstall
    "explain": "explain",
    "doctor": "doctor",
    "attention": "overview",
    "owners": "overview",
    "duplicates": "overview",
    "coverage": "coverage",
    "welcome": "welcome",
    "preferences": "prefs_cmds",
    "exclude": "prefs_cmds",
    "include": "prefs_cmds",
    "hold": "prefs_cmds",
    "unhold": "prefs_cmds",
    "group": "prefs_cmds",       # group set, group remove
    "settings": "prefs_cmds",
    "channel": "channel",
    "system": "system",
    "export": "exportimport",
    "import": "exportimport",
    "notify": "notify",
    "docs": "docs",              # docs, home, open
    "history": "history_cmds",
    "logs": "history_cmds",
    "cleanup": "history_cmds",   # cleanup history only
    "inventory": "inventory_cmd",
    "catalog": "catalog_cmd",
    "project": "project",
    "fleet": "fleet",            # list, add, remove, discover, and runs on every computer
}

# Internal fzf binding commands (__fzf-rows, __cat-*, ...) go to the TUI helper.
INTERNAL_MODULE = "aiup.tui.fast"

CommandRun = Callable[..., int]


def module_name(command: str) -> Optional[str]:
    """The full module name for a canonical command, or None when unknown."""
    if command.startswith("__"):
        return INTERNAL_MODULE
    short = COMMAND_MODULES.get(command)
    return "aiup.commands." + short if short else None


def _import(name: str) -> Optional[ModuleType]:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        # Only "this module does not exist" means not implemented. A missing
        # import inside an existing module is a real bug and is raised.
        if exc.name and (name == exc.name or name.startswith(exc.name + ".")):
            return None
        raise


def load(command: str) -> Optional[CommandRun]:
    """The ``run`` function for a command, or None when its module is not written yet."""
    name = module_name(command)
    if name is None:
        return None
    module = _import(name)
    if module is None:
        return None
    run = getattr(module, "run", None)
    if not callable(run):
        return None
    found: CommandRun = run
    return found
