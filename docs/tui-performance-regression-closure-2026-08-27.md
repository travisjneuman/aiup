# TUI performance and regression closure

Decision: **PASS WITH FIXES**
Audited baseline: `9f283e45e3d7e5225e24a2f45b26f7e94a297e44`
Corrected runtime/manifest: **2026.08.27-02**
Historical same-host reference: `8c25e1e87d4ad8971091df03bc717b039f6e641a`

This is the independent final closure of the `aiup list` performance work delivered by `d72ec95`, `634c895`, `8c25e1e`, `6c96397`, and `9f283e4`. Earlier reports were treated as claims. Conclusions below come from the current source, generated artifacts, deterministic fixtures, repeatable profiling, PTY execution, Git state, and bounded publication readback.

## Contract matrix

| Contract | Source authority | Test or evidence | Result |
|---|---|---|---|
| Runtime, manifest, filesystem, installed versions, lifecycle, dependencies, and provider contracts remain authoritative | `mutation_authoritative_preflight`, `update_candidate_live_revalidate` | Updates fake-updater suite; cache-only candidate with live provider failure | PASS |
| Cache/session data accelerate display only and never authorize mutation | `available_cache_read`, `tui_cache_restore`, `apply_verified_update_selection` | `test-aiup-tui-updates`, `test-aiup-tui-closure` | PASS |
| Runtime and manifest are one exact public activation pair | `macos/aiup-launcher`, `tui_session_context_valid` | `test-aiup-launcher`, wrong-pair session cases | PASS |
| Public launcher is absent from high-frequency fzf interactions | `tui_helper_command`, `tui_fast_helper_command`, `tui_fast_dispatch` | structural assertions plus 20-run helper benchmark | PASS |
| Fast private dispatch cannot mutate and invalid private session context fails closed | `tui_internal_command`, final dispatch gate | cache/session structural tests; wrong/missing token and changed-content closure cases | PASS |
| Catalog/session materialization is one coherent session snapshot | `tui_session_create`, one-pass session metadata writer | cache/session tests and profile substages | PASS |
| Search, category, navigation, resize, reload, and local first-line preview are session-local | generated `fast-helper.py`, fzf bindings | lazy suite, benchmark, five-size PTY matrix | PASS |
| Remote work is lazy, installed-only, cancellable, and bounded | `available_version_preview`, `tui_prefetch_*`, `bounded_provider_capture` | debounce/cancel/timeout/oversize/worker tests | PASS |
| Available-version records bind tool plus installed version | `available_cache_read`, `available_version_of_tool` | version-change and stale-version tests | PASS |
| Provider work debounces, times out, coalesces, recovers stale locks, and retains bounded state | availability cache/lock functions | lazy and closure suites | PASS |
| Installed enrichment uses two workers, one consolidated Homebrew response, and one atomic final publication | `tui_prefetch_supervisor`, `tui_prefetch_brew_consolidated` | structural check, real `current_version` parser, provider-count and reload-coalescing assertions | PASS |
| Exact dedicated-app updates may refresh incrementally; broad-impact operations rescan authoritatively | `tui_incremental_post_action_refresh`, `cmd_catalog_browse` | fixture PTY action harness and profile markers | PASS |
| Updates is a dynamic first category with stable synthetic identities | `tui_updates_publish`, `tui_resolve_update_selection` | Updates suite and PTY matrix | PASS |
| Individual, selected, and update-all mutations are exact, confirmed, revalidated, sequential, and truthful on partial failure | `apply_verified_update_selection`, `apply_catalog_action` | fake updater, cancellation, partial-failure, disappearance/retention tests | PASS |
| Terminal, session, worker, lock, socket, and temporary state clean up without crossing sessions | traps, `tui_session_cleanup`, `tui_stale_sessions_cleanup` | normal exit; `HUP`, `INT`, `TERM`; concurrent-session isolation | PASS |
| Runtime generation directories contain executable release pairs only | launcher generation validation and pruning | launcher interruption/concurrency/retention suite | PASS |
| No database, daemon, service, dependency, or competing persistence layer was added | source and repository diff | complete task-owned diff review | PASS |

## Fault and correctness coverage

The deterministic suites reproduce these boundaries:

- Cache/snapshot: missing, stale, corrupt metadata/content, partial publication, concurrent publication, wrong schema, wrong runtime version/hash, wrong manifest version/hash, wrong source fingerprint, changed content hash, symlink generation, interrupted staging, malformed pointer, and conservative retention of symlinked/unfamiliar state.
- Session: missing/wrong token, wrong runtime/manifest, dead or wrong owner identity, wrong snapshot/update identity, modified indexed content, symlink substitution, concurrent isolated sessions, normal cleanup, `HUP`/`INT`/`TERM`, preservation of other active/malformed/symlinked sessions, and absence of owned provider locks/processes after cancellation.
- Remote enrichment: newer, current, failure, malformed, timeout, oversized response, cancellation before debounce, cancellation during work, five-way coalescing, stale-lock recovery, installed-version changes, corrupt-cache repair, positive/current/failure TTL boundaries, bounded retention, and one consolidated Homebrew `outdated --json=v2` parser using `current_version`.
- Updates: cached first render, uncached checking render, atomic refresh, truthful current/checking/unavailable states, stable/deduplicated aliases, malformed/unknown fail-closed behavior, ordinary-row preservation, search/selection/query/expansion continuity, eligibility exclusions, exact confirmation, live revalidation, sequential execution, dependency ordering, partial failure, successful disappearance, failed-item retention, no-longer-applicable reporting, and cache-only mutation refusal.
- Commands: help, version, plain/interactive list, installed/managed/detected/available views, category filtering, interactive install/remove through PTY fixtures, named update/remove dry-run paths, documentation printing, query/category/navigation persistence, summaries, missing/already-installed fzf, runtime/manifest mismatch, development override, normal launcher activation, and generated catalog count/contracts.

No real end-user package was installed, updated, removed, adopted, or cleaned up. All mutation evidence used public-safe fixtures, dry-run paths, or the fake updater.

## Defects found and fixed

1. **Untrusted availability-cache parsing.** Nonnumeric timestamps reached shell arithmetic and malformed cached versions could reach display. Cache reads now require one exact four-field record, a decimal timestamp, status-consistent empty fields, and the same strict version grammar/comparison used for live provider results. The Updates publisher applies the same grammar before rendering.
2. **Oversized provider response.** The previous effective file ceiling allowed a 2 MiB single line to reach shell parsing. Provider subprocesses are now pre-limited to 1 MiB and the captured byte count is rejected before parsing.
3. **Fast-helper context integrity.** The Python helper validated token/owner and the mutable Updates index but did not independently hash all immutable session inputs. It now rejects changed or symlinked runtime, manifest, catalog, inventory, versions, preview, helper, and row inputs against the session aggregate identity.
4. **Warm picker materialization regression.** Same-host PTY measurements found a current 1.63 s median versus 1.27 s for `8c25e1e`. Profiling attributed the delta to repeated per-file hashing of the Updates snapshot and session identity. One-pass hash emission plus one final activation validation reduced the final current median to 1.26 s; the same-host historical median was 1.18 s. No validation was removed from the activated session.
5. **Background reload storm.** Each installed-only result published and reloaded the session independently. During deterministic PTY startup this could delay or swallow a local preview-toggle or resize action. The two workers now populate the installed-version-keyed cache independently, then the supervisor performs one atomic session publication and one fzf reload after both finish. A structural regression asserts that workers cannot publish and the supervisor publishes exactly once.
6. **PTY harness startup races.** The capture child could query terminal geometry before the parent configured the new slave, and live-resize input could be sent before fzf finished its initial render. The harness now sizes the slave before exec and drains initial rendering before sending the live resize. Three consecutive five-size/live-resize runs passed after the runtime reload coalescing and harness corrections.

## Security and command-safety review

The fast helper, fzf commands, aliases, query state, documentation URLs, state roots, and provider parsers were reviewed for shell/argument injection, tabs/newlines/control bytes, path and symlink traversal, permissions, credential reuse, synthetic-ID leakage, TOCTOU, output/process bounds, orphan work, cross-session state, and cached mutation authority.

- Shell commands use `%q` quoting for exact runtime/session paths; the Python helper receives fzf arguments as argv rather than shell interpolation.
- Manifest and update-index IDs are grammar checked. Synthetic IDs are resolved through a validated index and rejected if they reach mutation dispatch.
- Session roots are mode 700, tokens are cryptographically random and mode 600, and every helper binds live owner, exact runtime/manifest, snapshot, content hashes, view/filter/sort, and token.
- Provider output is time and size bounded; provider and watchdog PIDs are killed/reaped on signals; lock recovery is owner/time bound.
- Every candidate is live-revalidated before confirmation and again before mutation. Availability cache bytes alone cannot invoke the updater.

No command-injection, path-traversal, credential, daemon, unbounded-worker, or cross-session mutation defect remained after the fixes above.

## Performance methodology

`scripts/benchmark-aiup-tui-closure` is the repeatable harness. It uses the public capture fixture, isolated state roots inside the canonical checkout, `time.perf_counter`, nine cold/session samples, 20 warm/interaction samples, nearest-rank p95, and identical environment/input pairs. It size-checks both historical Git objects below 1 MiB, writes bounded regular runtime/manifest files from `git show 8c25e1e:<path>`, never switches branches, and removes its task-owned directory on exit.

`AIUP_PROFILE=1` was run separately. The corrected warm picker attributed approximately 91 ms to the Updates snapshot and 56 ms to one-pass session identity generation; total profiled picker-ready time was 1,066 ms. Unprofiled timings below avoid profiler distortion.

### Same-host historical comparison

| Operation | Samples | `8c25e1e` median / p95 | `2026.08.27-02` median / p95 | Result |
|---|---:|---:|---:|---|
| Cold full fixture list | 9 | 2,144.4 ms / — | 2,535.9 ms / — | variable authoritative cold work; no operational ceiling |
| Warm managed list | 20 | 634.2 / 672.4 ms | 704.0 / 759.3 ms | under 1 s |
| Warm full list | 20 | 676.4 / 712.3 ms | 744.1 / 794.8 ms | under 1 s |
| Warm interactive picker session | 9 | 1,176.3 ms / — | 1,262.1 ms / — | host makes both exceed approximate 1 s; current +85.8 ms |
| Cold session creation | 9 | 4,347.5 ms / — | 4,058.3 ms / — | cold authoritative path |
| Session cleanup | 9 | 124.9 ms / — | 123.7 ms / — | comparable |
| Preview first line | 20 | 28.1 / 28.8 ms | 30.8 / 33.0 ms | PASS |
| Search change | 20 | 30.9 / 32.3 ms | 35.3 / 39.4 ms | PASS |
| Category toggle | 20 | 29.8 / 30.9 ms | 34.4 / 35.9 ms | PASS |
| Category navigation | 20 | 29.6 / 31.4 ms | 32.7 / 33.9 ms | PASS |
| Resize/header | 20 | 30.0 / 34.9 ms | 31.5 / 33.3 ms | PASS |
| Reload after enrichment | 20 | 30.3 / 33.0 ms | 32.3 / 33.9 ms | PASS |

The warm list thresholds pass. The same-host interactive picker comparison explains the approximate 1 s miss: this host also ran historical `8c25e1e` above 1 s, while the corrected current overhead is 82.2 ms for a validated dynamic Updates snapshot. Every local interaction median is below 50 ms and every measured p95 is below 100 ms. No local interaction invokes the launcher, catalog rebuild, complete Homebrew universe, or provider.

### Updates, provider, and action-return measurements

| Operation | Samples | Result |
|---|---:|---:|
| Uncached checking-state picker | 9 | 1,299.6 ms median |
| Cached Updates picker | 9 | 1,284.1 ms median |
| Forced uncached provider plus atomic category publication | 20 | 2,525.1 ms median; 2,554.6 ms p95; exactly 20 provider calls |
| Return after exact dedicated-app fake update | 9 | 10,634.2 ms median |
| Return after package-manager fake update and authoritative wide rescan | 9 | 10,602.0 ms median |

Cached and uncached picker medians are equivalent, proving provider independence. The publication measurement used `__available-version-test` followed by `__tui-test-updates-refresh` in a fresh isolated session for each sample; it deliberately includes the provider subprocess plus atomic refresh and is not a cursor-path latency. Action-return samples used the public capture fixture, fake fzf selection stream, and `AIUP_TUI_TEST_MUTATION_COMMAND`; each sample includes two complete PTY picker sessions and fake mutation. Profile markers, rather than the harness-dominated totals, prove `screenpipe` used incremental refresh and `gemini` used authoritative wide refresh. Provider logs and fake-mutation logs supplied the call counts; no real package command was permitted.

## PTY and media results

`scripts/capture-media --check-layout` passed at 60×18, 80×24, 100×30, 128×40, and 167×47. Updates remained first; 11, 11, 12, 14, and 14 useful catalog rows were visible respectively. Preview was hidden by default only at 60×18 and toggled successfully; other sizes retained a usable preview. Three consecutive matrix runs, each including the 167×47 → 60×18 → 100×30 live resize, passed after reload coalescing and deterministic child-side PTY sizing. Terminal dimensions were respected without resizing, maximizing, or repositioning Terminal. `scripts/capture-media --check` passed without replacing accepted media bytes.

This is automated PTY evidence only. No new visual, physical-device, Safari, actual reduced-motion, screen-reader, assistive-technology, social-preview, or owner acceptance was performed.

## Validation

Final task-owned state passed:

- Bash syntax checks for runtime, launcher, installer, and shell scripts;
- `scripts/test-aiup` (including launcher, cache/session, lazy-provider, Updates, and closure suites);
- `scripts/test-aiup-launcher`;
- `scripts/check-catalog-contracts`;
- `scripts/test-aiup-tui-performance`;
- `scripts/test-aiup-tui-lazy`;
- `scripts/test-aiup-tui-updates`;
- `scripts/test-aiup-tui-closure`;
- `scripts/benchmark-aiup-tui-closure`;
- responsive five-size PTY matrix and live resize;
- `scripts/capture-media --check-layout` and `scripts/capture-media --check`;
- two consecutive idempotent `scripts/sync-public-docs` passes;
- `scripts/check-site`; and
- `git diff --check`.

## Remaining limitations

- Cold authoritative inventory/session creation is intentionally slower than warm list readiness.
- The full interactive picker includes immutable session and Updates validation; on this run both current and historical sessions exceeded the approximate 1 s investigation threshold, while warm managed/full list readiness passed it.
- Provider availability and performance outside deterministic fixtures vary by network and upstream service.
- Linux, Windows, tagged releases, repository CI, Safari/device/accessibility acceptance, and the known greater-than-five-second animation control question remain outside this closure.

## Rollback

Revert the single Prompt 4 public commit on `main` and allow the established GitHub-connected Pages workflow to republish the prior runtime/manifest pair. Do not rewrite history or delete Cloudflare resources. Cache schema v3, availability records, and private sessions are disposable accelerators; an older runtime rejects incompatible state. The launcher retains the previous complete executable generation as recovery evidence.

## Final decision

**PASS WITH FIXES.** Confirmed cache/parser, provider-bound, session-integrity, warm-picker hashing, reload-coalescing, and PTY-harness defects were corrected through the existing architecture, regression-tested, fully revalidated, and prepared for the established publication path. The Prompt 1–4 TUI performance workstream is complete for this dated macOS scope.
