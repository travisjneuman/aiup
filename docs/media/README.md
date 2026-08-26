# TUI media provenance

`docs/media/` is the canonical product-media source. `scripts/capture-media`
copies all six assets byte-for-byte into `site/media/`, and
`scripts/capture-media --check` rejects mirror, hash, dimension, palette, frame,
duration, continuous-playback, semantic-sequence, or provenance drift.

The current set was captured from source commit
`c15f3366dc96d3b8440e2359ef46d64ec229e87b`. Reproduce and verify it with:

```bash
NO_COLOR=1 scripts/capture-media --source-commit c15f3366dc96d3b8440e2359ef46d64ec229e87b
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

The six-frame 10.78-second GIF contains a broader real-product narrative:

1. collapsed catalog overview — 1,040 ms;
2. Gemini search with installed/update lifecycle details — 2,070 ms;
3. expanded Homebrew hierarchy with reviewed recommendations — 1,800 ms;
4. Raycast on-disk / switch-to-Homebrew context — 2,070 ms;
5. the safe `[y/N]` pre-action confirmation, answered `n` — 2,300 ms; and
6. a stable final catalog overview — 1,500 ms.

The prior four-frame GIF used 900, 1,800, 900, and 1,300 ms dwells (4,900 ms
total). Retained overview, Gemini, and closing dwells were retimed from those
values with a 1.15 multiplier as the baseline; new states receive comparable
readable dwell. The immediately preceding six-frame asset had SHA-256
`190941c2f5c9fc203e95efb26e290db2a9d0f689be24fd7dc525719b8125d826`,
contained no NETSCAPE loop extension, and played once. The current asset keeps
the same six decoded frames, order, dimensions, colors, and 10,780 ms timing,
but Pillow `loop=0` adds a NETSCAPE extension with loop count zero so the
narrative repeats continuously.

The poster is pixel-equivalent to the static search state and is selected only
by `prefers-reduced-motion: reduce`. Documentation stills retain the collapsed,
search, Homebrew/Raycast, and pre-adoption states; the website uses only the
GIF/poster pair, with the GIF as its sole default media. The site has no
playback control or JavaScript. Because the owner-directed animation exceeds
five seconds without a control, this is a documented WCAG 2.2.2 limitation and
the site does not claim complete WCAG conformance.

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
| `aiup-list.gif` | 508,634 | `5e27e415507d679fa6959f9ad316bdaae0580587d474d3f1a71d992739b53296` |
| `aiup-list-collapsed.png` | 136,615 | `b7a637004d4be8933f49156214c88d49de44cc781c17d4854c0addd8d88ca998` |
| `aiup-list-search.png` | 152,728 | `abf9323351f5a702742180ad2177aa11d877fe48d1b41d5c19f42c268451704b` |
| `aiup-list-poster.png` | 152,724 | `9b985ca0daf6e5075fd0b2042069782a502944f6e92ab4a6dc3a9ab56bcf52e9` |
| `aiup-list-homebrew.png` | 169,412 | `fbce2edf3ba441d6110b28f5af11a17f0b33e0646139daaf36b36aaad9f94d5a` |
| `aiup-list-adopt.png` | 60,351 | `756966defd49edaff711f9b74fe09f5eb5be774775460a6af55275be4fe48ae5` |

Schema 3 / capture contract `2026-08-26-05` records exact font hashes, profile
values, PTY matrix results, reference comparison evidence, semantic PTY styles,
rendered pixel evidence for every GIF state, observed fixture commands,
dimensions, per-frame durations, semantic sequence, and continuous/infinite-loop metadata.
