# TUI media provenance

`docs/media/` is the canonical product-media source. `site/media/` holds
byte-for-byte copies of the same eight files: the six TUI files below and the
website video with its poster. `scripts/sync-public-docs` (without
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

## Website video (2026-10-14)

`aiup-brag.mp4` is a 21.5 second video for the homepage. It opens on five
different update commands (`brew upgrade`, an npm install, `uv tool upgrade`,
`claude update`, `opencode upgrade`), then shows `aiup` and one list for all of
them. Three short scenes follow, each on a real screenshot from the current
set: the collapsed list, the Gemini search, and the `[y/N]` prompt. It ends on
the logo, aiup.neuman.dev and the GitHub address.

`scripts/brag/film.py` draws every frame with Pillow and pipes them to ffmpeg.
The music and sound effects are made in the same script with numpy, so there
are no stock or licensed sounds. Its README has the scene plan and settings.

- 1920×1080, 30 fps, H.264 with AAC audio, `+faststart`. Integrated loudness
  is about -18 LUFS.
- Frame 0 is the poster frame, so every player shows the same still before you
  press play. `aiup-brag-poster.jpg` is that frame as a JPEG.
- The page loads only the poster. The video loads when you press play. It does
  not autoplay or loop.
- The counts on screen ("261 tools. 20 categories.") are from 2026-10-14. They
  will go out of date as the catalog grows.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `aiup-brag.mp4` | 2,671,285 | `3714c9ef9ce3d2b5f6a771c14e414de58acb8951ed3a59c7d0ab7bd73bd1c514` |
| `aiup-brag-poster.jpg` | 188,871 | `d7ed0c940a6e32b46641702496fd8577c0d247975d8cac6f6a481670302e8c4c` |

## Capturing again

[`scripts/capture-terminal-media`](../../scripts/capture-terminal-media) repeats
the real Terminal method above. Run `scripts/capture-terminal-media --help` for
the full details.

1. `scripts/capture-terminal-media capture <dir>` opens a Terminal window with
   the Homebrew profile at 100×30, runs `macos/aiup list` against the capture
   fixture, sends the keys for each state, and saves one PNG per state into
   `<dir>`. Use a folder outside `/tmp`, preferably outside the repo. The app you
   run it from needs Accessibility, Automation, and Screen Recording permission.
   Leave the keyboard and mouse alone until it finishes, or add `--confirm` to
   check each state by eye before its shot.
2. Look at the PNGs, then run `scripts/capture-terminal-media assemble <dir>`.
   It writes the six files here and updates the hashes, sizes, GIF fields, and
   date in `capture-manifest.json`. It writes nothing if the shots differ in
   size or the GIF would be over 5 MiB.
3. Update the Files table and the dates on this page.
4. Run `scripts/sync-public-docs` to mirror these files into `site/media`.

## Previous set and `scripts/archive/capture-media`

The set before this one (2026-08-26, source commit
`c15f3366dc96d3b8440e2359ef46d64ec229e87b`) came from an older renderer, now
archived at [`scripts/archive/capture-media`](../../scripts/archive/capture-media).
It rendered a virtual PTY stream to images with a reproduced Terminal frame at
2016×1208. Its full manifest, with font hashes, profile values, the PTY layout
matrix, and owner acceptance history, is kept at
[`archive/capture-manifest-2026-08-26.json`](archive/capture-manifest-2026-08-26.json),
and the earlier version of this page is in git history.

Do not run the archived renderer. It would replace the real Terminal captures
with rendered ones, and its `--check` mode compares against the old manifest
format. [`scripts/archive/README.md`](../../scripts/archive/README.md) says more.
