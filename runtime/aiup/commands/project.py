"""aiup project DIRECTORY (macOS: cmd_project).

Lists the dependency ranges a package.json declares. Runs no scripts,
changes no packages and scans no repositories.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from aiup.commands import _common
from aiup.errors import EXIT_OK, AiupError

if TYPE_CHECKING:
    from aiup.cli import Args
    from aiup.engine.context import Context

SECTIONS = ("dependencies", "devDependencies", "peerDependencies")
SIZE_LIMIT = 1048576


def run(args: "Args", ctx: Optional["Context"]) -> int:
    """Print the declared dependencies of one project."""
    try:
        root = Path(args.words[0]).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise AiupError("Cannot inspect package.json: " + str(exc)) from exc
    path = root / "package.json"
    try:
        usable = path.is_file() and path.stat().st_size <= SIZE_LIMIT
    except OSError:
        usable = False
    if not usable:
        raise AiupError("Provide a project directory with a package.json under 1 MiB")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.loads(handle.read(SIZE_LIMIT + 1))
        if not isinstance(data, dict) or any(not isinstance(data.get(key, {}), dict) for key in SECTIONS):
            raise ValueError("Invalid dependency sections")
    except (ValueError, OSError) as exc:
        raise AiupError("Cannot inspect package.json: " + str(exc)) from exc
    lines: List[str] = ["aiup · project dependencies", _common.clean(root), ""]
    for section in SECTIONS:
        for name, value in sorted(data.get(section, {}).items()):
            lines.append("{:18} {:36} {}".format(section, _common.clean(name), _common.clean(value)))
    lines.append("")
    lines.append("Declared version ranges only. No scripts executed, packages changed, or repositories scanned.")
    out = _common.stdout()
    out.write("\n".join(lines) + "\n")
    out.flush()
    return EXIT_OK
