# aiup

**A local catalog for AI tools on your Mac.**

Scan what you already have. Update it. Install or remove from a full-screen list. Nothing is uploaded.

[![aiup list](docs/media/aiup-list.gif)](https://aiup.neuman.dev)

<p align="center">
  <a href="https://aiup.neuman.dev"><strong>aiup.neuman.dev</strong></a>
  ·
  <a href="https://github.com/travisjneuman/aiup">github.com/travisjneuman/aiup</a>
  ·
  <a href="docs/install.md">install</a>
  ·
  <a href="docs/catalog.md">catalog</a>
  ·
  <a href="docs/privacy.md">privacy</a>
</p>

---

aiup is a bash script that knows how a messy neighborhood of coding agents, chat apps, local-model tools, and Homebrew extras actually land on a Mac. Default `aiup` only **updates what is present**. Missing tools come back only when you ask.

```bash
mkdir -p ~/.local/bin
curl -fsSL https://raw.githubusercontent.com/travisjneuman/aiup/main/macos/aiup -o ~/.local/bin/aiup
chmod +x ~/.local/bin/aiup
aiup list
```

## Why it exists

AI CLIs install everywhere: Homebrew, npm globals, vendor `curl | bash` scripts, `~/.local/bin`, `~/.grok`, `~/.hermes`. Updating with `sudo` writes root-owned files into user prefixes and the next update dies with `EACCES`. A hardcoded “install the whole set” command fights uninstalls.

aiup’s rules:

1. **Never sudo**
2. **Scan by default** — do not reinstall what you removed
3. **Presence is a live binary, package, cask, or app**
4. **Explicit install**
5. **Node CLIs go in `~/.local/share/aiup/npm`**, not `sudo npm -g`

## Commands

| Command | Behavior |
|---|---|
| `aiup` | Scan this Mac. Update installed tools only |
| `aiup list` | Interactive catalog |
| `aiup list --plain` | Print the table |
| `aiup install` / `aiup remove` | Checkbox install / uninstall |
| `aiup only grok` | Update, and install if missing |
| `aiup doctor` | Status, method, path for every catalog tool |
| `aiup docs grok` | Open the official GitHub or site |

In the list: **enter** install or expand a category, **ctrl-d** uninstall, **ctrl-o** docs, **esc** leave. Categories start collapsed. Installed rows are neon green; each category has a color bar.

## Catalog, in one screen

| Category | Examples |
|---|---|
| infra | Homebrew, Node/npm, uv, gh |
| coding-agents | Claude Code, Codex, Grok, Hermes CLI |
| workspaces | Grok Bot, OpenCode desktop, **Hermes Desktop**, T3 Code |
| editors | VS Code, Cursor, Zed |
| terminals | Ghostty, iTerm, Warp, cmux |
| chat | ChatGPT, Claude, Perplexity |
| local-ai | Ollama, LM Studio, **MLX**, **mlx-lm** |
| homebrew | What brew already put on *this* Mac, plus a short recommended list |

Hermes Desktop is a **workspace** (official Nous GUI for the same agent as the CLI), not a local-model runner.

**MLX** is Apple's Apple Silicon engine. **mlx-lm** runs local LLMs on that engine. They are not built into Ollama or LM Studio — those apps are separate products and may use MLX internally.

Homebrew children with “0 absent” are **inventory**, not a claim that Homebrew has nothing else. See [docs/homebrew.md](docs/homebrew.md). An app you installed from a vendor DMG (Obsidian is the usual example) shows as **on disk**, not missing.

## Dependencies

bash, python3, curl. **fzf** makes `aiup list` a TUI; without it you get numbered prompts. Homebrew / Node / uv are installed on demand when a catalog item needs them. Details: [docs/install.md](docs/install.md).

## Privacy

Scan is local. No account, no telemetry, no inventory upload. [docs/privacy.md](docs/privacy.md).

## Status

| OS | State |
|---|---|
| macOS | Current (`macos/aiup`) |
| Linux | Planned |
| Windows | Planned |

## License

[MIT](LICENSE)
