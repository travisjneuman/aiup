# Scope, completion, and next work

Status date: **2026-08-26**

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
- The minimal site contract and asset bytes pass local static validation. The T3 collaborative preview rendered a clean 1280×800 desktop screenshot, reported no page overflow at its comparable 1683×1052 CSS viewport, exposed only the skip and GitHub links in keyboard order with visible focus, and loaded the 2016×1208 poster when the native `<picture>` branch was forced applicable. A 41-second recording of the current GIF covered more than three complete cycles without adding a control to the accessibility tree. T3's 375px viewport-resize operation timed out again and did not apply, so a true mobile render remains unverified. These checks do not replace Safari/physical-device, screen-reader/assistive-technology, or social-preview acceptance. The owner has accepted the current six-state media and minimal site design.

## Site and publication status

The static site at [aiup.neuman.dev](https://aiup.neuman.dev/) is deliberately minimal and GitHub-first. Its visible homepage contains the aiup lockup, the real continuously looping TUI GIF as the sole default product media, a poster only for reduced motion, and one prominent repository link. It contains no playback control or JavaScript. The GitHub README owns installation, explanation, catalog, lifecycle, and safety content. The expanded marketing site and screenshot reel introduced at `677e1ed2aa245c1bffdcd5835b91ba1b73d58883` remain retired.

Metadata, WebSite/SoftwareApplication/Person JSON-LD, the favicon and manifest suite, robots, sitemap, `llms.txt`, static 404 behavior, and security headers remain behind the restrained page. The site has no framework, external runtime asset, external font, analytics, cookie, tracker, or service worker. The retained OG composition uses the established brand derivation and accepted TUI palette; its copy and 81-entry count remain factual.

`scripts/check-site` validates the minimal visible contract, sole GitHub destination, GIF/poster picture, absence of playback controls and external JavaScript, lack of secondary TUI stills and retired sections, exact semantic sequence/timing/playback manifest, metadata and JSON-LD, cache versions, local references, image dimensions, generated catalog data, canonical media mirrors, support files, headers, and public-safety boundaries. `scripts/sync-public-docs` owns the README catalog block, generated catalog documents, catalog JSON, and one-way media mirror; it does not require or inject a visible site catalog block.

Publication remains the established GitHub-connected Cloudflare Pages path; direct Wrangler publication is not part of the project workflow. Source, GitHub, provider-linked check, public HTTP, browser/device, assistive-technology, social-preview, and owner evidence remain distinct claims.

## Media and brand status

The current media is captured from source `c15f3366dc96d3b8440e2359ef46d64ec229e87b`. It uses the real TUI and fzf 0.74.3 at an ordinary 100 × 30 PTY, a measured macOS Terminal/Homebrew profile, the live shell's Catppuccin fzf palette, aiup's production indexed category colors, reproduced sanitized Terminal chrome, and 2016 × 1208 Retina output. The six-frame, 10.78-second sequence covers the overview, Gemini lifecycle state, expanded Homebrew recommendations, Raycast switch context, cancelled `[y/N]` safety boundary, and final overview. Its Pillow `loop=0` encoding includes the NETSCAPE infinite-loop extension and repeats continuously. Exact provenance, hashes, PTY matrix, dimensions, timing, profile evidence, and limitations are in [`media/README.md`](media/README.md) and [`media/capture-manifest.json`](media/capture-manifest.json).

The owner-directed absence of a playback control means the animation's greater-than-five-second autoplay is a known WCAG 2.2.2 limitation. Reduced-motion users receive the static poster through the native `<picture>` media query; the site does not claim complete WCAG conformance.

The explicit 2026-08-25 owner acceptance of media commit `4c1d980d68c2b0d22592ae3a4e587b603c598156` is retained as historical evidence and superseded by the owner's 2026-08-26 acceptance of the current six-state media and minimal design. The earlier muted media at `d629ca3b92a074de9f0ad99d7b1781c5036ae06e` remains rejected historical evidence of inherited `NO_COLOR=1` flattening the indexed palette.

The brand suite retains the open terminal, chevron, underscore, and cyan/mint/purple identity. It includes scalable sources, favicon/PWA/maskable derivatives, 1200 × 630 website Open Graph art, and the accepted 1280 × 640 GitHub social-preview image. The archived original remains byte-identical. See [`../site/brand/README.md`](../site/brand/README.md).

## Repository and community status

The repository is public on `main`. Its current About description is “Local-first macOS TUI to scan, update, install, remove, and browse reviewed AI and developer tools.” Its homepage is `https://aiup.neuman.dev`. The current topics are `ai`, `ai-tools`, `bash`, `catalog`, `cli`, `developer-tools`, `fzf`, `homebrew`, `llm`, `local-first`, `macos`, `package-manager`, `terminal`, `tool-manager`, and `tui`.

Issues are the public intake surface. Bug reports and catalog/tool requests have structured forms; pull requests have a scoped checklist. Contribution, support, and security policies are published at the repository root. Empty Wiki and Projects surfaces are disabled, Discussions remain disabled, and no tag, GitHub release, or Actions workflow has been manufactured. The repository contains the accepted 1280 × 640 GitHub social-preview asset; confirmation of the account-bound GitHub social-preview setting and its deployed rendering remains a separate manual acceptance lane.

The generated Homebrew `recommended` blurb now states aiup's narrow guarantee: aiup does not pass `--zap` or directly delete `~/Library`, while Homebrew and vendor behavior may vary. [Issue #1](https://github.com/travisjneuman/aiup/issues/1) records the correction.

Future tagged-release, CI, and cross-platform decisions remain separate scopes. Catalog breadth is lower priority than trustworthy lifecycle behavior for existing entries.

## Workstream disposition

The current macOS tool, public repository, minimal site, continuously looping media, brand/discovery suite, and public/private documentation workstream is complete for its dated scope. No additional implementation thread is required now. True 375px/mobile and Safari/physical-device rendering, actual OS reduced-motion, screen-reader/assistive-technology review, deployed social-preview acceptance, and reconsideration of the acknowledged WCAG 2.2.2 motion limitation are optional future release-hardening lanes rather than blockers to this closure.
