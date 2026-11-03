"""Detection sources, their registry, and the parallel scan (design 8.3, 9.1).

A source reads one kind of evidence (PATH commands, desktop entries, the
Windows Uninstall keys, ...) and returns :class:`InventoryItem` rows. Package
manager inventories are not sources; they come from ``Provider.inventory()``.

Rules every source follows (research section 2 and 13.2):

- no network, no privilege, no prompt, and never run an unfamiliar program;
- ``available()`` is a cheap probe: an absent source costs under a millisecond;
- ``fingerprint()`` is a cheap stamp (file times, registry key times). Rows are
  cached per source under ``<cache>/inventory/<name>.json`` and reused while the
  fingerprint matches and the rows are younger than ``inventory_cache_ttl``.
  ``--refresh`` (``ctx.refresh``) skips the cache.

The first ``scan()`` call for a cost class ("cheap" or "slow") reads every
available source of that class at once, eight at a time, and remembers the
result for the rest of the process. Callers that loop over sources one by one
(``commands/listing.py``) still get one parallel pass. A source that is not
done after the soft timeout (1.5 s) answers with its last cached rows, marked
stale; one with no cache gets until the hard timeout (3 s). Late results still
land in the cache for the next run.
"""

from __future__ import annotations

import importlib
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from aiup.detect.items import SCHEMA, InventoryItem, item_from_json, item_to_json
from aiup.engine.cache import atomic_write_json, read_json
from aiup.errors import AiupError

if TYPE_CHECKING:
    from aiup.engine.context import Context

COSTS = ("cheap", "slow")
WORKERS = 8
SOFT_TIMEOUT = 1.5
HARD_TIMEOUT = 3.0
CACHE_MAX_BYTES = 4 * 1024 * 1024

# Modules that register the built-in sources when imported.
BUILTIN_MODULES = (
    "aiup.detect.pathscan",
    "aiup.detect.desktop",
    "aiup.detect.registry",
    "aiup.detect.startmenu",
    "aiup.detect.extras",
    "aiup.detect.ondemand",
)


class DetectionSource:
    """One kind of evidence. Subclasses set the attributes and implement ``read``."""

    name: str = ""
    oses: FrozenSet[str] = frozenset()
    cost: str = "cheap"        # "cheap" | "slow": slow sources run after the picker opens

    def available(self, ctx: "Context") -> bool:
        """True on a matching OS when :meth:`probe` finds the source's folder or file."""
        return ctx.os_name in self.oses and self.probe(ctx)

    def probe(self, ctx: "Context") -> bool:
        """A sub-millisecond check that there is anything to read."""
        return True

    def fingerprint(self, ctx: "Context") -> str:
        """A cheap stamp; rows cached under the same stamp are reused (TTL bound)."""
        return ""

    def read(self, ctx: "Context") -> Iterable[InventoryItem]:
        """Read the source now, without the cache. Runs in a worker thread."""
        raise NotImplementedError

    def scan(self, ctx: "Context") -> Iterable[InventoryItem]:
        """This source's rows from the shared parallel pass (cache aware)."""
        if self in _REGISTRY:
            return run_batch(ctx, self.cost).items.get(self.name, ())
        return collect(ctx, (self,)).items.get(self.name, ())


@dataclass
class Batch:
    """The outcome of one parallel pass."""

    items: Dict[str, Tuple[InventoryItem, ...]] = field(default_factory=dict)
    stale: List[str] = field(default_factory=list)       # served from an old cache
    timed_out: List[str] = field(default_factory=list)   # nothing to show yet
    errors: Dict[str, str] = field(default_factory=dict)
    seconds: Dict[str, float] = field(default_factory=dict)


# ----- registry -------------------------------------------------------------------------

_REGISTRY: List[DetectionSource] = []
_REGISTRY_LOCK = threading.RLock()
_LOADED = False
_LOAD_ERRORS: Dict[str, str] = {}


def register(source: DetectionSource) -> None:
    """Add a source; a later source with the same name replaces the earlier one."""
    if not source.name:
        raise ValueError("a detection source needs a name")
    if source.cost not in COSTS:
        raise ValueError("unknown detection cost: " + source.cost)
    with _REGISTRY_LOCK:
        for index, existing in enumerate(_REGISTRY):
            if existing.name == source.name:
                _REGISTRY[index] = source
                return
        _REGISTRY.append(source)


def _load_builtin() -> None:
    global _LOADED
    with _REGISTRY_LOCK:
        if _LOADED:
            return
        _LOADED = True
        for module in BUILTIN_MODULES:
            try:
                importlib.import_module(module)
            except ImportError as exc:
                _LOAD_ERRORS[module] = str(exc)


def all_sources() -> Tuple[DetectionSource, ...]:
    """Every registered source, built-in ones first, in registration order."""
    _load_builtin()
    with _REGISTRY_LOCK:
        return tuple(_REGISTRY)


def get(name: str) -> Optional[DetectionSource]:
    for source in all_sources():
        if source.name == name:
            return source
    return None


def load_errors() -> Dict[str, str]:
    """Built-in source modules that failed to import, for ``aiup doctor``."""
    _load_builtin()
    with _REGISTRY_LOCK:
        return dict(_LOAD_ERRORS)


# ----- per-source cache -----------------------------------------------------------------


def cache_dir(ctx: "Context") -> Path:
    return Path(ctx.cache.root) / "inventory"


def _cache_path(ctx: "Context", name: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)
    return cache_dir(ctx) / (safe + ".json")


@dataclass(frozen=True)
class Cached:
    fingerprint: str
    at: float
    items: Tuple[InventoryItem, ...]


def load_cached(ctx: "Context", name: str) -> Optional[Cached]:
    data = read_json(_cache_path(ctx, name), CACHE_MAX_BYTES)
    if not isinstance(data, dict) or data.get("v") != SCHEMA:
        return None
    fingerprint = data.get("fingerprint")
    at = data.get("at")
    rows = data.get("items")
    if not isinstance(fingerprint, str) or not isinstance(at, (int, float)) or not isinstance(rows, list):
        return None
    items: List[InventoryItem] = []
    for row in rows:
        item = item_from_json(row)
        if item is not None:
            items.append(item)
    return Cached(fingerprint, float(at), tuple(items))


def store_cached(ctx: "Context", name: str, fingerprint: str, items: Sequence[InventoryItem]) -> None:
    data = {"v": SCHEMA, "fingerprint": fingerprint, "at": time.time(),
            "items": [item_to_json(item) for item in items]}
    try:
        atomic_write_json(_cache_path(ctx, name), data)
    except (OSError, ValueError, AiupError):
        pass


def _fresh(ctx: "Context", cached: Optional[Cached], fingerprint: str) -> bool:
    if cached is None or ctx.refresh:
        return False
    ttl = int(getattr(ctx.config, "inventory_cache_ttl", 300) or 0)
    if ttl <= 0:
        return False
    age = time.time() - cached.at
    return cached.fingerprint == fingerprint and 0 <= age < ttl


# ----- the parallel pass -----------------------------------------------------------------


class _Job:
    def __init__(self, source: DetectionSource, fingerprint: str, cached: Optional[Cached]) -> None:
        self.source = source
        self.fingerprint = fingerprint
        self.cached = cached
        self.done = threading.Event()
        self.items: Tuple[InventoryItem, ...] = ()
        self.error = ""
        self.seconds = 0.0


def _work(ctx: "Context", job: _Job, gate: threading.BoundedSemaphore) -> None:
    started = time.monotonic()
    try:
        with gate:
            started = time.monotonic()
            job.items = tuple(job.source.read(ctx))
        store_cached(ctx, job.source.name, job.fingerprint, job.items)
    except Exception as exc:  # noqa: BLE001 - a thread boundary: one broken source must not stop the scan
        job.error = "{}: {}".format(type(exc).__name__, exc)
    finally:
        job.seconds = time.monotonic() - started
        job.done.set()


def collect(ctx: "Context", sources: Sequence[DetectionSource]) -> Batch:
    """Read ``sources`` in parallel (cache aware), without linking or merging."""
    batch = Batch()
    jobs: List[_Job] = []
    for source in sources:
        try:
            if not source.available(ctx):
                continue
            fingerprint = source.fingerprint(ctx)
        except (OSError, ValueError, NotImplementedError, AiupError) as exc:
            batch.errors[source.name] = str(exc)
            continue
        cached = load_cached(ctx, source.name)
        if cached is not None and _fresh(ctx, cached, fingerprint):
            batch.items[source.name] = cached.items
            continue
        jobs.append(_Job(source, fingerprint, cached))
    if not jobs:
        return batch
    gate = threading.BoundedSemaphore(WORKERS)
    start = time.monotonic()
    for job in jobs:
        # Daemon threads: a stuck read never keeps aiup from exiting.
        thread = threading.Thread(target=_work, args=(ctx, job, gate),
                                  name="aiup-detect-" + job.source.name, daemon=True)
        thread.start()
    for job in jobs:
        name = job.source.name
        job.done.wait(max(0.0, start + SOFT_TIMEOUT - time.monotonic()))
        if not job.done.is_set() and job.cached is not None and job.cached.items:
            batch.items[name] = tuple(replace(item, stale=True) for item in job.cached.items)
            batch.stale.append(name)
            continue
        job.done.wait(max(0.0, start + HARD_TIMEOUT - time.monotonic()))
        if not job.done.is_set():
            batch.timed_out.append(name)
            if job.cached is not None:
                batch.items[name] = tuple(replace(item, stale=True) for item in job.cached.items)
            continue
        batch.seconds[name] = job.seconds
        if job.error:
            batch.errors[name] = job.error
            _log(ctx, "detect: " + name + " failed: " + job.error)
            if job.cached is not None:
                batch.items[name] = tuple(replace(item, stale=True) for item in job.cached.items)
                batch.stale.append(name)
            continue
        batch.items[name] = job.items
    return batch


def _log(ctx: "Context", line: str) -> None:
    log = getattr(ctx, "log", None)
    write = getattr(log, "write", None)
    if callable(write):
        try:
            write(line)
        except (OSError, ValueError):
            pass


_BATCH_LOCKS = {cost: threading.Lock() for cost in COSTS}


def run_batch(ctx: "Context", cost: str) -> Batch:
    """Every registered source of one cost class, read once per process and linked."""
    key = "aiup.detect.batch:" + cost
    lock = _BATCH_LOCKS.get(cost)
    if lock is None:
        raise ValueError("unknown detection cost: " + cost)
    with lock:
        done = ctx.cache.recall(key)
        if isinstance(done, Batch):
            return done
        batch = collect(ctx, [s for s in all_sources() if s.cost == cost])
        from aiup.detect import link
        link.link(ctx, batch)
        ctx.cache.remember(key, batch)
        return batch


def forget(ctx: "Context") -> None:
    """Drop this process's remembered passes (after aiup changed something)."""
    for cost in COSTS:
        ctx.cache.remember("aiup.detect.batch:" + cost, None)
    # The Uninstall entry memos (detect.registry) change when an app is removed.
    for key in ("aiup.detect.arp-entries", "aiup.detect.arp-folders"):
        ctx.cache.remember(key, None)
