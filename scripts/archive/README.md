# Archived scripts

These scripts are kept for provenance. Nothing in the repo calls them.

## `capture-media`

`capture-media` made the 2026-08-26 media set. It ran `macos/aiup list`
against the public capture fixture inside a virtual PTY, parsed the output
stream, and drew each state into an image with a reproduced macOS Terminal
frame at 2016×1208 pixels (100×30 cells at 2× scale). It then built the GIF,
copied the six files into `site/media`, and wrote a schema 3 manifest with font
hashes, palette evidence, and a PTY layout matrix.

That set's manifest is kept at
[`docs/media/archive/capture-manifest-2026-08-26.json`](../../docs/media/archive/capture-manifest-2026-08-26.json).
The script's `--check` mode validates against that schema 3 format, so it fails
on the current schema 4 manifest.

Do not run it. A normal run writes straight into `docs/media` and `site/media`,
so it would replace the real Terminal captures with rendered ones. It also
resolves its paths as if it still lived in `scripts/`, so from this folder it
points at the wrong places.

The current media comes from a real Terminal window. To capture it again, use
`scripts/capture-terminal-media` as described in
[`docs/media/README.md`](../../docs/media/README.md).
