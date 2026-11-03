"""uv tools (channel ``uv``, design doc section 6.3).

Port of the macOS ``uv-tool`` kind: when ``uv tool list`` has the tool,
``uv tool upgrade PKG``; otherwise ``uv tool install <args>``, with the same
per-tool arguments as macOS ``uv_tool_install_args``. Latest versions come
from PyPI.

Installed versions are read from the tool's own environment
(``<tool dir>/<pkg>/uv-receipt.toml`` plus the ``.dist-info`` folder), so no
``uv`` call is needed for a version check.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Tuple

from aiup.engine.cache import read_text_bounded
from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers.script import (
    ALL_OSES, empty_action, env_of, home, is_windows, path_inside, path_setup_step, read_command,
    real_path, which,
)

if TYPE_CHECKING:
    from aiup.engine.context import Context

# macOS uv_tool_install_args: tools that need a pinned Python or extras.
INSTALL_ARGS: Dict[str, Tuple[str, ...]] = {
    "open-webui": ("--python", "3.12", "open-webui"),
    "markitdown": ("markitdown[all]",),
    "mlx-audio": ("mlx-audio[all]",),
    "rapid-mlx": ("--python", "3.12", "rapid-mlx"),
    "browser-use": ("--python", "3.12", "browser-use"),
    "serena-agent": ("--python", "3.13", "serena-agent"),
}

_RECEIPT_MAX = 256 * 1024
_INSTALL_PATH = re.compile(r'install-path\s*=\s*"([^"]+)"')
_LIST_MAX = 2 * 1024 * 1024


def package_name(target: Target) -> str:
    """The PyPI name without extras: ``markitdown[all]`` -> ``markitdown``."""
    return target.package.split("[", 1)[0]


def normalize(name: str) -> str:
    """PEP 503 style name as used in ``.dist-info`` folders (``A.b-c`` -> ``a_b_c``)."""
    return re.sub(r"[-_.]+", "_", name).lower()


def env_name(name: str) -> str:
    """The folder uv gives a tool environment: the normalized name (``Foo_Bar`` -> ``foo-bar``)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def tool_dir(ctx: "Context") -> Path:
    """``UV_TOOL_DIR``, else uv's default tool folder for this OS."""
    env = env_of(ctx)
    value = env.get("UV_TOOL_DIR", "")
    if value and os.path.isabs(value):
        return Path(value)
    if is_windows(ctx):
        from aiup.paths import roaming_appdata

        return roaming_appdata(env) / "uv" / "tools"
    data = env.get("XDG_DATA_HOME", "")
    base = Path(data) if data and os.path.isabs(data) else home(ctx) / ".local" / "share"
    return base / "uv" / "tools"


def bin_dir(ctx: "Context") -> Path:
    """Where uv puts tool commands (``UV_TOOL_BIN_DIR``, else ``~/.local/bin``)."""
    env = env_of(ctx)
    for name in ("UV_TOOL_BIN_DIR", "XDG_BIN_HOME"):
        value = env.get(name, "")
        if value and os.path.isabs(value):
            return Path(value)
    data = env.get("XDG_DATA_HOME", "")
    if data and os.path.isabs(data):
        return Path(data).parent / "bin"
    return home(ctx) / ".local" / "bin"


def _site_packages(env: Path, windows: bool) -> List[Path]:
    if windows:
        return [env / "Lib" / "site-packages"]
    lib = env / "lib"
    if not lib.is_dir():
        return []
    return [entry / "site-packages" for entry in sorted(lib.glob("python*"))]


def env_version(env: Path, name: str, windows: bool) -> str:
    """Version of ``name`` from its ``.dist-info`` folder in a tool environment."""
    wanted = normalize(name)
    for site in _site_packages(env, windows):
        if not site.is_dir():
            continue
        for info in site.glob("*.dist-info"):
            dist, _, version = info.name[: -len(".dist-info")].rpartition("-")
            if dist and normalize(dist) == wanted:
                return version
    return ""


def receipt_paths(env: Path) -> Tuple[str, ...]:
    """Command paths from ``uv-receipt.toml`` (``install-path`` entries)."""
    text = read_text_bounded(env / "uv-receipt.toml", _RECEIPT_MAX) or ""
    return tuple(found.replace("/", os.sep) for found in _INSTALL_PATH.findall(text))


def pypi_latest(ctx: "Context", name: str, timeout: float) -> Latest:
    """The newest release on PyPI."""
    version = ctx.net.pypi_latest(name, timeout)
    return Latest(version, "pypi") if version else Latest("", "pypi", "PyPI did not answer")


def _listed(ctx: "Context", uv: str, name: str) -> bool:
    """True when ``uv tool list`` shows the tool."""
    out = read_command(ctx, (uv, "tool", "list"), max_bytes=_LIST_MAX)
    if out is None:
        return (tool_dir(ctx) / env_name(name) / "uv-receipt.toml").is_file()
    wanted = normalize(name)
    return any(line.split(" ", 1)[0] and normalize(line.split(" ", 1)[0]) == wanted
               for line in out.splitlines() if not line.startswith(("-", " ")))


class UvProvider(Provider):
    """Python command-line tools installed with ``uv tool``."""

    name = "uv"
    oses = ALL_OSES
    scope = "user"
    lane = "python"
    exclusive = False
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        return which(ctx, "uv") is not None

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        name = package_name(target)
        env = tool_dir(ctx) / env_name(name)
        if not (env / "uv-receipt.toml").is_file():
            return None
        found = receipt_paths(env)
        return Installed(env_version(env, name, is_windows(ctx)), found[0] if found else str(env), "user", self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        return pypi_latest(ctx, package_name(target), timeout)

    def install(self, ctx: "Context", target: Target) -> Action:
        return self._install(ctx, target, "install")

    def update(self, ctx: "Context", target: Target) -> Action:
        """``uv tool upgrade PKG`` when uv lists it, else ``uv tool install``."""
        uv = which(ctx, "uv")
        if not uv:
            return empty_action(target, "update", "uv is not on PATH.")
        name = package_name(target)
        if not _listed(ctx, uv, name):
            return self._install(ctx, target, "update")
        step = Step(argv=(uv, "tool", "upgrade", name), label="uv tool upgrade " + name)
        return Action(tool=target.package, op="update", channel=self.name, steps=(step,))

    def remove(self, ctx: "Context", target: Target) -> Action:
        uv = which(ctx, "uv")
        if not uv:
            return empty_action(target, "remove", "uv is not on PATH.")
        name = package_name(target)
        step = Step(argv=(uv, "tool", "uninstall", name), label="uv tool uninstall " + name)
        return Action(tool=target.package, op="remove", channel=self.name, steps=(step,))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        root = tool_dir(ctx)
        resolved = real_path(path)
        if path_inside(resolved, real_path(str(root))):
            relative = Path(os.path.relpath(resolved, real_path(str(root)))).parts
            if relative and relative[0] != ".":
                return Ownership(self.name, relative[0], "exact")
        # Windows (and some Linux setups) copy commands instead of linking them.
        if path_inside(path, str(bin_dir(ctx))) and root.is_dir():
            wanted = os.path.normcase(os.path.normpath(path))
            for env in sorted(root.iterdir()):
                if any(os.path.normcase(os.path.normpath(p)) == wanted for p in receipt_paths(env)):
                    return Ownership(self.name, env.name, "exact")
        return None

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        root = tool_dir(ctx)
        if not root.is_dir():
            return ()
        windows = is_windows(ctx)
        return tuple(
            PackageRecord(self.name, env.name, env_version(env, env.name, windows), "user", True, receipt_paths(env))
            for env in sorted(root.iterdir()) if (env / "uv-receipt.toml").is_file()
        )

    def _install(self, ctx: "Context", target: Target, op: str) -> Action:
        uv = which(ctx, "uv")
        if not uv:
            return empty_action(target, op, "uv is not on PATH.")
        name = package_name(target)
        args = INSTALL_ARGS.get(name, (target.package,))
        steps: List[Step] = [Step(argv=(uv, "tool", "install") + args, label="uv tool install " + " ".join(args))]
        setup = path_setup_step(ctx, str(bin_dir(ctx)))
        if setup is not None:
            steps.append(setup)
        return Action(tool=target.package, op=op, channel=self.name, steps=tuple(steps))
