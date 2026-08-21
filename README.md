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
| <kbd>alt</kbd>+<kbd>e</kbd> / <kbd>alt</kbd>+<kbd>c</kbd> | Expand / collapse all |
| <kbd>ctrl</kbd>+<kbd>d</kbd> | Uninstall |
| <kbd>ctrl</kbd>+<kbd>o</kbd> | Open GitHub or the product site |
| <kbd>esc</kbd> | Leave |

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
_**2026.08.21-02** · **69** tools in the main catalog. Generated from `macos/aiup`._

| | Category | What | Size |
|---|---|---|---|
| ⚙️ | **infra** | Runtimes and installers other tools need | 7 tools |
| 🤖 | **coding-agents** | Agents that write and edit code in the terminal | 27 tools |
| 🖥️ | **workspaces** | Desktop hubs that drive those agents | 6 tools |
| ✏️ | **editors** | Places you type code | 5 tools |
| ⌨️ | **terminals** | Places you run commands | 4 tools |
| 💬 | **chat** | Cloud chat apps | 4 tools |
| 🧠 | **local-ai** | Models, capture, and engines that run on your Mac | 10 tools |
| 🔧 | **llm-utils** | Unix-pipe LLM CLIs | 5 tools |
| 🔌 | **adapters** | Glue between agents and editors | 1 tool |
| 🍺 | **homebrew** | What Homebrew already put on your Mac, plus a short recommended list | your Mac + recommended |
<!-- CATALOG:END -->

Full list → **[docs/catalog.md](docs/catalog.md)** · Homebrew → **[docs/homebrew.md](docs/homebrew.md)**

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
