<p align="center">
  <img src="site/brand/derived/lockup.png" alt="aiup" width="560" />
</p>

<p align="center">
  <strong>Scan your Mac. Update what you already have. Install or remove from a full-screen list.</strong><br/>
  Nothing is uploaded. Nothing requires an account.
</p>

<p align="center">
  <img alt="macOS" src="https://img.shields.io/badge/macOS-catalog-39FF14?style=for-the-badge&logo=apple&logoColor=black&labelColor=111" />
  <img alt="local only" src="https://img.shields.io/badge/scan-local%20only-5CE1FF?style=for-the-badge&labelColor=111" />
  <img alt="MIT" src="https://img.shields.io/badge/license-MIT-d67bff?style=for-the-badge&labelColor=111" />
  <img alt="never sudo" src="https://img.shields.io/badge/sudo-never-ffb347?style=for-the-badge&labelColor=111" />
</p>

<p align="center">
  <a href="https://aiup.neuman.dev">🌐 aiup.neuman.dev</a>
  ·
  <a href="https://github.com/travisjneuman/aiup">⭐ GitHub</a>
  ·
  <a href="docs/install.md">⬇️ Install</a>
  ·
  <a href="docs/catalog.md">📚 Catalog</a>
  ·
  <a href="docs/privacy.md">🔒 Privacy</a>
</p>

---

<p align="center">
  <img src="docs/media/aiup-list.gif" alt="aiup list — collapsible catalog, neon installed rows, Homebrew extras" width="960" />
</p>

<p align="center"><em>⏎ install or expand &nbsp;·&nbsp; ⌃D uninstall &nbsp;·&nbsp; ⌃O docs &nbsp;·&nbsp; esc done</em></p>

## ⚡ One minute

```bash
mkdir -p ~/.local/bin
curl -fsSL https://raw.githubusercontent.com/travisjneuman/aiup/main/macos/aiup-launcher -o ~/.local/bin/aiup
chmod +x ~/.local/bin/aiup
export PATH="$HOME/.local/bin:$PATH"
aiup only fzf
aiup list
```

| You type | What happens |
|---|---|
| `aiup` | 🔍 Ensure fzf, scan your Mac → update **installed** tools |
| `aiup list` | 🎛️ Full-screen catalog |
| `aiup only grok` | 📦 Install or update one tool |
| `aiup doctor` | 🩺 How each tool was detected |

### 🔄 Always live

The installed `aiup` command runs the canonical `~/web-dev/aiup/macos/aiup` checkout on every invocation, so local testing starts with the latest local script—even before a push. `AIUP_SOURCE_PATH` can point to another checkout's `macos/aiup` script. GitHub is only a fallback for users without a local checkout.

Update runs are unattended: Homebrew upgrade/install confirmations are accepted automatically, and version checks cannot wait for terminal input. A Homebrew tap already installed on the Mac is treated as prior user approval and trusted automatically; a missing tap required by a selected tool prompts before it is added and trusted. Explicit uninstall and on-disk app-switch confirmations still require your approval.

Official desktop apps that are not Homebrew-managed can declare a lightweight update manifest in the catalog. aiup checks that manifest against the installed bundle version first, downloads the large installer only when a newer release exists, and validates the replacement before activation. Screenpipe uses this path; its settings and capture data remain outside the app bundle.

## ✨ Why people keep it

<table>
<tr>
<td width="50%">

### 🔍 Scan, don't spray
Default `aiup` keeps optional tools from coming back, but restores required infrastructure such as fzf.

</td>
<td width="50%">

### 🚫 Never sudo
User-prefix installs. Node CLIs live in `~/.local/share/aiup/npm`, not a root-owned global.

</td>
</tr>
<tr>
<td>

### 🍺 Homebrew, honestly
Child lists are **your Mac**, plus a short recommended set — not all of Homebrew.

</td>
<td>

### 🔒 Stays on the machine
PATH, app bundles, `brew list`. No telemetry. [Privacy →](docs/privacy.md)

</td>
</tr>
</table>

### 🔎 Your Mac, not a hardcoded demo

The managed catalog is curated for safe install/update/remove actions. The picker also discovers four kinds of software that are not yet managed: app bundles, global npm packages, uv tools, and user-facing PATH binaries. Those rows are clearly marked detected-only, counted by source, and kept separate from Homebrew's installed inventory. aiup has not verified an updater/remover contract for them yet, so it will not guess how to update them.

<p align="center">
  <img src="docs/media/aiup-list-collapsed.png" width="46%" alt="Collapsed catalog" />
  <img src="docs/media/aiup-list-homebrew.png" width="46%" alt="Homebrew recommended" />
</p>

## 🎛️ Keys

| Key | Action |
|---|---|
| <kbd>enter</kbd> | Expand a category, install/update a tool, or **switch an on-disk app to Homebrew** |
| <kbd>tab</kbd> / <kbd>space</kbd> | Check / uncheck |
| <kbd>ctrl</kbd>+<kbd>e</kbd> | Toggle this category |
| <kbd>←</kbd> / <kbd>→</kbd> | Collapse / expand this category |
| <kbd>pgup</kbd> / <kbd>pgdn</kbd> | Jump to the previous / next category |
| <kbd>ctrl</kbd>+<kbd>g</kbd> | Open a searchable category-jump palette |
| <kbd>alt</kbd>+<kbd>e</kbd> / <kbd>alt</kbd>+<kbd>c</kbd> | Expand / collapse all |
| <kbd>ctrl</kbd>+<kbd>d</kbd> | Uninstall managed items; preview cleanup for detected apps |
| <kbd>ctrl</kbd>+<kbd>o</kbd> | Open GitHub, the product site, or a Google search for detected software |
| <kbd>ctrl</kbd>+<kbd>/</kbd> | Toggle the preview pane |
| <kbd>esc</kbd> | Leave |

Type to search the entire catalog, including rows inside collapsed categories; clearing the query restores the compact collapsed overview. The picker remembers its last query and category locally, so reopening it resumes navigation without changing the default collapsed overview. Detected is always the final category: it is a cross-source inventory of software found on this Mac, not a managed update list or an Applications-only list. Its header shows the total plus app/npm/uv/PATH subtotals. Use `aiup list --category detected` (or another category id) when the full catalog is too large. Detected rows show their source, version, path, and web-search link in the preview. App-bundle rows also support an AppCleaner-style cleanup preview; `aiup cleanup <detected-app-id>` lists exact candidates without changing anything, and `--apply` moves confirmed candidates to Trash.

Use `--view installed` for a compact maintenance view, `--view managed` to hide local detections/Homebrew extras, `--view detected` for only software found on this Mac, or `--view available` for Homebrew's available packages. Use `--sort label` when scanning a category alphabetically; the default `--sort id` preserves manifest order. `aiup inventory` uses a five-minute source-aware cache; add `--refresh` after installing or removing software outside aiup.

For Homebrew extras outside the managed catalog, use `aiup list --category homebrew/available` or `aiup list --view available`. The overview intentionally does not load thousands of Homebrew rows: it says “not loaded” rather than showing a misleading zero. The full view is generated from the Homebrew taps already on the Mac, places `font-*` casks under `Homebrew > fonts`, and delegates dependency resolution back to Homebrew; managed catalog items remain in their normal categories.

Installed rows glow **neon green**. Each category has a color bar. Categories start collapsed.

## 🍺 Already installed — just not via Homebrew?

Same app. Not a second copy.

<p align="center">
  <img src="docs/media/aiup-list-adopt.png" alt="Switch an existing app to Homebrew without losing settings" width="720" />
</p>

| State | Meaning |
|---|---|
| 💚 **installed** | Homebrew owns it |
| 💚 **on disk** | The app or command is already here some other way |
| ⬜ **absent** | Not found (recommended list only) |

Press <kbd>enter</kbd> on an **on disk** app to let Homebrew manage it.

- Notes, vaults, preferences, and `~/Library` **stay**
- Homebrew **never** runs `--zap`
- If the versions already match, Homebrew **adopts** the existing `.app` (no re-download)
- If they don't, only the app bundle is replaced — your data is left alone
- Command-line tools already on PATH get a Homebrew copy **alongside**; the original is not deleted

## 📚 What's in the catalog

<!-- CATALOG:START -->
_**2026.08.23-01** · **83** tools in the main catalog. Generated from `macos/aiup`._

| | Category | What | Size |
|---|---|---|---|
| ⚙️ | **infra** | Runtimes and installers other tools need | 16 tools |
| 🤖 | **coding-agents** | Agents that write and edit code in the terminal | 29 tools |
| 🖥️ | **workspaces** | Desktop hubs that drive those agents | 6 tools |
| ✏️ | **editors** | Places you type code | 5 tools |
| ⌨️ | **terminals** | Places you run commands | 4 tools |
| 💬 | **chat** | Cloud chat apps | 4 tools |
| 🧠 | **local-ai** | Models, capture, and engines that run on your Mac | 13 tools |
| 🔧 | **llm-utils** | Unix-pipe LLM CLIs | 5 tools |
| 🔌 | **adapters** | Glue between agents and editors | 1 tool |
| 🍺 | **homebrew** | Homebrew extras outside the managed catalog, plus a short recommended list | your Mac + recommended |
<!-- CATALOG:END -->

Full list → **[docs/catalog.md](docs/catalog.md)** · Homebrew → **[docs/homebrew.md](docs/homebrew.md)**

Research notes → **[catalog research](docs/catalog-research.md)** · TUI review → **[navigation research](docs/tui-research.md)**

## 🧰 What aiup needs

| Need | Why |
|---|---|
| bash · python3 · curl | The script (macOS already has these) |
| [fzf](https://github.com/junegunn/fzf) | Required full-screen catalog and infrastructure tool; aiup installs and updates the Homebrew formula |
| Homebrew / Node / uv | Homebrew is required for fzf and brew-managed items; Node/uv are installed on demand when needed |

## 🗺️ Status

| OS | |
|---|---|
| 🍎 macOS | Current — `macos/aiup` |
| 🐧 Linux | Coming |
| 🪟 Windows | Coming |

## 📜 License

[MIT](LICENSE) · [travisjneuman/aiup](https://github.com/travisjneuman/aiup)
