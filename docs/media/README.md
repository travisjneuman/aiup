# TUI media provenance

`docs/media/` is the canonical product-media source. `scripts/capture-media`
copies all six assets byte-for-byte into `site/media/`, and
`scripts/capture-media --check` rejects mirror, hash, dimension, palette, frame,
or provenance drift.

The current set was captured from source commit
`8e596312e77a86b69dd27ff370381506666e1035`. Reproduce and verify it with:

```bash
NO_COLOR=1 scripts/capture-media --source-commit 8e596312e77a86b69dd27ff370381506666e1035
scripts/capture-media --check
scripts/capture-media --check-layout
```

The explicit `NO_COLOR=1` parent remains a regression probe. The capture session
removes it before starting fzf so aiup's production indexed category colors reach
the PTY stream.

## What is real and what is reproduced

- The process is the real `macos/aiup list` command, real fzf 0.74.3 picker, real
  row formatter, preview command, query reload, category navigation, preview
  toggle, cancellation, and adoption confirmation.
- Catalog and inventory content comes from the deterministic public fixture in
  `scripts/fixtures/capture`: 81 managed entries, five Homebrew extras, two
  recommendations, and eight detected-only rows. It is not host inventory.
- The rasterizer consumes the real PTY/ANSI stream. It does not construct a mock
  TUI or redraw aiup rows after capture.
- The macOS window frame is a sanitized reproduction of Terminal chrome. The
  traffic lights and title bar are reproduced; the title contains only `aiup`,
  the command, and the public 100×30 cell geometry.
- The actual Terminal `Homebrew` profile was read back before capture: Andale
  Mono 16 pt with antialiasing, block green cursor, 90%-opaque black background,
  green normal/bold text, and blue selection. Menlo supplies Terminal-like
  fallback glyphs for box drawing, triangles, and spinners.
- The live shell's actual Catppuccin fzf options are replayed: `#1e1e2e`
  background, `#313244` selected row, pink header/highlight, purple prompt, and
  mist foreground. The previous capture-only cyan border and purple labels are
  gone. aiup's intentional indexed category and state colors remain unchanged.

The primary capture uses an ordinary 100×30 PTY rendered at 2× Retina density to
2016×1208 pixels, including chrome. It does not resize, maximize, fullscreen, or
reposition Terminal. The layout checker also drives 60×18, 80×24, 100×30,
128×40, and 167×47 PTYs plus a live 167×47 → 60×18 → 100×30 resize sequence.
All five sizes retain 11 collapsed catalog rows. The 60×18 preview starts hidden
and its `ctrl-/` toggle is verified; the other sizes start with a responsive
one-third preview.

The four-frame 4.9-second GIF contains real states: collapsed overview, Gemini
search/update preview, restored overview, and cancellation. The poster is
pixel-equivalent to the static search state for reduced motion. Documentation
stills retain the collapsed, search, Homebrew, and pre-adoption states; the
website uses only the GIF/poster pair, with the GIF as its sole default media.

## Safety and sanitization

The fixture's rejecting `brew` is first on PATH. It records read-only queries and
rejects install, upgrade, uninstall, trust, and tap mutation. Adoption stops at
the first `[y/N]` prompt. No real package is installed, updated, removed,
adopted, or trusted, and no host inventory is scanned.

Before writing, the renderer rejects personal home paths, usernames, hostnames,
private project names, private fixture rows, and retired claims. The PNG title,
GIF frames, manifest, alt text, and this documentation publish no host username,
hostname, private path, or actual installed inventory.

## Historical visual decisions

The explicit 2026-08-25 owner acceptance of media commit
`4c1d980d68c2b0d22592ae3a4e587b603c598156` from source
`04fe3b62c2d6d665774097a582677cae08c50ce4` is retained as historical
provenance but is **superseded** by the latest owner direction. It is not current
visual acceptance. The associated expanded-site visual review is likewise
historical rather than acceptance of this rebuilt media. The earlier muted set at
`d629ca3b92a074de9f0ad99d7b1781c5036ae06e` remains rejected historical
evidence of the inherited-`NO_COLOR` failure.

Current canonical hashes and sizes are:

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `aiup-list.gif` | 267,545 | `472baf1540385a8a03209515f9b873f59610b8b35981442a5d9523535c74d27f` |
| `aiup-list-collapsed.png` | 136,615 | `8e476458ba55fc324c2a84cdc5da8180a033fd2de5718d990788631d8f8cf337` |
| `aiup-list-search.png` | 152,728 | `c199fe6246540f461dc5c015813cf16109b5e854415219ec1a9a49993242c3b5` |
| `aiup-list-poster.png` | 152,724 | `9d3f6a59af3da797c6be1d6c6d617001527e2c3b40ab56159069af01c8c0a057` |
| `aiup-list-homebrew.png` | 169,412 | `ff27ef9258ee1151e7a07f53e34590d46dc0ef4a63546aa0115338247817b835` |
| `aiup-list-adopt.png` | 60,351 | `d8e6d1ec1839ce34de30e7ee2a314f735461ce3ec67ce91fc31f8efdea5482a2` |

Schema 3 of `capture-manifest.json` records exact font hashes, profile values,
PTY matrix results, reference comparison evidence, semantic PTY styles, rendered
pixel evidence, observed fixture commands, dimensions, frames, and duration.
