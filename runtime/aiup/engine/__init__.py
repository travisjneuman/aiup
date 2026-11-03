"""The engine: runs what providers describe (design doc sections 6 to 9).

Providers return :class:`aiup.model.Action` objects. The engine decides the
channel, checks privilege, runs each step with progress and logging, handles
Ctrl-C, records results, and writes the report and run history.

Modules:

- ``context``: the :class:`Context` passed to providers.
- ``host``: the one place that calls the platform layer and the provider registry.
- ``cache``: atomic writes and TTL caches.
- ``net``: bounded HTTPS reads and downloads.
- ``prefs``: preferences.json, channels.tsv, settings.
- ``channels``: channel resolution and policy (section 6.5), and the short
  per-tool hook table (section 6.6).
- ``latest``: newest-version reads and their cache.
- ``privilege``: sudo and Windows approval rules (section 7).
- ``plan``: turns tools into plan items.
- ``run``: update runs, ``aiup system`` and named removal.
- ``execute``: runs one tool's steps (on_fail chains, downloads, deferrals).
- ``lanes``: parallel lanes for user-level managers.
- ``report``: the results table and the JSON documents.
- ``history``: saved runs, logs, retry and resume.
- ``check``: aiup check, and the check data aiup plan and notify read.
- ``releasenotes``: "What's new" lookups.
- ``cleanup``: user-level cache cleanup after runs.
"""

from __future__ import annotations
