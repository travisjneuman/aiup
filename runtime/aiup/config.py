"""Environment variables and their clamps (design doc section 2.4 and 9.1).

Defaults and limits match the top of macos/aiup. A value that is not a whole
number falls back to its default, as the Bash ``case`` checks do there. One
difference: macOS resets the whole cache group when any one of its values is
bad; here only the bad value falls back.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

DEFAULT_REPO_RAW = "https://raw.githubusercontent.com/travisjneuman/aiup"
PROVIDER_MAX_BYTES = 1048576


def _int_env(env: Mapping[str, str], name: str, default: int) -> int:
    """A whole number from the environment, or the default when unset or bad."""
    raw = env.get(name, "")
    if not raw or not raw.isdigit() or not raw.isascii():
        return default
    return int(raw)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _on(env: Mapping[str, str], name: str) -> bool:
    """A setting that is on unless set to exactly 0 (AIUP_PARALLEL and friends)."""
    return env.get(name, "1") != "0"


def _flag(env: Mapping[str, str], name: str) -> bool:
    """A setting that is off unless set to exactly 1 (AIUP_PROFILE and friends)."""
    return env.get(name, "0") == "1"


def log_limit(env: Mapping[str, str]) -> int:
    """Runs to keep: 1 to 100, default 20; anything else means 20."""
    value = _int_env(env, "AIUP_LOG_LIMIT", 20)
    return value if 1 <= value <= 100 else 20


def check_worker_count(env: Mapping[str, str], cpu_count: Optional[int] = None) -> int:
    """Read workers for installed-version reads: half the CPUs, from 2 to 6.

    ``AIUP_CHECK_WORKERS`` overrides the CPU-based number but is still clamped
    (macOS ``check_worker_count``).
    """
    raw = env.get("AIUP_CHECK_WORKERS", "")
    if raw.isdigit() and raw.isascii():
        workers = int(raw)
    else:
        cpus = cpu_count if cpu_count is not None else (os.cpu_count() or 4)
        workers = cpus // 2
    return _clamp(workers, 2, 6)


@dataclass(frozen=True)
class Config:
    """Every environment setting the runtime reads, already validated."""

    no_color: bool
    heartbeat_seconds: int
    log_limit: int
    check_workers: int
    inventory_cache_ttl: int
    tui_cache_ttl: int
    tui_session_ttl: int
    available_version_cache_ttl: int
    available_version_failure_ttl: int
    available_version_provider_timeout: int
    available_version_cache_limit: int
    run_provider_timeout: int
    tui_prefetch_workers: int
    provider_max_bytes: int
    parallel: bool
    release_notes: bool
    npm_provenance_check: bool
    brew_attestations: bool
    cleanup_caches: bool
    no_pager: bool
    profile: bool
    allow_root: bool
    ascii: bool
    no_modify_path: bool
    state_dir: str
    local_bin: str
    npm_prefix: str
    source_path: str
    python: str
    launcher_path: str
    catalog_dir: str
    active_generation: str
    repo_raw: str
    release_url: str


def load_config(env: Optional[Mapping[str, str]] = None) -> Config:
    """Read the environment (``os.environ`` by default) into a :class:`Config`."""
    source: Mapping[str, str] = os.environ if env is None else env
    repo_raw = source.get("AIUP_REPO_RAW", "") or DEFAULT_REPO_RAW
    heartbeat = _int_env(source, "AIUP_HEARTBEAT_SECONDS", 5)
    return Config(
        no_color=bool(source.get("NO_COLOR", "")),
        heartbeat_seconds=heartbeat if heartbeat >= 1 else 5,
        log_limit=log_limit(source),
        check_workers=check_worker_count(source),
        inventory_cache_ttl=_int_env(source, "AIUP_INVENTORY_CACHE_TTL", 300),
        tui_cache_ttl=_int_env(source, "AIUP_TUI_CACHE_TTL", 300),
        tui_session_ttl=_int_env(source, "AIUP_TUI_SESSION_TTL", 86400),
        available_version_cache_ttl=_int_env(source, "AIUP_AVAILABLE_VERSION_CACHE_TTL", 900),
        available_version_failure_ttl=_int_env(source, "AIUP_AVAILABLE_VERSION_FAILURE_TTL", 60),
        available_version_provider_timeout=_int_env(source, "AIUP_AVAILABLE_VERSION_PROVIDER_TIMEOUT", 5),
        available_version_cache_limit=_int_env(source, "AIUP_AVAILABLE_VERSION_CACHE_LIMIT", 512),
        run_provider_timeout=_int_env(source, "AIUP_RUN_PROVIDER_TIMEOUT", 60),
        tui_prefetch_workers=_clamp(_int_env(source, "AIUP_TUI_PREFETCH_WORKERS", 2), 2, 3),
        provider_max_bytes=PROVIDER_MAX_BYTES,
        parallel=_on(source, "AIUP_PARALLEL"),
        release_notes=_on(source, "AIUP_RELEASE_NOTES"),
        npm_provenance_check=_on(source, "AIUP_NPM_PROVENANCE_CHECK"),
        brew_attestations=_on(source, "AIUP_BREW_ATTESTATIONS"),
        cleanup_caches=_on(source, "AIUP_CLEANUP_CACHES"),
        # macOS pages only when AIUP_NO_PAGER is unset or exactly 0.
        no_pager=source.get("AIUP_NO_PAGER", "0") != "0",
        profile=_flag(source, "AIUP_PROFILE"),
        allow_root=_flag(source, "AIUP_ALLOW_ROOT"),
        ascii=_flag(source, "AIUP_ASCII"),
        no_modify_path=_flag(source, "AIUP_NO_MODIFY_PATH"),
        state_dir=source.get("AIUP_STATE_DIR", ""),
        local_bin=source.get("AIUP_LOCAL_BIN", ""),
        npm_prefix=source.get("AIUP_NPM_PREFIX", ""),
        source_path=source.get("AIUP_SOURCE_PATH", ""),
        python=source.get("AIUP_PYTHON", ""),
        launcher_path=source.get("AIUP_LAUNCHER_PATH", ""),
        catalog_dir=source.get("AIUP_CATALOG_DIR", ""),
        active_generation=source.get("AIUP_ACTIVE_GENERATION", ""),
        repo_raw=repo_raw,
        release_url=source.get("AIUP_RELEASE_URL", "") or repo_raw + "/main/macos/release",
    )
