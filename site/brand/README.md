# aiup brand assets

`original/aiup-logo.png` is the archived pre-vector source and remains
byte-for-byte unchanged at SHA-256
`726b5f4c1a9e518055bbdeb1807c6bb42700fd0bb5631fb514e3bd9c5f39b5c8`.
It is preservation evidence, not the derivative source.

The canonical scalable sources are in `source/`:

- `mark.svg`, `wordmark.svg`, and `lockup.svg` define the transparent primary identity;
- `favicon.svg` removes the three status dots so the terminal, chevron, and underscore remain recognizable at 16 × 16;
- `app-icon.svg` supplies the Apple and ordinary PWA icons;
- `maskable-icon.svg` keeps the visible mark inside the central 60% safe region;
- `og.svg` and `github-social-preview.svg` are dedicated large-card compositions without tiny copy.

Run `scripts/build-brand-assets` from the repository root to render every file in
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
