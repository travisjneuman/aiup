# Privacy and scanning

aiup is a local-inventory catalog. Inventory data never leaves the machine it runs on, but normal public execution and software maintenance do make clearly bounded network requests.

## What a scan reads

All of this stays on the machine:

- `PATH` and `command -v`
- Homebrew `brew list --formula` / `brew list --cask` (if Homebrew is installed)
- App bundles in `/Applications` and `~/Applications`
- A few well-known user prefixes used by vendor CLIs (`~/.local/bin`, `~/.grok/bin`, `~/.warp`, `~/.hermes`, `~/.opencode`)
- aiup's own state under `~/.local/share/aiup`

The interactive catalog also builds a local-only inventory of app bundle identifiers/display names/versions, global npm package names/versions, uv tool names/versions, and executable names/paths in user-facing prefixes. These records are written to `inventory-index.tsv` only to render the picker and `aiup inventory`; they are never uploaded. The inventory is cached locally for five minutes and can be rebuilt with `aiup inventory --refresh`.

## What a scan does not do

- No telemetry
- No account
- No upload of the inventory
- No upload or network lookup containing the local inventory
- No background telemetry or account profile

## Network requests

The network lanes are separate:

1. **Launcher refresh:** a public installation requests the small release pointer from `raw.githubusercontent.com` before every invocation, and downloads the runtime and catalog manifest only when a new release is published. Those requests do not contain the local inventory. If a request fails or a download fails validation, aiup runs the last validated release. An explicit `AIUP_SOURCE_PATH` development run skips this refresh.
2. **Homebrew and vendor maintenance:** actions that inspect remote versions, install, or update software may contact Homebrew, npm registries, PyPI, GitHub releases, or the selected vendor's documented metadata/download endpoints. `aiup check` and the picker's update preview ask each installed tool's own release source for its newest version (one request per tool, naming only that tool's package or channel), and refresh Homebrew's package metadata when it is older than 15 minutes. These requests are made only by the relevant action; their remote services have their own logging and privacy policies.
3. **User-opened links:** `aiup docs` or the picker docs key opens a catalog URL. A detected-only item opens a Google search only after the user deliberately chooses that action. Merely scanning local inventory does not open those links.

The aiup CLI itself does not require an aiup account or upload local inventory to an aiup server. Individual catalog tools may require their own accounts.

## State files

| Path | Purpose |
|---|---|
| `~/.local/share/aiup/methods/` | Last known install method per tool |
| `~/.local/share/aiup/generations/<id>/aiup` | Runtime of a validated release; generations other than the current, the previous, and any less than a day old are pruned |
| `~/.local/share/aiup/generations/<id>/manifest.tsv` | Catalog paired with that generation's runtime; never mixed across generations |
| `~/.local/share/aiup/generations/<id>/release` | Commit of the published release this generation came from |
| `~/.local/share/aiup/current-generation` | Atomically replaced pointer selecting the active pair after refresh |
| `~/.local/share/aiup/previous-generation` | Pointer to the release that was active before the current one |
| `~/.local/share/aiup/launcher-notice.stamp` | Limits the reinstall notice for pre-release launchers to once a day |
| `~/.local/share/aiup/brew-metadata.stamp` | When aiup last refreshed Homebrew's package metadata for a check |
| `~/.local/share/aiup/available-versions/` | Short-lived cache of each installed tool's newest release; hidden temporaries older than an hour are swept |
| `~/.local/share/aiup/activation.lock` | Short-lived process-owned serialization record for finalization, pointer replacement, and exact retention cleanup |
| `~/.local/share/aiup/npm/` | Isolated npm prefix for Node CLIs |
| `~/.local/share/aiup/npm-prefix` | npm's global prefix, reused until npm, its config files or prefix variables change |
| `~/.local/share/aiup/fzf-expanded` | Which catalog categories are expanded |
| `~/.local/share/aiup/catalog-index.tsv` | Last scan of the main catalog |
| `~/.local/share/aiup/brew-index.tsv` | Last scan of Homebrew extras |
| `~/.local/share/aiup/inventory-index.tsv` | Last local-only inventory of un-managed apps and CLIs |
| `~/.local/share/aiup/inventory-cache.meta` | Timestamp and local source fingerprint for the inventory cache |
| `~/.local/share/aiup/list-query` / `list-category` | Last picker query and selected category, stored locally to resume navigation |

These are local cache, not a cloud profile.

## Local run history

Update runs save private logs and structured version/result records under the AIUP state directory. `aiup history` and `aiup logs` read them locally; nothing is uploaded. The latest 20 completed runs are retained by default, with active and recent legacy runs protected. Logs can contain provider output and local paths. See the README for `AIUP_LOG_LIMIT` and per-tool log access.

## Local preferences and diagnostics

`preferences.json` contains only explicitly chosen tool exclusions, hold dates, and named groups. `doctor`, `coverage`, and `project` display local installation/dependency information; they do not upload it. Project inspection requires an explicit directory and executes no scripts. New history records include per-tool durations.
