"""Available-version reads with the TTL cache (design doc sections 6.2 and 9.1).

``read_latest`` asks a provider for the newest version of one target,
through the 900 second cache (60 seconds for failures). Each provider's bulk
``outdated()`` read runs at most once per process, before per-tool reads
(macOS ``brew_outdated_snapshot_load``).

``classify`` turns an installed version and a latest version into the
``aiup check`` vocabulary: update, current, self-updated, skipped or
unverified. ``Latest.managed`` (another updater owns the copy, such as the
Microsoft Store) is skipped with that note, never an update.
``Latest.pending`` (the manager says an update waits but names no version,
such as flatpak) is an update with an unknown version. Neither is cached, so
the next read gives the same answer.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Dict, Iterable, Mapping, Optional

from aiup.model import Latest, Target
from aiup.versions import scheme_for, version_cmp, version_is_greater

from aiup.engine import host

if TYPE_CHECKING:
    from aiup.engine.context import Context
    from aiup.providers.base import Provider

_BULK_LOCK = threading.Lock()
_PROVIDER_LOCKS: Dict[str, threading.Lock] = {}


def cache_key(tool: str, channel: str) -> str:
    """One cache entry per tool and channel."""
    return channel + "_" + tool


def prefetch_outdated(ctx: "Context", providers: Iterable["Provider"]) -> None:
    """Run each provider's bulk ``outdated()`` once, in parallel."""
    todo = [p for p in providers if ctx.cache.recall("outdated:" + p.name) is None]
    if not todo:
        return
    workers = max(1, min(len(todo), ctx.config.check_workers))
    host.map_threads(workers, lambda provider: _bulk(ctx, provider), todo)


def _provider_lock(name: str) -> threading.Lock:
    with _BULK_LOCK:
        lock = _PROVIDER_LOCKS.get(name)
        if lock is None:
            lock = _PROVIDER_LOCKS[name] = threading.Lock()
        return lock


def _bulk(ctx: "Context", provider: "Provider") -> Mapping[str, Latest]:
    """One provider's bulk read. Threads asking for the same provider wait for the first one."""
    key = "outdated:" + provider.name
    with _provider_lock(provider.name):
        found = ctx.cache.recall(key)
        if isinstance(found, dict):
            return found
        generation = ctx.cache.generation()
        try:
            snapshot: Dict[str, Latest] = dict(provider.outdated(ctx) or {})
        except Exception:  # noqa: BLE001  the bulk read is only a shortcut; per-tool reads still run
            snapshot = {}
        # A read that started before an action changed things is used once, never kept.
        ctx.cache.remember_from(generation, key, snapshot)
        return snapshot


def read_latest(ctx: "Context", provider: "Provider", target: Target, tool: str,
                current: str, during_run: bool = False) -> Latest:
    """The newest version the channel offers, from the cache when it is fresh.

    ``current`` is the installed version; a cached answer counts only for the
    version it was read for. ``--refresh`` skips the cache.
    """
    key = cache_key(tool, target.channel)
    if not ctx.refresh:
        hit = ctx.cache.available.get(key, current)
        if hit is not None:
            if hit.status == "newer":
                return Latest(hit.version, target.channel)
            if hit.status == "current":
                return Latest(current, target.channel)
            return Latest("", target.channel, "no answer from " + target.channel + " a moment ago")
    rows = _bulk(ctx, provider)
    bulk = rows.get(target.package)
    if bulk is None and ctx.os_name == "windows" and rows:
        bulk = _match_windows(rows, target)
    if bulk is not None and (bulk.version or bulk.pending or bulk.managed):
        latest = bulk
    else:
        latest = _ask(ctx, provider, target, during_run)
    _store(ctx, key, current, latest)
    return latest


def _match_windows(rows: Mapping[str, Latest], target: Target) -> Optional[Latest]:
    """A bulk row for ``target`` when the exact key missed.

    Windows package ids are case-insensitive. Scoop keys its rows
    ``bucket/app``, so a catalog cell that names only the app matches the row
    whose app part is that name (Scoop installs an app from one bucket only).
    """
    wanted = target.package.strip().lower()
    if not wanted:
        return None
    bare = target.channel == "scoop" and "/" not in wanted
    for name, row in rows.items():
        key = name.lower()
        if key == wanted or (bare and key.rsplit("/", 1)[-1] == wanted):
            return row
    return None


def _ask(ctx: "Context", provider: "Provider", target: Target, during_run: bool) -> Latest:
    try:
        return provider.latest(ctx, target, ctx.provider_timeout(during_run))
    except NotImplementedError:
        return Latest("", target.channel, target.channel + " cannot read versions yet")
    except Exception as exc:  # noqa: BLE001  a provider bug reads as unverified, never a crash
        return Latest("", target.channel, "could not read: " + (str(exc) or type(exc).__name__)[:120])


def _store(ctx: "Context", key: str, current: str, latest: Latest) -> None:
    if latest.managed or (latest.pending and not latest.version):
        return  # not a version answer; reading it again is cheap and gives the same answer
    if not latest.version:
        ctx.cache.available.put(key, current, "failure", "")
    elif current and version_is_greater(latest.version, current, scheme_for(latest.source)):
        ctx.cache.available.put(key, current, "newer", latest.version)
    elif current:
        ctx.cache.available.put(key, current, "current", "")


def forget(ctx: "Context", tool: str, channel: str) -> None:
    """Drop the cached answer after a tool changed."""
    ctx.cache.available.forget(cache_key(tool, channel))


def classify(installed: str, latest: Optional[Latest]) -> str:
    """update | current | self-updated | skipped | unverified (``aiup check`` results).

    skipped: ``latest.managed`` (show ``latest.managed`` as the note). An
    update with ``latest.pending`` has no version to show.
    """
    if latest is not None and latest.managed:
        return "skipped"
    if latest is not None and latest.pending and not latest.version:
        return "update"
    if latest is None or not latest.version or not installed:
        return "unverified"
    order = version_cmp(installed, latest.version, scheme_for(latest.source))
    if order < 0:
        return "update"
    if order > 0:
        return "self-updated"
    return "current"


def self_updated_note(installed: str, channel: str, latest: str) -> str:
    """The note for a copy that is newer than its channel offers."""
    return ("Current (self-updated): installed {} is newer than {}'s {}; "
            "skipped the update, no downgrade.").format(installed, channel, latest)
