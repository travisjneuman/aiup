# TUI media provenance

`docs/media/` is the canonical product-media source. `scripts/capture-media`
copies the six published assets byte-for-byte into `site/media/`, and
`scripts/capture-media --check` rejects any duplicate drift. The catalog sync
script repeats that one-way media sync alongside generated catalog output.

The current set was captured from source commit
`be76e09420e8a2d39b7be259b30be47186994473`, after the bounded launcher-retention
commit `94ae5f964ebd3133ba260125d3e3311e3ceec3a9`. Reproduce it from that source with:

```bash
scripts/capture-media --source-commit be76e09420e8a2d39b7be259b30be47186994473
scripts/capture-media --check
```

The capture drives the real `macos/aiup list` command, real fzf 0.74.3 picker,
current row formatter, current preview command, current search reload binding,
current adoption confirmation, and current cancelled-result summary. A marked
repository-local fixture supplies deterministic public demo indexes: 81 managed
entries, five Homebrew extras plus two recommendations, and eight detected-only
items split into 2 app, 2 npm, 1 uv, and 3 PATH rows. Gemini and Continue are
active, n8n is npm-managed, GPT4All is maintenance-only, and OMP/Plandex are absent.

Capture settings are 128 × 40 terminal cells rendered to 1280 × 720 pixels,
JetBrains Mono Nerd Font Mono Regular at 15 px, `en_US.UTF-8`, navy/mist terminal
colors, and the fixed cyan/mint/purple fzf palette recorded in
`capture-manifest.json`. The four-frame 4.9-second GIF contains stable real states:
collapsed overview, Gemini search and update preview, restored collapsed overview,
and the real cancelled result. `aiup-list-poster.png` is the equivalent static
search state used for reduced motion.

The fixture puts a rejecting `brew` executable first on PATH. It records read-only
queries and exits nonzero for install, upgrade, uninstall, trust, or tap mutation.
The adoption session stops at its first `[y/N]` prompt. No real catalog package is
installed, updated, removed, adopted, or trusted; no host inventory is scanned.
The renderer rejects personal home paths, usernames, hostnames, private project
names, OMP/Plandex rows, and the retired settings-survival claims before writing.

The output is a deterministic rendering of the real PTY/ANSI stream rather than a
screenshot of a specific terminal application's window chrome. Exact font, media
hashes, dimensions, frame count/duration, palette, and observed fixture commands
are in `capture-manifest.json`.
