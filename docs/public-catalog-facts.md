# Public catalog facts

## Population and joins

The Catalog tools metric (`key: tools`, exact string value) counts the top-level
`tools` array exported by the checkout's `macos/aiup catalog --json`. Those are
the curated entries in the adjacent `macos/catalog/manifest.tsv`, including
infrastructure. It is not a count of tools installed on the maintainer's Mac.

Keep these populations separate:

- category tool counts describe curated entries in that category;
- Homebrew extras describe local inventory plus a recommended list;
- exported `recommended` rows are suggestions, not extra catalog tools;
- detected-only software and manual-update apps are local inventory, not public
  curated catalog entries.

## Real write invocation

After runtime/manifest source edits finish, from the canonical checkout:

```bash
scripts/sync-public-docs --skip-media
```

This runs the local runtime once with `catalog --json`, pins the adjacent
manifest, and ignores inherited `AIUP_*` runtime/session overrides. It does not
use an installed launcher, fetch a release pointer, scan installed software,
initialize or sweep user state, install packages, update software, or make
network requests. It retains the macOS 14+, Bash 3+, Python 3, and curl runtime
prerequisites. Definition exports use a pipe instead of a temporary state file.
Metric `source` strings are descriptive provenance and are never executed.

The same exported data supplies all these text outputs:

- `site/catalog.json`: the existing catalog definition shape, including separate
  `categories`, top-level `tools`, and `recommended` arrays. Each category has
  `id`, `name` (the heading shown in `aiup list`), `emoji`, `blurb` and `tools`;
- `docs/catalog.md`: category tables headed by name and id, and a separate Homebrew recommendation table;
- `README.md`: the existing `CATALOG` marker block;
- `showcase.json`: the Catalog tools metric, plus `updated` when metrics change.
  The exporter assigns `key: tools`, an exact value, a local-export source note,
  and the date of this actual measurement as `asOf`. Its optional `provenance`
  records the producer, population, runtime version, and SHA-256 hashes of the
  exact UTF-8 runtime/manifest inputs and JSON export. No Git lookup is needed.
  Existing unrelated provenance fields are retained. Reviewed label mappings
  also assign `macOS` to `key: platform` and `Daemons` to `key: background`;
- `site/index.html`: software version, a `catalog-tools` JSON-LD PropertyValue,
  the visible `CATALOG-COUNT` marker span and its `data-catalog-tools` value,
  and catalog context in Open Graph/Twitter alt text;
- `site/llms.txt`: the version and reviewed-entry total.

Status, summary, links, and platform/background evidence stay unchanged. Adding
those identity keys preserves each record's value, label, source, round, `asOf`,
and any provenance. It is not a new measurement or review of the old claims.
An export does not establish that a background service is absent. A later-day
export is a new measurement and may change the Catalog tools date even if the
population is unchanged. Unchanged
file contents are not rewritten.

Include the generated text outputs in the same commit as source changes. Do
not copy counts by hand or run a second export just to test idempotence. The
consumer's showcase schema supports optional metric `key` and `provenance`
fields. Key references do not fall back to array positions.

## Media boundary

Without `--skip-media`, the exporter also copies the six accepted assets from
`docs/media/` to `site/media/` when their bytes differ. It checks all required
assets before refreshing any public output. `--skip-media` does not read or
write these assets. Neither mode generates or renders media.

Social alt text contains current catalog context. It does not attest to the
embedded number in a social image. Count-bearing social SVG/PNG artwork and
cache-version changes remain a separate, explicitly authorized media task.
Never claim those images were refreshed by a text-only export.

## Failure and review contract

Unknown arguments fail with usage. There is no `--check`, recount, or dry-run
mode. Missing source files, duplicate JSON fields or metric keys, ambiguous
reviewed labels or key/label conflicts, missing text markers, missing media in
copy mode, export failures, and runtime/manifest mismatches stop with an
actionable error before public writes. Export records must have the expected
object/string/array shapes, unique identities, and category tool lists that
agree with the top-level curated tools. Malformed records fail explicitly
before rendering or staging; missing fields do not become a KeyError. Restore
the named source or use `--skip-media` if only the canonical media is unavailable.

All intended JSON, Markdown, HTML, and text is computed before writes. The
exporter refuses an input edit during export, stages all changed files beside
their destinations, then atomically replaces each file. A staging failure leaves
public outputs unchanged. Replacement across several files is not an OS-level
transaction: a disk/permission failure during replacement can leave a partial
refresh and must be reported, not called a success.

Review the source and output diff. Do not run tests, syntax checks, builds,
media checks, provider checks, or network probes unless the owner explicitly
asks for them. No CI, scheduled refresh, or automatic metric-source execution
is part of this pipeline.
