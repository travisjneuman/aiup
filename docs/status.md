# Scope, completion, and next work

Status date: **2026-08-25**

Current version: **2026.08.25-02**

## What is complete

The macOS implementation has passed the documented source and regression checks for this dated daily-use scope:

- scan installed managed tools and update only what is present;
- require and maintain fzf as interactive infrastructure;
- install, update, remove, or adopt catalog items through explicit actions;
- browse the managed catalog, local detected-only software, and Homebrew inventory through focused views;
- search inside collapsed categories and restore a clean picker after provider actions;
- avoid passing `--zap` or directly deleting `~/Library` when an existing app is handed to Homebrew, without claiming universal vendor behavior;
- check official desktop-app metadata before downloading a replacement and validate the replacement before activation;
- keep generated catalog documentation synchronized with the manifest;
- install publicly without probing a maintainer checkout or any personal path;
- refresh and validate the public runtime plus its matching catalog manifest before activating one immutable generation through an atomic pointer;
- retain the previous complete validated generation as recovery evidence without executing it as an offline fallback;
- serialize finalization, pointer replacement, and exact pruning so repeated successful refreshes retain only current and previous while overlapping hidden staging remains untouched;
- keep local-checkout execution behind an explicit non-empty `AIUP_SOURCE_PATH` opt-in;
- fail closed on offline, failed, empty, invalid, mismatched, or partial public refreshes;
- capture the real current TUI through a deterministic public-safe, mutation-free fixture while preserving its ANSI category and state colors;
- keep `docs/media/` canonical and verify byte-identical `site/media/` mirrors;
- provide a scalable brand source plus complete favicon, PWA, maskable, social-card, README, and site derivatives;
- serve the static TUI poster instead of the animated GIF when reduced motion is requested;
- provide a complete static product site with semantic navigation, a descriptive
  install path, plain-language lifecycle explanation, captioned real-TUI media,
  generated catalog summaries, safety/privacy boundaries, requirements, FAQ,
  progressive copy and animation controls, and a branded 404;
- keep essential content indexable and usable without JavaScript, remove the
  external font request, and add dependency-free deterministic site validation;
- provide aligned title/description/social metadata, truthful WebSite and
  SoftwareApplication JSON-LD, crawler files, a manifest, and narrowly scoped
  static-site security headers.

The 2026-08-25 closure added a validated atomic launcher installer and network-free regression coverage for clean public HOME/state fixtures, paths containing spaces, first install, safe replacement, install/PATH persistence, runtime and manifest activation failures, pre-switch and current-pointer failure, offline refusal, explicit local development, exact uninstall scope, invalid/partial refresh rejection, prior-pair preservation, bounded repeated-success retention, dead-lock recovery, overlapping activation safety, and later recovery. The same date's primary-source catalog audit recorded a disposition for all 83 starting entries and left 81 managed entries with executable contracts. The public support baseline is macOS 14+ with Bash 3+, Python 3, and curl; individual products can impose stricter constraints recorded in the [dated audit](catalog-accuracy-2026-08-25.md).

## What is not complete

aiup is not a finished cross-platform or tagged 1.0 product:

- Linux and Windows are documented stubs.
- There is no tagged release or packaged installer; installation uses the live launcher.
- A normal public invocation is not offline-capable: it must refresh from GitHub and deliberately refuses to execute a stale cache. Offline development requires an explicit local checkout path.
- There is no repository CI workflow. Current validation is local and intentionally small relative to the Bash runtime.
- Catalog/provider maintenance is ongoing as upstream tools, installers, and trust requirements change.
- Browser/device/assistive-technology and owner acceptance remain evidence lanes separate from source, asset, publication, and public-HTTP checks; the Thread 3 media owner-acceptance lane is satisfied, but Thread 4 site visual/accessibility acceptance is not.
- The muted media at `d629ca3` remains rejected historical evidence. The corrected color-faithful media published at `4c1d980` has received explicit owner visual acceptance.

## Site status

Thread 4 source implementation is complete in this revision. The single-page
information architecture now covers product state, per-run activation, the real
TUI, generated catalog scope, safety/privacy, requirements, installation, FAQ,
and durable source/documentation links. It uses semantic landmarks, one H1, a
main-targeting skip link, visible focus, 44-pixel controls, meaningful image
alternatives/captions, a reduced-motion poster and explicit animation control,
and a no-JavaScript install fallback. The page uses system fonts, no framework,
no external runtime dependency, no analytics, no cookies, no tracker, and no
service worker.

`scripts/check-site` validates metadata, JSON-LD, manifest and sitemap parsing,
local references, ids and anchors, image dimensions, generated version/count and
category facts, reduced-motion wiring, headers, accepted media mirrors, and
public-safety boundaries. `scripts/sync-public-docs` now owns the index catalog
summary as well as the README, generated catalog documents, catalog JSON, and
media mirrors.

The T3 collaborative preview loaded the local root and returned the new title,
but its screenshot, resize, DOM-evaluation, and interaction calls timed out in
this implementation run. Source validation is therefore not visual, keyboard,
device, Safari, screen-reader, or assistive-technology acceptance. No owner
visual/accessibility acceptance has been provided for Thread 4.

Publication remains exclusively on the established GitHub-connected Cloudflare
Pages path. A source push, authenticated Pages receipt, public HTTP/hash
readback, browser/device evidence, and owner acceptance remain separate claims;
this checked-in source file alone does not prove any later promotion.

Thread 3 is complete and owner accepted. Thread 5 still separately owns GitHub
About, topics, social-preview settings, repository settings, tags, releases, and
the broader GitHub public-presence overhaul.

## Accepted media correction and brand status

The owner-accepted corrected real-TUI media was published at `4c1d980` from capture source commit `04fe3b62c2d6d665774097a582677cae08c50ce4`. It uses a 128 × 40 PTY, 1280 × 720 output, a fixed JetBrains Mono Nerd Font Mono profile, the production indexed category palette, fixed fzf chrome colors, and public demo indexes. The first Thread 3 set inherited `NO_COLOR=1`, causing fzf to remove input ANSI styles before PTY capture; those muted files at `d629ca3` failed owner acceptance and remain historical rejection evidence. The corrected session explicitly removes that inherited variable, asserts raw SGR forms and parsed cell styles, then verifies expected PNG pixels and GIF palette retention. The fixture still records read-only Homebrew queries, rejects mutating verbs, bypasses host inventory, and cancels adoption at the first confirmation. Exact provenance, hashes, dimensions, timing, and limitations are in [`media/README.md`](media/README.md) and [`media/capture-manifest.json`](media/capture-manifest.json).

The completed set is:

1. `aiup-list.gif` — compact overview, a query that finds a row inside a collapsed category, preview visibility, then a clean cancel.
2. `aiup-list-collapsed.png` — current full-screen overview with current categories, counts, border, and navigation hints.
3. `aiup-list-homebrew.png` — focused Homebrew/recommended view with current action labels.
4. `aiup-list-adopt.png` — the real pre-action adoption confirmation, cancelled before mutation.
5. `aiup-list-search.png` — a still that makes collapsed-category search and the current Gemini preview explicit.
6. `aiup-list-poster.png` — the corresponding static reduced-motion presentation.

The brand review retained the recognizable open terminal, chevron, underscore, and cyan/mint/purple identity. It introduced scalable canonical sources, a simplified 16-pixel favicon, ordinary and maskable PWA compositions, 1200 × 630 Open Graph art, and a 1280 × 640 GitHub social-preview file below 1 MiB. The archived original remains byte-identical. See [`../site/brand/README.md`](../site/brand/README.md).

## Ordered closure sequence

1. **Catalog/provider audit accepted** — completed in 2026.08.25-02 with all 83 starting dispositions recorded.
2. **Current TUI media and brand suite** — corrected media published at `4c1d980` from the real current interface without software mutation and explicitly owner accepted; Thread 3 is complete.
3. **Site UX/SEO** — Thread 4 source implementation and deterministic validation are complete; publication, browser/device, assistive-technology, search-indexing, social-cache, and owner acceptance stay separate evidence lanes.
4. **GitHub public-presence overhaul** — Thread 5 remains separate and must not begin from Thread 4.

The product should remain maintenance-led. New catalog breadth is lower priority than trustworthy lifecycle behavior for existing entries; tagged-release, CI, and cross-platform decisions remain separate future scopes.
