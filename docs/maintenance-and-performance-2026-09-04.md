# Maintenance commands and efficiency review — 2026-09-04

Runtime/catalog: `2026.09.04-03`.

## Delivered

- `aiup check [tools…]`: installed/available version and proposed action. `--refresh` bypasses availability cache. No package mutation or shell-profile writes; local cache writes are allowed. Unsupported, failed, empty, or malformed metadata is not reported as current.
- `aiup explain <tool>`: detection state, version, manager, resolved location, package, documentation, and next action/reason. Detected inventory IDs retain their inspect-only contract.
- `aiup history [tool]` and `aiup logs [tool]`: structured results and exact byte-range tool output. New update runs save progress atomically so interrupted runs remain diagnosable.
- Warnings have a separate marker and count. Script-setup warnings receive an actionable explanation, while benign already-installed/no-upgrade notices remain in logs.
- Retain 20 completed runs by default, configurable from 1 to 100 with `AIUP_LOG_LIMIT`. Protect active owners, ambiguous active markers, symlinks, unfamiliar files, and recent unindexed legacy logs. Interrupted inactive runs count toward retention. Existing legacy logs lack per-tool metadata; they remain readable as whole logs.
- Skip npm reinstall only on a fresh exact version match with existing executable links in the target prefix. Provider errors, missing/invalid responses, broken links, differing versions, and `--force` retain installation. Existing migration and cleanup contracts still execute.
- Skip generic Homebrew no-op upgrades using one valid post-refresh `outdated --greedy --json=v2` snapshot. Unknown metadata preserves normal updates. Verified TUI update selections bypass this shortcut.

## Codebase review

The review covered the macOS runtime subsystems, public launcher and installer, catalog and inventory, TUI/session/provider helpers, removal and cleanup boundaries, site, generators, capture/brand tooling, fixtures/checks, and cross-platform placeholder documentation. This is a source review and targeted verification, not a claim that every vendor installer was executed.

| Area | Finding and action |
|---|---|
| Update adapters | Avoided unconditional npm reinstall and generic Homebrew no-op upgrade. Preserved native vendor updater behavior, dependency ordering, manager switching, and failures. Package mutations remain serialized. |
| Homebrew inventory/version reads | One shared pair of formula/cask version listings provides both membership and version values. Warm the cache in the parent before command substitutions to avoid discarded cache initialization. In a fixture, four version lookups require only two total Homebrew listing calls; previously the same pattern needed two membership listings plus four version calls. |
| Managed shell paths | Perform existing profile reconciliation once per process; later updater calls reuse the active setup. Read-only commands never invoke it. |
| Inventory fingerprints | Removed an unused `npm root -g` query. Include scoped package metadata and the actual npm prefix so nested external installs/updates invalidate snapshots. |
| Public launcher | Fetch runtime and manifest concurrently, capped at 1 MiB each. Both downloads and the matching pair still validate before activation. Preserve locks, current/previous pointers, failure rollback, and generation retention. The installer’s validation and atomic replacement remain unchanged. |
| TUI and update providers | Preserve indexed/session-local fast helpers, bounded provider requests, existing workers, negative caches, installed-version binding, and fresh mutation authorization. Tightened empty/malformed provider responses; preserved explicit failure states. Avoid a broad renderer or concurrency rewrite without evidence it improves the current hot path. |
| Reports and logs | Separate outcome from warning, preserve before/after and failed/skipped results, and retain actionable history. Keep plain/NO_COLOR and narrow-terminal layouts. Logs contain local provider output and remain private. |
| Catalog and generated documentation | Removed the obsolete fixed 81-entry contract assertion; compare against the canonical manifest and retain tool-specific checks. Synchronize the site’s embedded software version. |
| Media generation | Compare canonical media before copying. An unchanged sync avoids rewriting roughly 1.1 MiB of accepted media. Preserve accepted art, animation, provenance, and capture behavior. |
| Static site | Already has no runtime JavaScript, framework, analytics, external fonts, or service worker. Preserve this low-cost architecture; no new frontend machinery or provider resources. |
| Capture, brand, test, and benchmark tools | They run on demand and do not affect normal CLI startup. Preserve their fixture, provenance, and cleanup contracts; do not run broad benchmarks or regenerate assets as a routine gate. |
| Linux/Windows | Remain documented placeholders. No unsupported cross-platform behavior was added. |

## Verification and limits

Focused fake-provider checks exercise npm no-op/fallback/repair, Homebrew batching and conservative snapshot behavior, scoped npm fingerprints, read-only checks, warning/result rendering, bounded retention, active-run/symlink preservation, and exact tool-log slices. Existing launcher checks cover pair activation and failure handling with mocked downloads. No live package upgrade is needed to prove these changes.

Live acceptance uses read-only `check`/`explain` and a dry-run update/history readback. These are separate from actual vendor update success and owner visual acceptance. Improvements reduce unnecessary commands and writes; no universal wall-clock speedup is claimed. Network and vendor time remain variable.

## Preserved and deferred

Do not replace safe session verification with an unchecked cache, parallelize mutating package managers, infer management of project-local dependencies, or install extra browser/CI tooling as an optimization. Additional native-provider metadata contracts and a broader cold-scan rewrite should follow measured bottlenecks and reviewed provider behavior. An explicit npm/Homebrew repair remains available through `--force`.

Rollback is a normal Git revert of this release. Retention removes only eligible old local logs; it does not modify installed packages, project data, or user settings.
