# Scope, completion, and next work

Status date: **2026-08-24**

Current version: **2026.08.23-01**

## What is complete

The macOS implementation is complete for its present daily-use scope:

- scan installed managed tools and update only what is present;
- require and maintain fzf as interactive infrastructure;
- install, update, remove, or adopt catalog items through explicit actions;
- browse the managed catalog, local detected-only software, and Homebrew inventory through focused views;
- search inside collapsed categories and restore a clean picker after provider actions;
- preserve settings when an existing app is adopted by Homebrew;
- check official desktop-app metadata before downloading a replacement and validate the replacement before activation;
- keep generated catalog documentation synchronized with the manifest.

The 2026-08-24 review passed Bash syntax, the repository regression suite (`83 catalog tools`), generated catalog consistency, a fresh PTY open/cancel run, public HTTP checks, and local link/asset resolution.

## What is not complete

aiup is not a finished cross-platform or tagged 1.0 product:

- Linux and Windows are documented stubs.
- There is no tagged release or packaged installer; installation uses the live launcher.
- There is no repository CI workflow. Current validation is local and intentionally small relative to the Bash runtime.
- Catalog/provider maintenance is ongoing as upstream tools, installers, and trust requirements change.
- The public site still uses TUI media captured on 2026-08-20, before the current navigation, dynamic views, detected inventory, collapsed-category search, action badges, and result classifications.

## Site status

`https://aiup.neuman.dev` is live from the established Cloudflare Pages project and the current source commit has a successful Pages check. The static page, metadata, headers, crawler files, catalog JSON, and referenced assets resolve successfully.

The site is therefore **live and mechanically complete as a small product poster**, but it is **not content-current or visually complete** until the TUI media is replaced and the refreshed desktop/mobile presentation receives visual review. An HTTP 200 and source-level responsive CSS are not browser/device or owner acceptance.

## Media decision

Replace the current GIF and TUI stills. Keep the logo, favicon, Open Graph image, and restrained poster layout unless a separate brand review finds a real problem.

The replacement set should be captured from the real current TUI, not recreated as an illustration:

1. `aiup-list.gif` — compact overview, a query that finds a row inside a collapsed category, preview visibility, then a clean cancel.
2. `aiup-list-collapsed.png` — current full-screen overview with current categories, counts, border, and navigation hints.
3. `aiup-list-homebrew.png` — focused Homebrew/recommended view with current action labels.
4. `aiup-list-adopt.png` — the real pre-action adoption confirmation, cancelled before mutation.
5. Optional `aiup-list-search.png` — a still that makes collapsed-category search obvious if the GIF does not communicate it clearly.

Capture requirements:

- use one named source commit and record it with the capture;
- use a deterministic public-demo terminal size and fzf color configuration;
- show only public-safe managed/demo data—no personal paths, account data, or private inventory;
- perform no install, update, remove, or adoption during capture;
- verify the GIF loop, still readability, alt text, desktop layout, mobile layout, and reduced-motion presentation before calling the site current.

## Next work, in order

1. Refresh and accept the public TUI media set, then update the site and README together.
2. Define the macOS stability contract and decide whether the next milestone is a tagged pre-1.0 release.
3. Add CI for syntax, regression tests, and generated-doc drift only after explicitly approving the recurring GitHub workflow.
4. Choose whether Linux or Windows is genuinely next; do not call aiup cross-platform until one is implemented and accepted.

The product should remain maintenance-led after the media/release pass. New catalog breadth is lower priority than trustworthy lifecycle behavior for existing entries.
