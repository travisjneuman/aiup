"""aiup for Linux and Windows: keeps the AI and developer tools on a computer current.

The entry point is :func:`aiup.cli.main`. The design contract every module codes
against is docs/cross-platform-design.md.
"""

from __future__ import annotations

from aiup.version import AIUP_VERSION

__all__ = ["AIUP_VERSION"]
