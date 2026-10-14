# Scripting and moving to another Mac | aiup

How to use aiup from your own scripts: JSON output, exit status, and the export file that moves your setup to another Mac.

## Exit status

| Status | Meaning |
| --- | --- |
| 0 | Done. For `aiup check`, the check ran (updates may or may not be ready). |
| 1 | Something failed: a tool's update, a check that could not run, or a refused action. |
| 2 | A mistyped command, option or missing argument. aiup prints one line, such as `aiup: unknown command 'chek'. Run aiup help.` |
| 130 | Stopped with Ctrl-C. Finished tools are recorded; the rest are pending for `aiup resume`. |

## JSON output

`--json` works with update runs (`aiup`, `aiup full`, `aiup core`, `aiup only`, `aiup resume`, `aiup retry`, `aiup group run`) and with `aiup check` and `aiup group check`. The results go to stdout as one JSON document. Progress, notes and any prompt go to stderr, so a pipe gets only the JSON.

```bash
aiup check --json > check.json
aiup only wrangler --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["counts"])'
```

Other commands refuse `--json` with exit status 2.

### `aiup check --json` (schema `aiup-check-v1`)

```json
{
  "schema": "aiup-check-v1",
  "mode": "check",
  "duration": 4,
  "interrupted": false,
  "counts": {"update": 2, "current": 40, "unverified": 1},
  "tools": [
    {"tool": "wrangler", "result": "update", "installed": "4.42.0", "latest": "4.43.1", "note": "", "warning": false}
  ]
}
```

`result` is one of `update`, `current`, `self-updated` (the app updated itself), `unverified` (no read-only source could confirm it; a normal run still updates it), `skipped` (held, excluded or managed elsewhere) and `absent`.

### Update runs (schema `aiup-run-v1`)

```json
{
  "schema": "aiup-run-v1",
  "mode": "update",
  "duration": 182,
  "interrupted": false,
  "counts": {"updated": 3, "unchanged": 39},
  "log": "/Users/you/.local/share/aiup/logs/update-20261013-090000.AbC123",
  "tools": [
    {"tool": "wrangler", "result": "updated", "before": "4.42.0", "after": "4.43.1", "note": "", "warning": false, "duration": 21}
  ]
}
```

`result` is one of `updated`, `installed`, `unchanged`, `downgraded`, `failed`, `deferred` (an open app, or an npm release that needs your OK), `cancelled`, `pending` (not reached), `skipped`, `cleaned`, `self-updated`, `unverified` and `planned` (with `--dry-run`). `warning` is true when the tool's log has a warning worth a look; `aiup attention` explains it. The numbers above are examples.

## Notifications

`aiup notify` prints one summary line and shows a macOS notification when updates are ready. See [notify.md](notify.md) for cron and launchd examples.

## Export and import

```bash
aiup export my-mac.json      # save this Mac's setup (never overwrites an existing file)
aiup export                  # or print it to stdout
aiup import my-mac.json --dry-run   # on the other Mac: show what it would add
aiup import my-mac.json             # show it, ask once, then install
```

The export file (schema `aiup-export-v1`) holds:

- `tools`: the catalog tools installed here
- `homebrew.formulae`: the Homebrew formulae you installed yourself (from `brew leaves --installed-on-request`, so dependencies are left out), apart from the ones the catalog already covers
- `homebrew.casks`: the Homebrew apps installed here that the catalog does not cover
- `preferences`: your exclusions, holds, named groups and cleanup setting

It has no paths, host names or account details. The file is written readable only by you.

`aiup import` changes nothing until you answer yes:

1. It lists the tools, Homebrew formulae and apps that are missing on this Mac, any third-party Homebrew taps they come from, and the preferences it will add.
2. Tools already here are left as they are. A tool excluded in the file or on this Mac is not installed. IDs this version of aiup does not know are listed and skipped.
3. After you confirm, it adds the preferences (exclusions are added, the later of two hold dates wins, a group with the same name is replaced, the cleanup setting is taken from the file when the exporting Mac had chosen one), installs the Homebrew formulae and apps, then installs the catalog tools the same way `aiup only` does, with the usual report.

It needs a terminal for the question. An import file must be under 1 MiB.
