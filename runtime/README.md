# Runtime | aiup

Developer notes for the Linux and Windows runtime. The design is in
[../docs/cross-platform-design.md](../docs/cross-platform-design.md); this page
only says where things are and what each part promises the others.

The runtime is plain Python 3.9 or newer with the standard library only. fzf
drives the picker.

## Running a checkout

```sh
python3 -I runtime/aiup_main.py version
python3 -I runtime/aiup_main.py catalog --json --platform all
```

`aiup_main.py` puts its own folder first on `sys.path` and calls
`aiup.cli.main`. `python -m aiup` from inside `runtime/` does the same.
Installed launchers run the release named in `macos/release` instead (see the
design doc, section 4).

## Layout

| Path | What it holds |
| --- | --- |
| `aiup/version.py` | `AIUP_VERSION`, one line the release scripts edit |
| `aiup/errors.py` | Exit codes and the errors that map to them |
| `aiup/model.py` | The shared data classes (design doc 6.1) |
| `aiup/versions.py` | Version parsing and comparison, ported from macOS `version_is_greater` |
| `aiup/config.py` | Environment variables, defaults and clamps |
| `aiup/paths.py` | Config, data, state, cache and runtime folders per OS |
| `aiup/cli.py` | Argument parsing, help text and dispatch |
| `aiup/catalog/` | Catalog loader, cell grammar, user data paths, export |
| `aiup/providers/` | Provider base class, registry, one module per channel |
| `aiup/commands/` | One module per command group, each with `run(args, ctx) -> int` |
| `aiup/platform/`, `aiup/engine/`, `aiup/tui/`, `aiup/detect/` | OS layer, engine, picker, detection |

## Catalog files

The loader reads four files and stops with the file, line and column when one
breaks the schema:

- `macos/catalog/manifest.tsv`: the base list every platform shares.
- `catalog/platforms.tsv`: Linux and Windows install targets. When it is
  missing, the catalog still loads with no Linux or Windows targets and says so
  once on stderr.
- `catalog/categories.tsv`: category order, names, emoji and blurbs.
- `catalog/tool-meta.tsv`: aliases, command names, process names and user data
  paths. A tool with no row uses its id as its command. A row with an empty
  commands cell means the tool has no command of its own.

`AIUP_CATALOG_DIR` names a `catalog/` folder to read instead; the manifest then
comes from `macos/catalog/manifest.tsv` beside that folder.

The version header in `manifest.tsv` and `platforms.tsv` must match
`AIUP_VERSION`. `categories.tsv` and `tool-meta.tsv` carry no version line.

## Commands

`aiup/commands/__init__.py` maps each command to its module. The CLI loads a
module only when its command runs. A module that is not written yet makes the
command print `aiup: <command> isn't implemented on this system yet` and exit 1.

Arguments arrive as `aiup.cli.Args`. A few details:

- `aiup`, `full`, `core`, `only`, `resume`, `retry`, `npm-update` and
  `group run` all reach the `update` module. `args.invoked` says which one was
  typed (`group` for `group run`), and `args.subcommand` holds `run` for groups.
- `group check` reaches the `check` module the same way.
- `args.no_install` is already set for each form: off for `only`, `retry` and
  `npm-update`, on for everything else, and `--no-install` always wins.
- With `--json` on a run or `check`, write the JSON document to
  `args.json_stream`. Plain `print` already goes to stderr.
- `catalog` gets `ctx=None` and reads `args.catalog`, `args.catalog_format` and
  `args.platform`; `aiup.catalog.export.render` builds the text.

## Providers

`aiup/providers/__init__.py` loads `aiup.providers.<module>` the first time a
channel is asked for. A module offers its provider as a `PROVIDER` instance, a
`PROVIDERS` sequence, or a `Provider` subclass defined in that module whose
`name` is the channel. A module that fails to import affects only its own
channel; `load_errors()` lists those for `aiup doctor`.
