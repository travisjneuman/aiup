# aiup public site

Up: [README](../README.md) · [docs](../docs/README.md). Not here: product screenshots and GIF capture ([docs/media/README.md](../docs/media/README.md)), logo and icon sources ([brand/README.md](brand/README.md)).

Static files for **https://aiup.neuman.dev**. Cloudflare Pages serves this
directory through the repository's existing GitHub-connected publication path.
Do not publish it directly with Wrangler.

## Architecture and content ownership

The homepage is intentionally minimal and points to GitHub:

- `index.html` presents the aiup lockup, a short video about aiup (only its
  poster loads until you press play; no autoplay), the continuously looping TUI
  animation, its reduced-motion poster, one GitHub repository destination, and an exported
  curated-catalog total;
- `styles.css` owns the dependency-free responsive stage without recreating a
  terminal frame around media that already contains sanitized Terminal chrome;
- `catalog.json` remains generated from `macos/aiup` for machine-readable
  discovery and is not rendered on the homepage;
- `media/` remains a byte-identical one-way mirror of `docs/media/`;
- `brand/` contains the accepted canonical and derived brand suite;
- `robots.txt`, `sitemap.xml`, `llms.txt`, `manifest.webmanifest`, `_headers`,
  `_redirects`, metadata, and JSON-LD preserve nonintrusive discovery,
  security, and routing behavior;
- `404.html` provides the static noindex recovery page.

`README.md` is where installation, product behavior, catalog scope, lifecycle,
and safety are explained. `scripts/sync-public-docs`
generates README/catalog documentation, `site/catalog.json`, the Catalog tools
metric in `showcase.json`, and site JSON-LD, social alt catalog context, `llms.txt`,
and the small visible catalog total from one local JSON export. It does not add
a catalog table or marketing sections. The default also mirrors accepted media;
`--skip-media` leaves all media untouched. No invocation regenerates images.
See [public catalog facts](../docs/public-catalog-facts.md).

The page has no JavaScript. The default GIF, reduced-motion picture source, and
GitHub destination therefore remain useful without a runtime behavior layer.
The animation includes an infinite-loop NETSCAPE extension and repeats its six-state
narrative continuously. Because its expanded narrative lasts longer than five seconds and no
playback control is present by owner direction, the page has a known WCAG 2.2.2
limitation and does not claim complete WCAG conformance.

## Refresh public facts

From the repository root, after catalog source edits finish:

```bash
scripts/sync-public-docs --skip-media
```

This is a real write, not a check or dry run. Include its outputs in the same
commit as the source change. Use `scripts/sync-public-docs` without the flag only
when the accepted canonical media should also be copied to `site/media`.

## Validation (only when explicitly requested)

Do not run tests, media checks, or brand generation as an automatic refresh gate.

`scripts/check-site` uses Python's standard library. It validates the minimal
visible contract, metadata and JSON-LD, absence of animation controls and
JavaScript, local references, image dimensions, generated catalog data,
canonical media mirrors,
manifest/robots/sitemap/llms/404 behavior, security headers, and public-safety
boundaries without adding dependencies.

For a bounded local preview, serve this existing directory from the canonical
checkout and use the T3 collaborative preview. Stop the server afterward. Do
not install or run a separate browser payload.

## Publication

Completed site work is committed and pushed to the maintainer default branch.
The existing Cloudflare Pages integration then publishes `site/`. Keep the
source push, Pages provider receipt, public HTTP readback, browser/device
evidence, and owner acceptance as separate claims. No direct Cloudflare
publication, new resource, analytics, tracker, cookie, external font, remote
runtime asset, or service worker is part of this site.

The sole default homepage media is `media/aiup-list.gif`; its static poster is
used only for reduced motion. Capture and brand provenance
live in [`docs/media/README.md`](../docs/media/README.md) and
[`brand/README.md`](brand/README.md).
