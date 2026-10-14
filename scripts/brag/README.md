# aiup website video

Up: [docs/media/README.md](../../docs/media/README.md).

`film.py` renders `docs/media/aiup-brag.mp4` and its poster from real aiup
output and the real Terminal screenshots. It needs Python 3 with Pillow and numpy, and ffmpeg.

```bash
python3 scripts/brag/film.py WORK full --fonts /path/to/fonts
```

WORK needs an `assets/` folder with `lockup.png` (from `site/brand/derived`)
and `aiup-list-collapsed.png`, `aiup-list-search.png` and `aiup-list-adopt.png`
(from `docs/media`). The fonts folder needs `segoeuib.ttf`, `segoeui.ttf` and
`CascadiaMono.ttf`. `stills` writes review sheets instead of a video, and
`audio` writes only the soundtrack. Copy `brag.mp4` and `brag.jpg` to
`docs/media/aiup-brag.mp4` and `docs/media/aiup-brag-poster.jpg`, then run
`scripts/sync-public-docs` to mirror them into `site/media`.

## The idea

Every AI tool updates a different way. aiup is one command for all of them.
Plain `aiup` updates everything it finds on your Mac. `aiup list` opens the
catalog, where you browse, search and switch tools.

## Scenes

| Time | Scene | On screen |
| --- | --- | --- |
| 0.0 to 3.5 s | Hook | "Every AI tool updates a different way." Five real update commands type out one after another. |
| 3.5 to 6.5 s | Reveal | `$ aiup` types out, then the logo and "One command for all of them." |
| 6.5 to 13.5 s | Run | "Run aiup. It updates your tools and Homebrew packages." A Terminal window types `aiup` and prints the update report from a real run (see below). The Updated and Unchanged lines are outlined. |
| 13.5 to 16.0 s | List | `$ aiup list` types out. "Opens the full catalog in one list." |
| 16.0 to 20.0 s | Browse | The collapsed list. "260+ tools. 20+ categories." The Updates row is outlined. |
| 20.0 to 24.0 s | Search | The Gemini search. "Type to find any tool." The query and the keys line are outlined. |
| 24.0 to 28.0 s | Asks first | The `[y/N]` prompt. "It asks first." |
| 28.0 to 32.0 s | End | Logo, "Free and open source, for macOS.", aiup.neuman.dev, github.com/travisjneuman/aiup. |

## The run scene

Recording a real `aiup` run would update the tools on the machine doing the
recording, so the run scene draws the Terminal window instead. Every line in it
is what aiup printed for my real update run on 2026-10-06, from that run's JSON
log: 122 tools in 149 seconds, 7 updated, 1 updated itself (the Claude app),
114 unchanged. The report uses the same layout, colors and 100-column width
aiup uses. The progress line shows the first 25 tools of the run with elapsed
times added up from each tool's duration, and the run log path is shortened to
`~`. The constants that hold this data start with `RUN_` in `film.py`.

The counts on the Browse scene are rounded down ("260+", "20+") so the video
stays true as the catalog grows.

## Sound

A short A minor loop at 120 BPM: pad chords, bass and plucked notes, a kick
and claps after the logo lands, typing clicks under the commands, soft
ticks under the progress line, a chime when the report prints, a whoosh at
each cut and a bell on each outline. All of it is made in `film.py`.

## Settings

1920×1080 at 30 fps, 32 seconds. libx264 `slow`, CRF 23 with a 1,800 kb/s
cap, AAC 160 kb/s, `+faststart`. Frame 0 is the poster frame (the finished run
report at 12.6 s), so players show it before the video starts.

`share-copy.txt` has short text to post with the video.
