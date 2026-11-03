"""The run context every provider and engine function receives (design doc 6.2).

Providers read through ``ctx.run_read(argv, timeout, max_bytes, cwd=, env=)`` and
``ctx.net``; they look at ``ctx.platform``, ``ctx.interactive``,
``ctx.dirs``, ``ctx.distro`` and ``ctx.settings``. Nothing here changes a
tool.

``create_context(args, catalog)`` is what the command line calls;
``build_context`` takes the same choices as keywords.
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence, TextIO, Tuple

from aiup.config import Config, load_config
from aiup.paths import Dirs, dirs_for

from aiup.engine import host
from aiup.engine.cache import Caches
from aiup.engine.net import Net
from aiup.engine.prefs import Settings, read_settings

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.platform.base import DistroInfo, Platform
    from aiup.platform.proc import ReadResult
    from aiup.providers.base import Provider

INTERACTIVE_PROVIDER_TIMEOUT = 5.0


class RunLog:
    """Appends lines to one log file. Thread-safe. A RunLog without a path drops lines."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self._lock = threading.Lock()

    def write(self, line: str) -> None:
        """Append one line. Errors are ignored: a log must never stop a run."""
        if self.path is None:
            return
        with self._lock:
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(str(self.path), flags, 0o600)
                with os.fdopen(fd, "a", encoding="utf-8") as handle:
                    handle.write(line.rstrip("\n") + "\n")
            except OSError:
                pass


@dataclass
class Context:
    """Everything one aiup command knows about this computer and this run."""

    platform: "Platform"
    os_name: str
    dirs: Dirs
    config: Config
    settings: Settings
    net: Net
    cache: Caches
    distro: "DistroInfo"
    env: Mapping[str, str]
    dry_run: bool = False
    interactive: bool = False
    verbose: bool = False
    refresh: bool = False
    force: bool = False
    json_output: bool = False
    log: RunLog = field(default_factory=RunLog)
    out: TextIO = field(default_factory=lambda: sys.stderr)
    json_out: Optional[TextIO] = None   # the real stdout in --json mode (cli keeps it in args.json_stream)
    system_approved: Optional[bool] = None
    confirmed: Dict[str, bool] = field(default_factory=dict)   # a step's own yes/no answers this run
    catalog: Optional["Catalog"] = None
    _available: Dict[str, bool] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ----- reads -------------------------------------------------------------

    def run_read(self, argv: Sequence[str], timeout: Optional[float] = None,
                 max_bytes: Optional[int] = None, cwd: Optional[str] = None,
                 env: Optional[Mapping[str, str]] = None) -> "ReadResult":
        """Run a read-only command: no terminal, stdin closed, output capped.

        ``cwd`` sets the working folder (some tools read a project file
        there); ``env`` adds variables on top of the user's environment.
        """
        limit = self.provider_timeout() if timeout is None else float(timeout)
        cap = self.config.provider_max_bytes if max_bytes is None else int(max_bytes)
        return host.run_read(argv, timeout=limit, max_bytes=cap, env=env, cwd=cwd)

    def provider_timeout(self, during_run: bool = False) -> float:
        """5 seconds for interactive reads, ``AIUP_RUN_PROVIDER_TIMEOUT`` during runs."""
        if during_run:
            return float(self.config.run_provider_timeout)
        return float(self.config.available_version_provider_timeout or INTERACTIVE_PROVIDER_TIMEOUT)

    # ----- providers -----------------------------------------------------------

    def provider(self, name: str) -> Optional["Provider"]:
        """The provider for a channel on this OS, or None."""
        provider = host.get_provider(name)
        if provider is None or not provider.supports(self.os_name):
            return None
        return provider

    def provider_available(self, name: str) -> bool:
        """True when the channel's manager is present here (asked once per process)."""
        with self._lock:
            if name in self._available:
                return self._available[name]
        provider = self.provider(name)
        try:
            ok = provider is not None and bool(provider.available(self))
        except Exception:  # noqa: BLE001  a provider that cannot tell counts as missing
            ok = False
        with self._lock:
            self._available[name] = ok
        return ok

    def providers(self) -> Tuple["Provider", ...]:
        """Every provider for this OS whose manager is present."""
        found: List["Provider"] = []
        for provider in host.all_providers():
            if provider.supports(self.os_name) and self.provider_available(provider.name):
                found.append(provider)
        return tuple(found)

    # ----- output ---------------------------------------------------------------

    def say(self, text: str = "") -> None:
        """Print one line of progress or notes to stderr."""
        try:
            self.out.write(text + "\n")
            self.out.flush()
        except (OSError, ValueError):
            pass


def create_context(args: Any, catalog: Optional["Catalog"] = None) -> Context:
    """The context for one command, from the parsed command line (``cli.Args``).

    Reads ``dry_run``, ``verbose``, ``refresh``, ``force``, ``json``,
    ``json_stream`` and the already loaded ``config``; a missing attribute
    counts as off.
    """
    config = getattr(args, "config", None)
    ctx = build_context(
        dry_run=bool(getattr(args, "dry_run", False)),
        verbose=bool(getattr(args, "verbose", False)),
        refresh=bool(getattr(args, "refresh", False)),
        force=bool(getattr(args, "force", False)),
        json_output=bool(getattr(args, "json", False)),
        config=config if isinstance(config, Config) else None,
    )
    ctx.catalog = catalog
    stream = getattr(args, "json_stream", None)
    if ctx.json_output and stream is not None:
        ctx.json_out = stream
    return ctx


def build_context(*, dry_run: bool = False, verbose: bool = False, refresh: bool = False,
                  force: bool = False, json_output: bool = False,
                  env: Optional[Mapping[str, str]] = None,
                  platform: Optional["Platform"] = None,
                  settings: Optional[Settings] = None,
                  config: Optional[Config] = None) -> Context:
    """Make the context for one command from the environment and this computer."""
    environ: Mapping[str, str] = os.environ if env is None else env
    if config is None:
        config = load_config(environ)
    plat = platform if platform is not None else host.current_platform()
    os_name = host.platform_name(plat)
    dirs = dirs_for(os_name, environ)
    caches = Caches(dirs.cache, config.available_version_cache_ttl,
                    config.available_version_failure_ttl, config.available_version_cache_limit)
    return Context(
        platform=plat,
        os_name=os_name,
        dirs=dirs,
        config=config,
        settings=settings if settings is not None else read_settings(dirs),
        net=Net(),
        cache=caches,
        distro=host.distro(plat),
        env=environ,
        dry_run=dry_run,
        interactive=_has_terminal(),
        verbose=verbose,
        refresh=refresh,
        force=force,
        json_output=json_output,
    )


def _has_terminal() -> bool:
    """stdin and stderr are both terminals (prompts go to stderr)."""
    try:
        return sys.stdin.isatty() and sys.stderr.isatty()
    except (AttributeError, ValueError, OSError):
        return False
