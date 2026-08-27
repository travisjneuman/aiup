# Changelog

## 2026.08.27-02

- Audited the integrated `aiup list` performance program with independent cache, session, provider, Updates, mutation-safety, command, PTY, launcher, and publication regression evidence; the public implementation is closed, while the required private closure record remains blocked by its preserved canonical checkout.
- Hardened remote availability cache parsing so nonnumeric timestamps, extra TSV fields, malformed or control-bearing versions, and oversized provider responses fail safe and are repaired through a bounded live provider check.
- Added final regressions for strict cache metadata, the 1 MiB provider-response boundary, stale-lock recovery, cancellation during provider work, TTL and retention behavior, concurrent session isolation, all supported cleanup signals, and the rule that cache contents alone cannot invoke an updater.
- Coalesced two-worker enrichment into one atomic session publication and fzf reload, and made the PTY layout harness establish child geometry before exec so interaction and live-resize checks are deterministic.

## 2026.08.27-01

- Added an immediate virtual Updates category above the catalog. It distinguishes checking, verified newer, verified current, and unavailable-to-verify results without waiting for provider enrichment.
- Added stable `__update:<id>` aliases and an `__updates:all` action that map back to canonical catalog identities for preview, documentation, selection, and updates. Synthetic identities are rejected at provider and mutation boundaries.
- Added individual, selected, and explicit update-all execution through the existing authoritative update path. Batch candidates are confirmed by name, dependency ordered, revalidated immediately before each sequential mutation, deduplicated, and reported as successful, failed, skipped, or no longer applicable.
- Extended private TUI sessions with an atomically published, runtime/manifest/session/snapshot/version-bound update index. Cached availability accelerates display only; changed installed versions invalidate the pairing and can never authorize an update.
- Added deterministic update-category, alias, bulk-action, failure, refresh, corruption, cleanup, provider-coalescing, Homebrew-laziness, and continuity coverage.

## 2026.08.26-03

- Materialized complete local preview lines and installed versions in each validated TUI session. Cursor focus now uses one small indexed helper process; provider metadata starts only after the local preview is visible.
- Added current-version-keyed positive, current, and short failure caches; a 200 ms cancellable focus debounce; atomic writes; bounded retention; stale-lock recovery; and concurrent lookup coalescing compatible with Bash 3.
- Added installed-only background enrichment with two workers and one consolidated read-only Homebrew outdated snapshot. Workers are delayed until the picker is interactive and are cancelled and reaped on exit.
- Removed query persistence and full runtime row rebuilding from the per-character path. Collapsed-category search now transforms materialized session rows, while category, navigation, resize, and documentation-return actions stay session-local and use fzf field identity tracking.
- Added exact selection persistence and an incremental post-action snapshot refresh for dedicated app updates. Package-manager, installer, removal, cleanup, adoption, dependency, and PATH-affecting actions deliberately retain the wider authoritative rescan.
- Added deterministic provider/cache/cancellation/coalescing/version-change tests and measured session interaction regressions.

## 2026.08.26-02

- Added schema-versioned, fingerprinted, atomically published disposable catalog snapshots beneath the aiup state directory; invalid, stale, corrupt, partial, incompatible, symlinked, concurrent, and interrupted states fail safe and rebuild.
- Added bounded PID-plus-nonce TUI sessions that bind helpers to the exact validated runtime, manifest, view, and snapshot. fzf helpers execute that runtime directly and no longer refresh public generations or repeat full initialization during cursor movement, search, resize, or category navigation.
- Replaced per-field manifest `awk` scans with one-pass in-memory manifest data and one bounded static-preview renderer; made the system npm prefix lazy and pre-rendered session rows/previews.
- Opening interactive list/install/remove now uses an installed fzf without updating it. Missing fzf retains the established bootstrap/error path, while normal updates and `aiup only fzf` still maintain it.
- Every mutation path invalidates accelerators and revalidates the runtime, manifest, live filesystem, package metadata, and provider state immediately before work. `AIUP_PROFILE=1` reports concise stage timings on stderr.
- Added deterministic cache/session corruption, concurrency, interruption, pair-binding, cleanup, fzf-boundary, structural, and generous performance regression coverage.

## 2026-08-26 — public presence and documentation closure

- Restored the owner-selected minimal, GitHub-first site: the aiup lockup, one authentic TUI animation, and one prominent repository destination. The README remains the explanatory product surface.
- Rebuilt the primary media from the real responsive TUI at 100 × 30 with six authentic states, exact Catppuccin/indexed colors, a 10.78-second continuous loop, and a static reduced-motion poster. The site contains no playback control or JavaScript.
- Published the complete favicon, Apple/PWA/maskable, Open Graph, and GitHub social-preview asset suite together with accurate metadata, JSON-LD, robots, sitemap, manifest, `llms.txt`, static 404, and security headers.
- Reconciled the public repository description, homepage, topics, issue/community surfaces, installation language, generated catalog, media provenance, and current macOS-only/pre-1.0 limitations. Wiki, Projects, and Discussions remain disabled; no tag, release, or CI workflow was manufactured.
- Recorded owner acceptance of the current minimal site and six-state media. True mobile/Safari, physical-device, screen-reader/assistive-technology, actual OS reduced-motion, and deployed social-preview acceptance remain optional separate evidence lanes. The greater-than-five-second autoplay without a control remains a documented WCAG 2.2.2 limitation.
- This public-presence and media work did not change the runtime version; `2026.08.25-02` remains the current macOS tool version.

## 2026.08.25-02

- The public launcher now activates each validated runtime/manifest pair as one immutable generation behind an atomic pointer and retains the previous complete generation as recovery evidence.
- The public installer downloads beside the destination, validates the launcher, and atomically replaces it; network-free regressions cover first install, safe replacement, invalid/partial input, spaced paths, idempotent PATH persistence, exact uninstall scope, activation failures, and later recovery.
- A dated primary-source audit records dispositions for all 83 starting entries: 73 confirmed, 7 corrected, 1 downgraded, and 2 removed, leaving 81 managed entries.
- Gemini CLI and Continue CLI are active; `n8n` now uses its official npm package; Pi, GSD, OpenCode, and Goose use current canonical sources; GPT4All is maintenance-only; `omp` and Plandex are detected-only when present.
- Homebrew adoption and recommended-category copy now state the controlled behavior precisely: aiup does not pass `--zap` or directly delete `~/Library`, while Homebrew and vendor behavior may vary.

## 2026.08.25-01

- Public installs no longer default to or probe a maintainer-specific checkout. `AIUP_SOURCE_PATH` is consulted only when a user deliberately sets a non-empty local-development path.
- The launcher now fetches, validates, version-matches, and activates the public runtime together with its catalog manifest. Failed, empty, invalid, mismatched, partial, and offline refreshes stop without executing the download or a stale cache.
- Installation, PATH persistence, prerequisites, network behavior, local development, and uninstall instructions now describe the public macOS contract without assuming Bash, Python 3, curl, Homebrew, or fzf is already usable.
- Network-free launcher regressions cover clean HOME/state fixtures, paths with spaces, first run, refresh, offline failure, explicit source override, and uninstall scope.

## 2026.08.23-01

- Official app updaters can declare a metadata endpoint template; Screenpipe now checks its official Tauri update manifest before downloading a DMG and refuses unverified fallback downloads.
- `pi-acp` now reports its npm package version even when its CLI emits no `--version` output, and removing Pi explicitly explains that the independently installed ACP adapter remains.
- Default update results distinguish current tools and skipped unmanaged apps from completed updates.

## 2026.08.21-02

- The interactive catalog now supports left/right category collapse/expand and Page Up/Page Down jumps between category rows.

## 2026.08.21-01

- `aiup list` now caches catalog/Homebrew ownership lookups during inventory scanning, so the fzf picker opens promptly even when many Homebrew packages are installed.

## 2026.08.20-25

- Homebrew taps already installed on a Mac are treated as prior user approval and trusted automatically; missing taps required by a selected tool still prompt before they are added and trusted.

## 2026.08.20-24

- Screenpipe now updates from the official architecture-specific stable DMG, verifies the bundle identity, code signature, and Gatekeeper assessment, preserves a rollback copy, and relaunches only when it was running.
- Installed untrusted Homebrew taps are displayed with their remote and automatically trusted as prior user-approved taps; newly required taps still require approval before they are added.
- Catalog validation now fails closed when an entry lacks its installer metadata, updater, remover, label, category, or documentation URL.

## 2026.08.20-23

- Update/install runs are now unattended: Homebrew receives `--yes`, child processes receive no terminal input, and duplicate Homebrew refreshes are skipped.
- Version summaries close stdin so terminal-oriented tools such as `pi-acp` cannot block aiup; unsupported downloaded apps are skipped during the default scan.

## 2026.08.20-22

- Historical: installed `aiup` temporarily preferred a maintainer checkout path for local testing. Version 2026.08.25-01 removed that machine-specific public default; local-checkout execution now requires an explicit `AIUP_SOURCE_PATH`.

## 2026.08.20-21

- Installed `aiup` now uses a live-sync launcher that fetches and validates the current public `main` runtime on every invocation, failing closed when it cannot refresh.

## 2026.08.20-20

- fzf is required infrastructure, managed as a Homebrew formula and refreshed during update runs.

## 2026.08.20-19

- Tab title is `aiup`. Favicon at `/favicon.ico`.

## 2026.08.20-18

- Open Graph and Twitter large image, JSON-LD, sitemap, robots.txt.

## 2026.08.20-17

- Site uses the official lockup and brand colors.

## 2026.08.20-16

- Public site is the product page. Install and how-to live in the repo.

## 2026.08.20-11

- Historical copy said settings always stay. The current contract is narrower: aiup does not pass `--zap` or directly delete `~/Library` during adoption.
- Command-line tools already on PATH get a Homebrew copy alongside.

## 2026.08.20-10

- Initial public source revision. No version tag or packaged installer was created.
