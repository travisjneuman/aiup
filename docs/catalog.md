# Catalog

Anything in the AI / agent / LLM / nearby-dev neighborhood that can be installed, updated, or removed from the CLI belongs here. Default `aiup` still only **updates what is present**.

## Categories

| Category | For a new user |
|---|---|
| **infra** | Needed to install other things: Homebrew, Node/npm, uv, gh, wrangler, deno |
| **coding-agents** | The thing that writes or edits code in the terminal (Claude Code, Codex, Grok, Hermes CLI, …) |
| **workspaces** | A GUI or hub that *drives* those agents. Grok Bot, OpenCode desktop, T3 Code, **Hermes Desktop**, n8n |
| **editors** | Places you type code (VS Code, Cursor IDE, Zed, Antigravity IDE) |
| **terminals** | Places you run commands (Ghostty, iTerm, Warp app, cmux) |
| **chat** | Cloud chat products (ChatGPT, Claude app, Copilot app, Perplexity) |
| **local-ai** | Models and capture on this machine. Ollama, LM Studio, Jan, GPT4All, AnythingLLM, MacWhisper, screenpipe, **MLX**, **mlx-lm** |
| **llm-utils** | Unix-pipe LLM CLIs (`llm`, aichat, fabric, sgpt) |
| **adapters** | Glue (pi-acp) |
| **homebrew** | Extras already on this Mac via brew, plus a short recommended list. See [homebrew.md](homebrew.md) |

## Hermes: CLI vs Desktop

They are two catalog items, same product family:

| Id | Category | What |
|---|---|---|
| `hermes` | coding-agents | Nous Hermes Agent CLI (`hermes` in a terminal) |
| `hermes-desktop` | **workspaces** | Official Nous desktop app (`Hermes.app`). Same agent, memory, and skills as the CLI — the same *class* as Grok Bot or OpenCode desktop, not a local-model runner |

Install the desktop app with the Homebrew cask `hermes-desktop`, the official DMG, or `hermes desktop` if the CLI is already present.

## MLX vs local LLM apps

**MLX is not another chat app.** It is Apple's array/math engine for Apple Silicon. Chat products (Ollama, LM Studio, Jan) are apps that *run models*; some of them may use MLX internally. Installing those apps does **not** mean `mlx` / `mlx-lm` show as installed.

| Id | What |
|---|---|
| `mlx` | The engine (`brew install mlx`) |
| `mlx-lm` | CLI + server to generate, chat, and serve local LLMs on MLX (`brew install mlx-lm`) |

Use Ollama/LM Studio if you want a product with a model library UI. Use mlx-lm if you want Apple's stack directly (`mlx_lm.chat`, `mlx_lm.server`).

## Detection

A tool is **installed** when any of these is true (checked locally):

- Its binary is on `PATH` or a known user prefix
- Its Homebrew formula or cask is installed
- Its `.app` exists under `/Applications` or `~/Applications`
- Its npm package is in aiup's prefix or (as a fallback) a user npm prefix

Presence is not a leftover state file. An empty `~/.hermes` does not count.

## Lifecycle flags

Some rows carry `[sunset]`, `[archived]`, or `[maintenance]`. Installing those from the picker warns first.
