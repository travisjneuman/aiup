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

1. **Launcher refresh:** a public installation requests the current runtime and catalog manifest from `raw.githubusercontent.com` before every invocation. Those requests do not contain the local inventory. If either request fails validation or is unavailable, aiup stops rather than running an old cache. An explicit `AIUP_SOURCE_PATH` development run skips this refresh.
2. **Homebrew and vendor maintenance:** actions that inspect remote versions, install, or update software may contact Homebrew, npm registries, GitHub releases, or the selected vendor's documented metadata/download endpoints. These requests are made only by the relevant action; their remote services have their own logging and privacy policies.
3. **User-opened links:** `aiup docs` or the picker docs key opens a catalog URL. A detected-only item opens a Google search only after the user deliberately chooses that action. Merely scanning local inventory does not open those links.

The aiup CLI itself does not require an aiup account or upload local inventory to an aiup server. Individual catalog tools may require their own accounts.

## State files

| Path | Purpose |
|---|---|
| `~/.local/share/aiup/methods/` | Last known install method per tool |
| `~/.local/share/aiup/generations/<id>/aiup` | Runtime in an immutable validated runtime/catalog generation; never used as an offline fallback |
| `~/.local/share/aiup/generations/<id>/manifest.tsv` | Catalog paired with that generation's runtime |
| `~/.local/share/aiup/current-generation` | Atomically replaced pointer selecting the active pair after refresh |
| `~/.local/share/aiup/previous-generation` | Previous complete pair retained as recovery evidence, not an offline fallback |
| `~/.local/share/aiup/npm/` | Isolated npm prefix for Node CLIs |
| `~/.local/share/aiup/fzf-expanded` | Which catalog categories are expanded |
| `~/.local/share/aiup/catalog-index.tsv` | Last scan of the main catalog |
| `~/.local/share/aiup/brew-index.tsv` | Last scan of Homebrew extras |
| `~/.local/share/aiup/inventory-index.tsv` | Last local-only inventory of un-managed apps and CLIs |
| `~/.local/share/aiup/inventory-cache.meta` | Timestamp and local source fingerprint for the inventory cache |
| `~/.local/share/aiup/list-query` / `list-category` | Last picker query and selected category, stored locally to resume navigation |

These are local cache, not a cloud profile.
