"""The interactive picker behind ``aiup list`` and ``aiup install``.

Modules:

- ``rows``: row, header and meter formatting, glyph sets, width-safe text.
- ``preview``: preview lines and ``aiup preview TOOL`` text.
- ``session``: the session folder, saved UI state and snapshot cache.
- ``picker``: finds fzf (0.73.0 or newer), builds its command line, runs it,
  and reads available versions in the background.
- ``fast``: the stdlib-only helper fzf runs for each key and keystroke.

Nothing is imported here, so starting the fast helper stays cheap and the
modules can import each other in any order.
"""

from __future__ import annotations
