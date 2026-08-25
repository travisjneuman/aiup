# TUI media provenance

`docs/media/` is the canonical product-media source. `scripts/capture-media`
copies the six published assets byte-for-byte into `site/media/`, and
`scripts/capture-media --check` rejects any duplicate drift. The catalog sync
script repeats that one-way media sync alongside generated catalog output.

The corrected color-faithful set was captured from source commit
`04fe3b62c2d6d665774097a582677cae08c50ce4`, after the bounded
launcher-retention commit `94ae5f964ebd3133ba260125d3e3311e3ceec3a9`. Reproduce it from that source with:

```bash
NO_COLOR=1 scripts/capture-media --source-commit 04fe3b62c2d6d665774097a582677cae08c50ce4
scripts/capture-media --check
```

The explicit `NO_COLOR=1` parent is a regression probe. The capture session
removes that inherited variable before starting the real TUI, because fzf
otherwise consumes aiup's ANSI input styles and emits a flattened PTY stream.
That was the diagnosed cause of the owner-rejected media published in
`d629ca3b92a074de9f0ad99d7b1781c5036ae06e`: the list file contained the
production `CSI 38;5;<index> m` colors, but the fzf PTY stream contained only its
configured chrome colors. The custom terminal parser and PNG renderer therefore
never received category colors to preserve.

With the correction, the raw stream uses fzf-composed forms such as
`CSI ;38;5;171;48;2;11;12;35 m`; parsed cells retain xterm index 171 for
`coding-agents`, and raster pixels retain its exact `#d75fff` RGB. Schema 2 of
`capture-manifest.json` records the corresponding raw escape forms, styled-cell
counts, and raster pixel counts for every visible category plus the Homebrew,
selection, query-highlight, preview-label, installed, and absent states.

The capture drives the real `macos/aiup list` command, real fzf 0.74.3 picker,
current row formatter, current preview command, current search reload binding,
current adoption confirmation, and current cancelled-result summary. A marked
repository-local fixture supplies deterministic public demo indexes: 81 managed
entries, five Homebrew extras plus two recommendations, and eight detected-only
items split into 2 app, 2 npm, 1 uv, and 3 PATH rows. Gemini and Continue are
active, n8n is npm-managed, GPT4All is maintenance-only, and OMP/Plandex are absent.

Capture settings are 128 × 40 terminal cells rendered to 1280 × 720 pixels,
JetBrains Mono Nerd Font Mono Regular at 15 px, `en_US.UTF-8`, navy/mist terminal
colors, and the fixed cyan/mint/purple fzf chrome palette recorded in
`capture-manifest.json`. The real input palette remains authoritative: blue,
magenta, pink, soft blue, cyan, green, orange, yellow, Homebrew golds, and detected
gray. The Homebrew still now expands the real parent and child hierarchy before
selecting Raycast, so its 214/208/176/178/180/220 family and current action preview
are visible together.

The four-frame 4.9-second GIF contains stable real states: collapsed overview,
Gemini search and update preview, restored collapsed overview, and the real
cancelled result. It uses Pillow's deterministic maximum-coverage 256-color
quantizer without dithering; the checker permits at most an 8-point RGB distance
for material GIF colors. `aiup-list-poster.png` is pixel-equivalent to the static
search state used for reduced motion.

The fixture puts a rejecting `brew` executable first on PATH. It records read-only
queries and exits nonzero for install, upgrade, uninstall, trust, or tap mutation.
The adoption session stops at its first `[y/N]` prompt. No real catalog package is
installed, updated, removed, adopted, or trusted; no host inventory is scanned.
The renderer rejects personal home paths, usernames, hostnames, private project
names, OMP/Plandex rows, and the retired settings-survival claims before writing.

The output is a deterministic rendering of the real PTY/ANSI stream rather than a
screenshot of a specific terminal application's window chrome. A separate
non-mutating cmux/xterm-256color comparison of the same fixture confirmed the same
category hierarchy. The production adoption output emits `[INFO]`, `[WARN]`, and
confirmation roles textually, without role-specific SGR; the capture preserves
that limitation rather than adding post-capture color.

Current canonical hashes and sizes are:

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `aiup-list.gif` | 171,298 | `cedd7a20278578debd812186f2e31db7e3bf05da789fa8b0e6d696c1a34592fd` |
| `aiup-list-collapsed.png` | 110,312 | `d81eb71b853f3e4d7c8e4de41e97602d36fc3462d6ee8225f7cc7ec8437a9fd8` |
| `aiup-list-search.png` | 114,291 | `619b2cce700f95761e53a7a58f9440f41309f8f1cc110b9d607bab9253c0a8ef` |
| `aiup-list-poster.png` | 114,287 | `8bac9862c047efa434a9452d0e19a9a0c56ea7300eecc8d749e350499bfe2bfb` |
| `aiup-list-homebrew.png` | 122,208 | `0b12f88f56c67cde212867a6f94750a5328ae6192ac45121092b6f6742b1561f` |
| `aiup-list-adopt.png` | 28,343 | `bdea45dade438aeb683530b981bbb3c4997827d142ff70a108218158bb8ffc5f` |

Exact font provenance, dimensions, frame count/duration, palette evidence, and
observed fixture commands remain machine-readable in `capture-manifest.json`.
