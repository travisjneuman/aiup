# TUI media provenance

`docs/media/` is the canonical product-media source. `site/media/` holds
byte-for-byte copies of the same six files. `scripts/sync-public-docs` (without
`--skip-media`) mirrors them when the bytes differ.

## Current set (2026-10-14)

I captured the current GIF and screenshots on 2026-10-14 from a real macOS
Terminal window running `macos/aiup list` against the public capture fixture.
They show the 2026-10-14 list layout: category names, installed bars, state
marks, and the framed picker.

How they were made:

- A small launcher opened a Terminal window at 100×30 cells with the Homebrew
  profile, the Catppuccin fzf colors in `FZF_DEFAULT_OPTS`, and
  `AIUP_CAPTURE_FIXTURE_DIR` pointed at `scripts/fixtures/capture`. HOME, TMPDIR
  and the aiup state directory pointed at a throwaway work folder.
- Keys were sent to that window (search text, arrow keys, Return, `n`), and each
  state was saved with `screencapture -x -o -l<window id>`. Nothing was redrawn
  or edited after capture. The window title shows only `aiup`, the command, and
  the cell size.
- The GIF is built from those PNGs with Pillow: 255 colors per frame, one extra
  transparent index for the rounded window corners, `loop=0` so it repeats.

The six GIF states, 10,780 ms in total:

1. collapsed catalog overview (1,040 ms);
2. Gemini search with its update and install details (2,070 ms);
3. the expanded Homebrew hierarchy with Suggestions selected (1,800 ms);
4. Raycast's switch-to-Homebrew context (2,070 ms);
5. the `[y/N]` adoption prompt, which I answered `n` (2,300 ms);
6. the collapsed overview again (1,500 ms).

The poster is the same image as the search still. The site and README show it
only to visitors who ask for reduced motion. The animation runs longer than five
seconds with no playback control, which is a known WCAG 2.2.2 limitation, so the
site does not claim full WCAG conformance.

## What is real and what is fixture data

- The command, fzf picker, row formatter, preview, search reload, and adoption
  prompt are the real ones from this repo.
- Catalog and inventory content comes from `scripts/fixtures/capture`: the 261
  manifest entries, a short installed set with demo versions, five Homebrew
  extras, two recommendations, and a few detected-only rows. None of it is
  read from the capture machine.
- The fixture `brew` is first on PATH. It records queries and rejects install,
  upgrade, uninstall, trust, and tap changes. During this capture it saw only
  `brew list --formula --versions`, `brew list --cask --versions`, and
  `brew info --json=v2 --cask raycast`. Nothing was installed, updated, removed,
  adopted, or trusted.
- The log lines on the adoption prompt carry the fixture's fixed timestamp.

## Files

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `aiup-list.gif` | 257,819 | `bffcce1ec2d2f2586971578dceed90a5e70acb2445312aeffe40294e0f248e39` |
| `aiup-list-collapsed.png` | 222,725 | `d13530937aef47784234d058b46d6f4d0fa85183a101595ef7cac9b6c1a3749c` |
| `aiup-list-search.png` | 167,682 | `bf21829f9940451f7a84de401747b9e0480b2d16d7783f970d2e9416759de92e` |
| `aiup-list-poster.png` | 167,682 | `bf21829f9940451f7a84de401747b9e0480b2d16d7783f970d2e9416759de92e` |
| `aiup-list-homebrew.png` | 264,784 | `697bb37170f1bb28cf27a365b428bddd56b22e6f5efb854a793b3fad9e3080de` |
| `aiup-list-adopt.png` | 112,498 | `65ee29d05618007e89197441b2e8032a9e0297d96ad2a8bb1d413d23256c2724` |

All six are 1020×618 pixels. [`capture-manifest.json`](capture-manifest.json)
records the same hashes, the GIF sequence and timing, the fixture commands seen,
and the capture method.

## Previous set and `scripts/capture-media`

The set before this one (2026-08-26, source commit
`c15f3366dc96d3b8440e2359ef46d64ec229e87b`) came from `scripts/capture-media`,
which renders a virtual PTY stream to images with a reproduced Terminal frame at
2016×1208. Its full manifest, with font hashes, profile values, the PTY layout
matrix, and owner acceptance history, is kept at
[`archive/capture-manifest-2026-08-26.json`](archive/capture-manifest-2026-08-26.json),
and the earlier version of this page is in git history.

`scripts/capture-media` still describes that older renderer. Running it would
replace the real Terminal captures with rendered ones, and its `--check` mode
compares against the old manifest format, so do not run it for this set. The
next capture should repeat the real Terminal method above.
