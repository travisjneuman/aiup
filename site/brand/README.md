# aiup brand assets

Up: [site/README.md](../README.md). Not here: product screenshots and GIF capture ([docs/media/README.md](../../docs/media/README.md)).

`original/aiup-logo.png` is the archived pre-vector source and remains
byte-for-byte unchanged at SHA-256
`726b5f4c1a9e518055bbdeb1807c6bb42700fd0bb5631fb514e3bd9c5f39b5c8`.
It is preservation evidence, not the derivative source.

The canonical scalable sources are in `source/`:

- `mark.svg`, `wordmark.svg`, and `lockup.svg` define the transparent primary identity;
- `favicon.svg` removes the three status dots so the terminal, chevron, and underscore remain recognizable at 16 × 16;
- `app-icon.svg` supplies the Apple and ordinary PWA icons;
- `maskable-icon.svg` keeps the visible mark inside the central 60% safe region.

The two social cards, `derived/og.png` (1200 × 630) and
`derived/github-social-preview.png` (1280 × 640), come from
`scripts/build-social-cards`. It puts the lockup and the line "Your tool stack.
One list." next to the real collapsed list screenshot from `docs/media`. The
cards have no tool count, so they stay accurate as the catalog grows. Run it
after new screenshots, then update the two entries in `brand-manifest.json`.
The old SVG card sources are kept in `source/archive/` and are no longer used.

Run `scripts/build-brand-assets` from the repository root to render the other files in
`derived/`, the three-size `favicon.ico`, and the byte-identical site-root icon
mirrors. Rendering uses the macOS `sips` SVG path already present on the supported
platform, then Pillow normalizes PNG mode and encoding. `scripts/build-brand-assets
--check` verifies the archived original hash, source/derived SVG identity, exact
raster dimensions, alpha range, ICO sub-images, root mirrors, social-preview size,
and `brand-manifest.json` hashes.

The palette follows the real TUI: navy `#0b0c23`, mist `#e8e9ff`, cyan
`#4de0ff`, mint `#4ef0c4`, purple `#c084fc`, with pink and amber status accents.
Transparent mark/wordmark/lockup assets are intended for dark surfaces; the PWA,
maskable, OG, and GitHub social assets include their own dark background.
