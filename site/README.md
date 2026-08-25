# aiup public site

Static files for **https://aiup.neuman.dev**. Cloudflare Pages serves this
directory through the repository's existing GitHub-connected publication path.
Do not publish it directly with Wrangler.

## Architecture and content ownership

The site is one semantic HTML page plus a branded static 404:

- `index.html` owns the visible product explanation, landmarks, install path,
  TUI captions, safety boundaries, requirements, FAQ, metadata, and JSON-LD;
- `styles.css` owns the dependency-free responsive visual system;
- `site.js` progressively enhances command copying and animation control;
- `catalog.json` is generated from `macos/aiup`, not maintained by hand;
- `media/` is a byte-identical mirror of the accepted canonical files in
  `docs/media/`;
- `brand/` contains the accepted canonical and derived brand suite;
- `robots.txt`, `sitemap.xml`, `llms.txt`, `manifest.webmanifest`, `_headers`,
  and `_redirects` own crawler, installability, header, and routing behavior.

The index's `SITE-CATALOG` block, catalog count, and product version are updated
by `scripts/sync-public-docs`. Essential product, catalog, safety, requirement,
and FAQ content stays in HTML and remains usable without JavaScript.

## Validate

From the repository root:

```bash
scripts/sync-public-docs
scripts/check-site
scripts/capture-media --check
scripts/build-brand-assets --check
```

`scripts/check-site` uses Python's standard library. It validates metadata,
JSON-LD, manifest JSON, sitemap XML, local assets, image dimensions, ids and
anchors, generated catalog facts, reduced-motion wiring, media mirrors,
security headers, and public-safety boundaries without adding dependencies.

For a bounded local preview, serve this existing directory from the canonical
checkout and use the T3 collaborative preview. Stop the server afterward. Do
not install or run a separate browser payload.

## Publication

Completed site work is committed and pushed to the maintainer default branch.
The existing Cloudflare Pages integration then publishes `site/`. Keep the
source push, Pages provider receipt, public HTTP readback, browser/device
evidence, and owner acceptance as separate claims. No direct Cloudflare
publication, new resource, analytics, tracker, cookie, or service worker is
part of this site.

The checked-in media represents aiup `2026.08.25-02` and its 81-entry catalog.
Capture and brand provenance live in [`docs/media/README.md`](../docs/media/README.md)
and [`brand/README.md`](brand/README.md).
