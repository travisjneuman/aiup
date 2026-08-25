# Scope, completion, and next work

Status date: **2026-08-25**

Current version: **2026.08.25-02**

## Current product scope

aiup is a local-first, macOS-only Bash TUI. The current implementation can:

- scan installed managed tools and update only what is present;
- require and maintain fzf as interactive infrastructure;
- install, update, remove, or adopt catalog items through explicit actions;
- browse the managed catalog, detected-only local software, and Homebrew inventory through focused views;
- search inside collapsed categories and restore a clean picker after provider actions;
- avoid passing `--zap` or directly deleting `~/Library` when an existing app is handed to Homebrew, without claiming universal vendor behavior;
- check official desktop-app metadata before downloading a replacement and validate the replacement before activation;
- keep generated catalog documentation synchronized with the manifest;
- install publicly without probing a maintainer checkout or personal path;
- refresh and validate the public runtime plus its matching catalog manifest before atomically activating one immutable generation;
- retain the previous complete generation as recovery evidence without executing it as an offline fallback;
- fail closed on offline, failed, empty, invalid, mismatched, partial, locked, or unactivatable public refreshes; and
- keep local-checkout execution behind an explicit non-empty `AIUP_SOURCE_PATH` opt-in.

The public support baseline is macOS 14+ with Bash 3+, Python 3, and curl. Individual products can impose stricter constraints recorded in the [dated 83-entry accuracy audit](catalog-accuracy-2026-08-25.md). That audit left 81 managed entries with executable contracts.

## Current limitations

- Linux and Windows are not implemented.
- There is no tagged release or packaged installer; installation uses the live launcher.
- A normal public invocation is not offline-capable. It refreshes from GitHub and refuses to execute a stale cache. Offline development requires an explicit local checkout path.
- There is no repository CI workflow. Current validation is local.
- Catalog/provider maintenance is ongoing as upstream tools, installers, macOS floors, and trust requirements change.
- Desktop and 375px browser presentation passed independent review. Safari, physical devices, screen readers, and assistive-technology acceptance have not been claimed.

## Site and publication status

The static product site at [aiup.neuman.dev](https://aiup.neuman.dev/) covers product state, per-run activation, the real TUI, generated catalog scope, safety/privacy, requirements, installation, FAQ, and durable source/documentation links. Essential content remains usable without JavaScript. The site has no framework, external runtime dependency, analytics, cookies, tracker, or service worker.

`scripts/check-site` validates metadata, JSON-LD, manifest and sitemap parsing, local references, ids and anchors, image dimensions, generated version/count/category facts, reduced-motion wiring, headers, accepted media mirrors, and public-safety boundaries. `scripts/sync-public-docs` owns the site catalog summary as well as the README catalog block, generated catalog documents, catalog JSON, and media mirrors.

The accepted site source was published at `677e1ed2aa245c1bffdcd5835b91ba1b73d58883` through the established GitHub-connected Cloudflare Pages path. Authenticated provider receipt `1a3f288d-3dfb-4a82-a0be-b2799a43acc7` and exact public-HTTP readback were verified separately. Desktop and 375px browser review then passed without a corrective source change. Source, GitHub, provider, public HTTP, browser/device, and owner evidence remain distinct claims.

## Media and brand status

The accepted color-faithful real-TUI media was published at `4c1d980d68c2b0d22592ae3a4e587b603c598156` from capture source `04fe3b62c2d6d665774097a582677cae08c50ce4`. It uses a 128 × 40 PTY, 1280 × 720 output, JetBrains Mono Nerd Font Mono, the production indexed category palette, fixed fzf chrome colors, and public demo indexes. Exact provenance, hashes, dimensions, timing, and limitations are in [`media/README.md`](media/README.md) and [`media/capture-manifest.json`](media/capture-manifest.json).

The earlier muted media at `d629ca3b92a074de9f0ad99d7b1781c5036ae06e` remains truthful rejected historical evidence. Inherited `NO_COLOR=1` caused fzf to strip the production indexed palette at the PTY boundary. The accepted capture removes that inherited variable inside the capture session and verifies raw SGR styles plus expected raster/GIF colors.

The brand suite retains the open terminal, chevron, underscore, and cyan/mint/purple identity. It includes scalable sources, favicon/PWA/maskable derivatives, 1200 × 630 website Open Graph art, and the accepted 1280 × 640 GitHub social-preview image. The archived original remains byte-identical. See [`../site/brand/README.md`](../site/brand/README.md).

## Repository and community status

Issues are the public intake surface. Bug reports and catalog/tool requests have structured forms; pull requests have a scoped checklist. Contribution, support, and security policies are published at the repository root. Empty Wiki and Projects surfaces are disabled, Discussions remain disabled, and no release or CI workflow has been manufactured.

The generated Homebrew `recommended` blurb still says “switch to Homebrew without losing settings.” That runtime-provided wording is broader than aiup's documented guarantee. The accurate contract is that aiup does not pass `--zap` or directly delete `~/Library`, while Homebrew and vendor behavior may vary. [Issue #1](https://github.com/travisjneuman/aiup/issues/1) tracks the canonical runtime/catalog correction.

Future tagged-release, CI, and cross-platform decisions remain separate scopes. Catalog breadth is lower priority than trustworthy lifecycle behavior for existing entries.
