# aiup website video

Up: [docs/media/README.md](../../docs/media/README.md).

`film.py` renders `docs/media/aiup-brag.mp4` and its poster from the real
Terminal screenshots. It needs Python 3 with Pillow and numpy, and ffmpeg.

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

Every AI tool updates a different way. aiup is one list for all of them.

## Scenes

| Time | Scene | On screen |
| --- | --- | --- |
| 0.0 to 3.5 s | Hook | "Every AI tool updates a different way." Five real update commands type out one after another. |
| 3.5 to 6.5 s | Reveal | `$ aiup` types out, then the logo and "One list for all of them." |
| 6.5 to 10.5 s | List | The collapsed list. "261 tools. 20 categories." The Updates row is outlined. |
| 10.5 to 14.0 s | Search | The Gemini search. "Type to find any tool." The query and the keys line are outlined. |
| 14.0 to 17.5 s | Asks first | The `[y/N]` prompt. "It asks first." |
| 17.5 to 21.5 s | End | Logo, "Free and open source, for macOS.", aiup.neuman.dev, github.com/travisjneuman/aiup. |

## Sound

A short A minor loop at 120 BPM: pad chords, bass and plucked notes, a kick
and claps after the logo lands, typing clicks under the commands, a whoosh at
each cut and a bell on each outline. All of it is made in `film.py`.

## Settings

1920×1080 at 30 fps, 21.5 seconds. libx264 `slow`, CRF 23 with a 1,800 kb/s
cap, AAC 160 kb/s, `+faststart`. Frame 0 is the poster frame (the List scene at
9.6 s), so players show it before you press play.

`share-copy.txt` has short text to post with the video.
