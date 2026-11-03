#!/usr/bin/env python3
"""Entry script for the aiup runtime.

It puts its own folder first on sys.path, so the ``aiup`` package next to it is
the one that runs, then hands the arguments to :func:`aiup.cli.main`. The
launcher imports ``aiup.cli`` in-process instead; running this file directly is
the development path (``python3 runtime/aiup_main.py version``).
"""

from __future__ import annotations

import sys
from pathlib import Path


def _prepare_path() -> None:
    """Put this file's folder first on sys.path."""
    here = str(Path(__file__).resolve().parent)
    if not sys.path or sys.path[0] != here:
        sys.path.insert(0, here)


def run() -> int:
    """Run aiup with this process's arguments and return its exit status."""
    _prepare_path()
    from aiup.cli import main

    return main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(run())
