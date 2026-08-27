# Dynamic Updates category and safe bulk updating

Status: implemented in runtime **2026.08.27-01**

## User-visible behavior

`aiup list` now places a virtual Updates category above `infra` and every catalog category. The picker still renders before remote enrichment. A valid installed-version-keyed cache can populate verified rows immediately; otherwise the category starts in a checking state and reloads from the private session as the existing two read-only provider workers complete.

The header distinguishes these facts rather than collapsing them into a binary result:

- `Updates · checking…`
- `Updates available · N`
- `Updates · all verified items current`
- `Updates · N verified · M checking`
- `Updates · N verified · M unavailable to verify`

Timeouts, transport failures, malformed responses, missing contracts or versions, stale cache entries, and unfinished checks never mean current. Each verified update row shows its canonical name and `installed → available` versions. Its preview retains normal catalog context and promotes `installed`, `available`, and `action    update` lines.

Enter or `ctrl-r` updates one focused update row. Checked update rows plus `ctrl-r` update only those verified canonical items. A distinct `Update all verified items · N` row appears only when at least one verified item is bulk eligible.

## Identity and selection

Virtual rows use stable synthetic identities: `__update:<canonical-id>` and `__updates:all`. They do not replace the ordinary row, so each item remains visible in its normal category. Preview, documentation, Enter, and multi-selection resolve aliases through the validated update index before dispatch.

Resolution rejects malformed or unknown aliases, deduplicates canonical IDs, and prevents a synthetic ID from entering provider or mutation functions. Selecting Update all alongside ordinary update aliases expands the displayed eligible snapshot once and deduplicates the union. fzf retains `--track --id-nth=1`; reloads preserve the current query, exact selection identities, expansion state, preview state, and tracked position where fzf can retain it.

## Bulk eligibility and execution

An item enters the verified update set only when its installed version is known, its supported provider check completed successfully, and the existing version comparison confirms a genuinely newer release. The bounded inventory includes installed managed catalog items, required infrastructure such as fzf, and already-enumerated installed Homebrew extras confirmed by the consolidated Homebrew response. It does not enumerate Homebrew's complete universe.

Absent, detected-only, unmanaged, unknown-version, checking, failed, adoption, removal, unsupported-updater, and stale-version results are excluded. Exceptional lifecycle rows can remain visible as manual review but are not silently included in Update all.

Activating Update all captures an immutable, deduplicated set of the currently displayed eligible canonical IDs. aiup revalidates the live runtime/manifest pair, filesystem state, installed version, package metadata, dependencies, lifecycle, updater contract, and live provider result before confirmation, displays the exact count and names, and repeats the item-specific live validation immediately before every mutation. A declined confirmation performs no mutation.

Accepted batches run sequentially through `apply_catalog_action update`, `main_update`, and the established updater. Dependency ordering is preserved and package/provider mutations are never parallelized. A permitted item failure does not abort unrelated later items; the final result separates successful, failed, skipped, and no-longer-applicable items.

## Session and cache boundary

The update index is disposable session state, not another database. It is atomically replaced inside the existing private session and bound to the exact runtime version/hash, manifest version/hash, session token and owner, snapshot generation, canonical ID, installed and available versions, result status, and cache timestamp/status identity. Its metadata also hashes the base rows, rendered rows, and update index.

Corrupt, partial, symlinked, duplicate-key, wrong-runtime, wrong-manifest, wrong-session, wrong-snapshot, and wrong-installed-version data is rejected. Publication uses a private session lock and same-directory temporary files followed by atomic rename. Normal exit and signal handling cancel and reap the prefetch supervisor/workers and remove the socket, publication lock, temporary files, and session. Existing bounded cache/session retention remains in force; executable generation directories are untouched.

Availability caches and sessions accelerate display only. They never authorize mutation. An installed-version change misses and invalidates the old pairing. Successful actions refresh authoritative state so current items disappear; failed items remain when a subsequent valid provider result still verifies a newer version. Dedicated-app updates retain the previously proven incremental refresh, while package-manager, dependency, PATH-sensitive, adoption, removal, and other broad-impact operations retain the wider authoritative rescan.

## Performance

Measurements used `AIUP_PROFILE=1`, the deterministic public capture/provider fixtures, and repeatable median runs on the same Mac. The published `8c25e1e` values remain the historical reference; the baseline commit was also executed immediately beside this implementation to distinguish host load from code change.

| Operation | Published `8c25e1e` | Same-host `8c25e1e` | `2026.08.27-01` | Change from same-host baseline |
|---|---:|---:|---:|---:|
| Warm managed picker/list readiness | about 700 ms | 814.4 ms | 825.3 ms | +10.9 ms |
| Warm full picker/list readiness | about 700 ms | 857.8 ms | 881.3 ms | +23.5 ms |
| Cursor preview first line | 23.8 ms | 24.3 ms | 30.3 ms | +6.0 ms |
| Search change | 25.8 ms | 26.7 ms | 32.3 ms | +5.6 ms |
| Category toggle | 26.8 ms | 27.0 ms | 33.0 ms | +6.0 ms |
| Resize/header | 25.6 ms | 26.4 ms | 32.0 ms | +5.6 ms |

Initial readiness remains provider-independent, update materialization is session-local, and every high-frequency interaction remains about 30–33 ms. The same-host deltas are the cost of validating the atomically changing update index before consuming it; no provider request or full-list regeneration entered cursor, search, category, or resize paths. The current values are nine-run medians; the same-host historical cursor-first-line harness emitted one first-line sample while its other interaction values were nine-run medians. Final independent regression closure is intentionally deferred to Prompt 4.

## Validation and limitations

The deterministic update suite covers cached and uncached startup, atomic background additions, current/failure/timeout/malformed/unfinished semantics, stale installed versions, corrupt/partial/symlinked/wrong-pair indexes, exact alias mapping, malformed aliases, deduplication, preview content, one/selected/all canonical dispatch, cancellation, eligibility exclusions, partial failure, post-action disappearance/retention, session continuity, cleanup, mutation preflight, provider coalescing, bounded Homebrew inventory, and existing controls.

The broader public validation includes Bash syntax, launcher and catalog contracts, cache/session and lazy-provider suites, responsive PTYs at 60×18 through 167×47, media-layout and accepted-media byte checks, generated-document idempotence, site validation, and diff whitespace checks. Provider behavior is fixture-driven and does not require external network availability.

Automated PTY evidence is not visual, physical-device, Safari, reduced-motion, screen-reader, assistive-technology, or owner acceptance. Accepted media, poster, brand assets, site composition, credentials, CI architecture, and Cloudflare resources are unchanged.

## Rollback

Revert the Prompt 3 source commit on `main`; the public launcher will return to the prior validated runtime/manifest pair through the established GitHub-connected publication path. Existing state under cache schema v3 is disposable and may be left in place: an older runtime ignores incompatible generations. Do not delete Cloudflare resources or rewrite repository history.
