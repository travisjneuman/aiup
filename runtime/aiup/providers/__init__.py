"""The provider registry: ``get(name)`` and ``all_providers()``.

Provider modules load on first use, so a run that never touches a channel
never imports it, and a module that is missing or broken affects only its own
channel. ``load_errors()`` lists those for ``aiup doctor``.

How a module offers its provider, checked in this order:

1. a module-level ``PROVIDER`` instance;
2. a module-level ``PROVIDERS`` sequence of instances (one module, several channels);
3. a :class:`Provider` subclass defined in that module whose ``name`` is the
   channel, built with no arguments.
"""

from __future__ import annotations

import importlib
import inspect
import threading
from types import ModuleType
from typing import Dict, List, Optional, Tuple

from aiup.providers.base import Provider

# Channel name -> module under aiup.providers (section 3.1 and 6.3).
CHANNEL_MODULES: Dict[str, str] = {
    "pacman": "linux_pacman",
    "aur": "linux_aur",
    "apt": "linux_apt",
    "dnf": "linux_dnf",
    "zypper": "linux_zypper",
    "flatpak": "linux_flatpak",
    "snap": "linux_snap",
    "nix": "linux_nix",
    "brew": "brew",
    "winget": "win_winget",
    "scoop": "win_scoop",
    "choco": "win_choco",
    "appx": "win_appx",
    "npm": "npm",
    "pnpm": "pnpm",
    "bun": "bun",
    "uv": "uv",
    "pipx": "pipx",
    "cargo": "cargo",
    "go": "go",
    "vendor": "vendor",
    "script": "script",
}

_LOCK = threading.RLock()
_CACHE: Dict[str, Provider] = {}
_ERRORS: Dict[str, str] = {}


def _from_module(module: ModuleType, channel: str) -> Optional[Provider]:
    single = getattr(module, "PROVIDER", None)
    if isinstance(single, Provider) and single.name == channel:
        return single
    for item in getattr(module, "PROVIDERS", ()) or ():
        if isinstance(item, Provider) and item.name == channel:
            return item
    for _, cls in inspect.getmembers(module, inspect.isclass):
        if (issubclass(cls, Provider) and cls is not Provider
                and cls.__module__ == module.__name__ and cls.name == channel):
            return cls()
    return None


def _load(channel: str) -> Optional[Provider]:
    module_name = CHANNEL_MODULES.get(channel)
    if module_name is None:
        return None
    try:
        module = importlib.import_module("aiup.providers." + module_name)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing in ("aiup.providers." + module_name, "aiup.providers"):
            _ERRORS[channel] = "not part of this runtime yet"
        else:
            _ERRORS[channel] = "could not load: {}".format(exc)
        return None
    except Exception as exc:  # a broken module must not take down other channels
        _ERRORS[channel] = "could not load: {}: {}".format(type(exc).__name__, exc)
        return None
    provider = _from_module(module, channel)
    if provider is None:
        _ERRORS[channel] = "module {} has no provider named {}".format(module_name, channel)
    return provider


def get(name: str) -> Optional[Provider]:
    """The provider for a channel name, or None when unknown or not loadable."""
    with _LOCK:
        if name in _CACHE:
            return _CACHE[name]
        if name in _ERRORS:
            return None
        provider = _load(name)
        if provider is not None:
            _CACHE[name] = provider
        return provider


def all_providers(os_name: Optional[str] = None) -> Tuple[Provider, ...]:
    """Every loadable provider, in registry order; only those for ``os_name`` when given."""
    found: List[Provider] = []
    for channel in CHANNEL_MODULES:
        provider = get(channel)
        if provider is None:
            continue
        if os_name is None or provider.supports(os_name):
            found.append(provider)
    return tuple(found)


def load_errors() -> Dict[str, str]:
    """Channels that could not be loaded, with the reason (for aiup doctor)."""
    with _LOCK:
        return dict(_ERRORS)


__all__ = ["CHANNEL_MODULES", "Provider", "all_providers", "get", "load_errors"]
