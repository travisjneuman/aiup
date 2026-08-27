# TUI performance slice 2

Status: implemented in runtime **2026.08.26-03**

## Work boundaries

The authoritative entry path still validates the exact runtime/manifest pair and obtains or rebuilds a fingerprint-bound local snapshot. The second slice changes what happens after that work:

- **Eager once per session:** catalog, installed managed state, installed versions, detected inventory, the bounded Homebrew inventory, expanded and collapsed row forms, static preview lines, documentation targets, and exact row IDs.
- **Lazy on focus:** available-version metadata for the focused installed managed item. Local preview lines are printed first. A cache miss waits 200 ms, so fzf can cancel work for a row that was only traversed.
- **Background after interactivity:** installed managed items only, never all 81 entries. The default is two workers (bounded to two or three), delayed by 350 ms. Homebrew metadata uses one read-only `brew outdated --json=v2` snapshot before non-Homebrew work is divided between workers.
- **Heavyweight views:** the complete Homebrew formula/cask universe is still absent from overview sessions. It is enumerated only by the explicit available view or focused available category context. Detected and bounded Homebrew inventory use schema-, age-, runtime-, manifest-, view-, and source-fingerprint-bound snapshots.

Automatic preview refresh after a background result is deliberately deferred. A new focus or manual preview refresh reads the new cache entry. This avoids a local fzf listener/socket lifecycle and keeps cancellation and terminal restoration simple.

## Remote metadata cache

Entries live under `$AIUP_STATE_DIR/available-versions` and bind exactly to `tool + installed version`.

| Result | Default TTL | Preview behavior |
|---|---:|---|
| Newer supported version | 900 seconds | Append `available <version>` |
| Valid provider response with no newer version | 900 seconds | Installed version only |
| Timeout, transport failure, malformed response | 60 seconds | Installed version only; never claim current |

Writes use same-directory temporary files plus atomic rename. One per-tool directory lock coalesces preview and prefetch workers; dead or over-time locks are recovered without `flock`, so the contract works with macOS Bash 3. Cache retention defaults to 128 tool records. Provider output is file-size bounded, network/provider calls have short timeouts, and killed/cancelled preview work removes or safely ages out its exact lock.

A cache record never authorizes a mutation. A changed installed version misses the old key. Corrupt, missing, stale, wrong-version, or concurrently replaced records degrade to installed-version-only display and an eligible read-only retry.

## Interaction path

fzf invokes a small session-owned Python helper for preview lookup, row transforms, header sizing, category actions, and category navigation. The helper validates the private session token and live owner before reading session files. It performs one indexed pass for a preview and then, only for an installed managed row, replaces itself with the exact active runtime's private remote-enrichment command.

Typing does not persist query state or reinitialize aiup. Because collapsed children are not in the empty-query input, the `change` event asynchronously transforms the already materialized expanded rows with one local helper. The final query is persisted only when the picker exits. Category and expand/collapse actions use the same local transform. `--track --id-nth=1` preserves the exact stable row identity across reloads, including selected multi-items. Resize changes only the responsive header and preview; documentation return refreshes the preview without rebuilding rows.

## Post-action invalidation

Every action revalidates its exact live target before mutation. Dedicated app updates can patch the affected catalog row and installed version into a new immutable cache generation, retaining unrelated snapshot data. The broader authoritative rebuild remains intentional for package-manager operations, installers, removals, cleanup, Homebrew adoption, dependency changes, and PATH-affecting actions. Those actions can change more than the selected row, so an incremental claim would be unsafe.

The final query, category, and exact selected ID survive picker exit/re-entry. Existing result summaries, controlling-terminal restoration, and signal cleanup remain the parent process's responsibility. Session cleanup cancels and reaps its read-only prefetch supervisor and workers.

## Fault behavior

Network loss, npm/PyPI/Homebrew/Screenpipe failure, timeout, malformed metadata, cancelled preview, killed worker, stale session, changed installed version, corrupt cache, and concurrent writes leave local rows and installed versions usable. No response for one installed version is displayed for another. Missing or invalid authoritative snapshots rebuild; invalid remote enrichment never escalates into mutation authority.

`AIUP_PROFILE=1` adds cache hit/miss status, snapshot schema/age/fingerprint diagnostics, worker bounds, incremental-versus-wide post-action choice, and normal stage timings to stderr. Normal TUI output stays unchanged.

## Measurements and coverage

The before values were captured from `2026.08.26-02` on this Mac immediately before the slice. The after values use the same deterministic public fixture and the actual validated session helper; nine-run medians are reported. Picker-ready and action-return remain dependent on authoritative local/provider work and are measured separately from session-only interactions.

| Operation | Before | After | Target |
|---|---:|---:|---:|
| Picker ready, warm validated fixture snapshot | 2,220 ms | 700 ms | measured, provider-independent |
| Cursor preview (local first line) | 150.7 ms full warm preview | 23.8 ms | <100 ms |
| Search change | about 300 ms (query process + 184.9 ms row helper + reload) | 25.8 ms | <200 ms |
| Category toggle/reload | about 300 ms (mutation process + 184.9 ms row helper) | 26.8 ms | <200 ms |
| Resize/header refresh | 111.4 ms header helper before preview refresh | 25.6 ms header helper | <200 ms |
| Action return to warm picker session | 2,220 ms session rematerialization, excluding the action | 700 ms session rematerialization, excluding the action | measured, action-dependent |

The deterministic suite covers cache hit/miss, valid negative cache, newer/current results, malformed metadata, timeout, provider failure, cancellation before debounce, five-way concurrency coalescing, installed-version changes, collapsed-category search, category transforms, navigation, resize, documentation return, stable IDs, exact fzf tracking configuration, and local-preview latency. The pre-existing cache/session corruption and PTY tests remain in force.

Automated PTY and fixture evidence is not visual, physical-device, Safari, reduced-motion, screen-reader, assistive-technology, or owner acceptance.
