"""Support for ``python -m aiup`` from the runtime folder."""

from __future__ import annotations

import sys

from aiup.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
