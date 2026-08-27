# TUI performance foundation

Status: implemented in runtime **2026.08.26-02**

## Authority model

The live runtime, paired manifest, filesystem, package metadata, and provider state remain authoritative. The TUI cache and session files are accelerators only and never authorize an install, update, remove, cleanup, or Homebrew adoption.

An authoritative interactive entry performs the normal runtime/environment and catalog validation once, scans or restores a compatible state snapshot, materializes display rows and static preview data, and then creates a private session. Every mutation path invalidates the accelerator and immediately revalidates the exact runtime/manifest plus live provider state before changing anything.

The public launcher still refreshes, validates, version-matches, stages, and atomically activates the runtime/manifest pair on every top-level invocation. Cursor movement, search, resize, category navigation, headers, and previews invoke the exact active runtime directly with the exact paired manifest; they do not reinvoke the launcher or refresh a public generation.

## Cache contract

Disposable cache generations live under `$AIUP_STATE_DIR/cache/v1/generations`. A single atomic pointer selects a complete immutable generation containing catalog, Homebrew, detected-inventory, and version indexes.

Each generation records:

- cache schema, aiup runtime version and hash;
- manifest version and hash;
- creation time and a lightweight source fingerprint;
- the view/filter key and hashes for every snapshot index.

Missing, stale, corrupt, partial, incompatible, wrong-runtime, wrong-manifest, symlinked, or interrupted generations are ignored and rebuilt. Publishing uses a same-filesystem staging directory followed by atomic rename and pointer replacement. Retention removes only older complete, familiar, unreferenced aiup snapshot generations; unfamiliar, partial, hidden staging, or symlinked entries are preserved.

The source fingerprint covers the exact runtime/manifest, PATH identities, fixture identity when testing, and lightweight mtimes for application, Homebrew, npm, and uv roots. A changed fingerprint prevents cache reuse.

## Session contract

Picker sessions live under `$AIUP_STATE_DIR/sessions/<pid>-<random-nonce>` with mode `0700`. A session records the exact runtime, manifest, schema, cache snapshot generation, owner PID, nonce, creation time, view/filter/sort state, content hashes, and a private token. It contains coherent copies of the snapshot indexes plus pre-rendered rows and static preview data.

The internal fast path is limited to fzf display/navigation/documentation helpers. It requires a live owner process, exact directory/name/token, exact runtime and manifest pair, matching view context, regular non-symlink files, and a matching aggregate content hash. Missing or invalid context falls back to authoritative initialization and fails safely when the supplied runtime or manifest is incompatible. Mutation commands are not members of this private dispatcher.

Static preview authority is materialized with the session. Installed/available version text is filled lazily for the selected managed item and then reused within that session, so picker startup does not run every installed command or contact every provider. That mutable version-display index is excluded from mutation authority and from the immutable session-content hash; provider and package state are re-read independently before any action.

Normal exit and `HUP`, `INT`, or `TERM` remove the exact task-owned session. Bounded stale cleanup removes only old, inactive, structurally familiar aiup sessions. Active, malformed, unfamiliar, or symlinked entries are preserved.

## fzf maintenance boundary

Interactive list, install, and remove require fzf. If it is missing, the established Homebrew installation/error behavior remains. If it is already installed, opening a picker does not run `brew update` or `brew upgrade`. Normal aiup updates and `aiup only fzf` continue to maintain fzf.

## Profiling and measurements

`AIUP_PROFILE=1` emits stage timings to stderr without changing normal stdout. Stages cover runtime validation, manifest parsing, Homebrew inventory, detected inventory, catalog-state scan, row generation, preview generation, and picker-ready time.

Measurements were taken on the same Mac on 2026-08-26. Before values are single bounded runs from runtime `2026.08.26-01`; after helper values are five-run medians using the deterministic public capture fixture and a valid session. Plain-list after values are three-run medians. These are performance evidence, not universal hardware guarantees.

| Operation | Before | After |
|---|---:|---:|
| Category preview | 1,889.2 ms | 114.1 ms |
| Warm managed preview | 1,920.9 ms | 148.3 ms |
| `__fzf-header` | 1,871.8 ms | 117.5 ms |
| `__fzf-rows` | 2,036.7 ms | 185.4 ms |
| Managed plain list | 2,470.7 ms | 626.7 ms |
| Full warm-cache plain list, real local inventory | 5,052.3 ms | 914.0 ms |

The regression ceiling is intentionally generous (750 ms for session helpers, 3 seconds for the managed fixture list, and 7 seconds for the full fixture list) to avoid noisy failures. The measured session helpers met the practical sub-250 ms target in the recorded run.

## Deterministic coverage

`scripts/test-aiup-tui-performance` covers valid, missing, stale, corrupt, partial, wrong-version, wrong-manifest-hash, symlinked, concurrently published, and interrupted cache generations; rebuilt-output equivalence; exact runtime/manifest session binding; normal and signal cleanup; preservation of active/unfamiliar/symlinked/malformed state; installed-fzf browsing without update/upgrade; structural fast-path constraints; and non-flaky performance ceilings.
