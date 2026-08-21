# Privacy and scanning

aiup is a local catalog. A scan never leaves the machine it runs on.

## What a scan reads

All of this stays on the machine:

- `PATH` and `command -v`
- Homebrew `brew list --formula` / `brew list --cask` (if Homebrew is installed)
- App bundles in `/Applications` and `~/Applications`
- A few well-known user prefixes used by vendor CLIs (`~/.local/bin`, `~/.grok/bin`, `~/.warp`, `~/.hermes`, `~/.opencode`)
- aiup's own state under `~/.local/share/aiup`

The interactive catalog also builds a local-only inventory of app bundle identifiers/display names/versions, global npm package names/versions, uv tool names/versions, and executable names/paths in user-facing prefixes. These records are written to `inventory-index.tsv` only to render the picker and `aiup inventory`; they are never uploaded.

## What a scan does not do

- No telemetry
- No account
- No upload of the inventory
- No network call to "check what you have" (docs URLs open only when you press the docs key)
- Installers you trigger still talk to their own vendors (Homebrew, npm, curl scripts). That is those tools, not aiup phoning home

The default product does not require an account or a server.

## State files

| Path | Purpose |
|---|---|
| `~/.local/share/aiup/methods/` | Last known install method per tool |
| `~/.local/share/aiup/npm/` | Isolated npm prefix for Node CLIs |
| `~/.local/share/aiup/fzf-expanded` | Which catalog categories are expanded |
| `~/.local/share/aiup/catalog-index.tsv` | Last scan of the main catalog |
| `~/.local/share/aiup/brew-index.tsv` | Last scan of Homebrew extras |
| `~/.local/share/aiup/inventory-index.tsv` | Last local-only inventory of un-managed apps and CLIs |

These are local cache, not a cloud profile.
