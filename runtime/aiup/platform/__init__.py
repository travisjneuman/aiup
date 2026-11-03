"""Operating-system layer: one ``Platform`` object per run (section 9).

``current()`` picks the implementation for this computer and caches it.
Platform modules load lazily, so importing ``aiup.platform.proc`` or
``aiup.platform.term`` never imports ctypes code for another system.
"""

from __future__ import annotations

import sys
import threading
from typing import Optional

from aiup.platform.base import DistroInfo, Platform, TrashError

__all__ = ["DistroInfo", "Platform", "TrashError", "current", "platform_name"]

_LOCK = threading.Lock()
_CURRENT: Optional[Platform] = None


def platform_name(system: Optional[str] = None) -> str:
    """``"linux"``, ``"windows"`` or ``"darwin"`` for ``sys.platform``; ``""`` otherwise."""
    value = sys.platform if system is None else system
    if value == "win32":
        return "windows"
    if value == "darwin":
        return "darwin"
    if value.startswith("linux"):
        return "linux"
    return ""


def current() -> Platform:
    """The ``Platform`` for this computer. Raises ``AiupError`` on other systems."""
    global _CURRENT
    if _CURRENT is not None:
        return _CURRENT
    with _LOCK:
        if _CURRENT is None:
            _CURRENT = _create(platform_name())
        return _CURRENT


def _create(name: str) -> Platform:
    if name == "linux":
        from aiup.platform.linux import LinuxPlatform

        return LinuxPlatform()
    if name == "windows":
        from aiup.platform.windows import WindowsPlatform

        return WindowsPlatform()
    if name == "darwin":
        from aiup.platform.darwin import DarwinPlatform

        return DarwinPlatform()
    from aiup.errors import AiupError

    raise AiupError("this runtime supports Linux and Windows; " + sys.platform + " is not one of them")
