# aiup public site

Static files for **https://aiup.neuman.dev**. Cloudflare Pages serves this
directory through the repository's existing GitHub-connected publication path.
Do not publish it directly with Wrangler.

## Architecture and content ownership

The homepage is deliberately a minimal GitHub-first stage:

- `index.html` presents the aiup lockup, the continuously looping TUI animation, its
  reduced-motion poster, and one GitHub repository destination;
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

`README.md` is the public explanatory destination for installation, product
behavior, catalog scope, lifecycle, and safety. `scripts/sync-public-docs`
continues to generate README/catalog documentation, `site/catalog.json`, and
the canonical media mirror; it does not inject marketing or catalog markup
into `site/index.html`.

The page has no JavaScript. The default GIF, reduced-motion picture source, and
GitHub destination therefore remain useful without a runtime behavior layer.
The animation includes an infinite-loop NETSCAPE extension and repeats its six-state
narrative continuously. Because its expanded narrative lasts longer than five seconds and no
playback control is present by owner direction, the page has a known WCAG 2.2.2
limitation and does not claim complete WCAG conformance.

## Validate

From the repository root:

```bash
scripts/sync-public-docs
scripts/check-site
scripts/capture-media --check
scripts/build-brand-assets --check
```

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
