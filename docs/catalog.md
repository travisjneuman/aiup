# Catalog (2026.08.20-21)

Generated from `macos/aiup` via `aiup catalog --markdown`.

## ⚙️ infra

Runtimes and installers other tools need

| Id | Label |
|---|---|
| `brew` | Homebrew — required for formulae, casks, and Node/npm on this system (not removable) |
| `npm` | Node/npm via Homebrew (infrastructure; update-only, not removable) |
| `uv` | Astral uv/uvx — Python toolchain (also used to install Aider/llm) |
| `fzf` | fzf fuzzy finder — required interactive catalog |
| `gh` | GitHub CLI |
| `wrangler` | Cloudflare Workers CLI (cloudflare-wrangler) |
| `deno` | Deno runtime |

## 🤖 coding-agents

Agents that write and edit code in the terminal

| Id | Label |
|---|---|
| `claude` | Claude Code — Anthropic native CLI |
| `copilot` | GitHub Copilot CLI — @github/copilot |
| `codex` | OpenAI Codex CLI — @openai/codex |
| `antigravity` | Google Antigravity CLI (agy) |
| `grok` | Grok Build — xAI official CLI |
| `gemini` | Google Gemini CLI (legacy; Antigravity is preferred) |
| `pi` | Pi coding agent — @earendil-works/pi-coding-agent |
| `kilo` | Kilo Code CLI — @kilocode/cli |
| `gsd2` | GSD (gsd-pi) — @opengsd/gsd-pi |
| `opencode` | OpenCode — official installer |
| `hermes` | Hermes Agent — Nous Research |
| `omp` | Oh My Pi (omp) standalone binary |
| `warp` | Warp Agent CLI (warp / Oz TUI) |
| `aider` | Aider — git-native pair programming CLI |
| `goose` | Goose — Block open-source agent CLI |
| `cursor` | Cursor Agent CLI (cursor-agent / cursor-cli cask) |
| `qwen` | Qwen Code — @qwen-code/qwen-code |
| `crush` | Crush — Charm agentic TUI (@charmland/crush) |
| `amp` | Amp — Sourcegraph frontier coding agent |
| `kiro` | Kiro CLI — Amazon Q Developer CLI successor |
| `droid` | Factory Droid — Factory.ai coding agent |
| `kimi` | Kimi Code CLI — Moonshot (kimi-code) |
| `openclaw` | OpenClaw — personal/local AI assistant CLI |
| `plandex` | Plandex — large-task planning CLI (quieter upstream) |
| `cline` | Cline CLI — npm cline |
| `continue` | [SUNSET] Continue CLI — acquired by Cursor Jun 2026, repo read-only |
| `interpreter` | Open Interpreter — natural-language computer-use agent |

## 🖥️ workspaces

Desktop hubs that drive those agents

| Id | Label |
|---|---|
| `t3-code` | T3 Code — desktop hub that drives Codex/Claude/Grok/OpenCode |
| `t3-nightly` | T3 Code Nightly — desktop hub (nightly build) |
| `grokbot` | Grok Bot — xAI teammates that work across your apps |
| `opencode-desktop` | OpenCode desktop client |
| `hermes-desktop` | Hermes Desktop — official Nous GUI for the same agent as the Hermes CLI |
| `n8n` | n8n — workflow automation (often used with local LLMs) |

## ✏️ editors

Places you type code

| Id | Label |
|---|---|
| `vscode` | Visual Studio Code |
| `vscode-insiders` | VS Code Insiders |
| `cursor-ide` | Cursor IDE app (Homebrew cask) |
| `zed` | Zed editor app (Homebrew cask) |
| `antigravity-ide` | Google Antigravity IDE |

## ⌨️ terminals

Places you run commands

| Id | Label |
|---|---|
| `cmux` | cmux — terminal for running coding agents (not an agent itself) |
| `warp-app` | Warp terminal (desktop; distinct from Warp Agent CLI) |
| `ghostty` | Ghostty terminal |
| `iterm2` | iTerm2 terminal |

## 💬 chat

Cloud chat apps

| Id | Label |
|---|---|
| `chatgpt` | ChatGPT desktop app (Homebrew cask) |
| `claude-app` | Claude desktop app (not Claude Code CLI) |
| `copilot-app` | GitHub Copilot native desktop app |
| `perplexity` | Perplexity desktop (Personal Computer agent) |

## 🧠 local-ai

Models, capture, and engines that run on your Mac

| Id | Label |
|---|---|
| `ollama` | Ollama local-model CLI |
| `lm-studio` | LM Studio — local LLM desktop app |
| `jan` | Jan — local ChatGPT-style app |
| `gpt4all` | GPT4All — local LLM desktop app |
| `anythingllm` | AnythingLLM — private local RAG/chat app |
| `mlx` | MLX — Apple Silicon engine for running local AI (not a chat app) |
| `mlx-lm` | mlx-lm — chat/generate/serve local LLMs on Apple Silicon using MLX |
| `ollama-app` | Ollama desktop app (Homebrew cask) |
| `macwhisper` | MacWhisper — local speech-to-text |
| `screenpipe` | screenpipe — local screen/audio capture (app, no Homebrew cask) |

## 🔧 llm-utils

Unix-pipe LLM CLIs

| Id | Label |
|---|---|
| `llm` | llm — Simon Willison Unix LLM CLI |
| `mods` | mods — Charm pipe-to-LLM (upstream archived) |
| `aichat` | aichat — all-in-one terminal AI workstation |
| `fabric` | fabric-ai — Daniel Miessler prompt-pattern CLI |
| `sgpt` | shell-gpt (sgpt) via uv |

## 🔌 adapters

Glue between agents and editors

| Id | Label |
|---|---|
| `pi-acp` | Pi ACP adapter (pi-acp) for T3 Code / editors |

## 🍺 homebrew

What Homebrew already put on your Mac, plus a short recommended list

| Child | What |
|---|---|
| `casks` | GUI apps Homebrew already installed on your Mac |
| `fonts` | Fonts Homebrew already installed on your Mac |
| `formulae` | CLI formulae Homebrew already installed on your Mac |
| `libraries` | Libraries Homebrew already installed on your Mac |
| `recommended` | Popular extras you can add — or switch to Homebrew without losing settings |

Recommended extras:

| Type | Id | Label |
|---|---|---|
| cask | `raycast` | Raycast launcher |
| cask | `obsidian` | Obsidian notes |
| cask | `docker` | Docker Desktop |
| cask | `linear` | Linear issue tracker |
| cask | `notion` | Notion |
| cask | `windsurf` | Windsurf AI IDE |
| cask | `devin-desktop` | Devin Desktop |
| cask | `copilot-cli` | GitHub Copilot CLI (Homebrew cask) |
| cask | `cursor-cli` | Cursor Agent CLI cask |
| cask | `claude-code` | Claude Code cask |
| cask | `chatgpt-atlas` | ChatGPT Atlas |
| cask | `kiro` | Kiro IDE |
| cask | `warp-agent-cli` | Warp Agent CLI cask |
| cask | `coderabbit` | CodeRabbit AI review |
| cask | `auto-claude` | Auto Claude |
| cask | `monet` | Monet — mission control for coding agents |
| cask | `ollamac` | Ollamac local chat |
| cask | `notesollama` | NotesOllama |
| cask | `tableplus` | TablePlus database GUI |
| cask | `postman` | Postman API client |
| cask | `insomnia` | Insomnia API client |
| cask | `1password` | 1Password |
| cask | `secretive` | Secretive SSH keys |
| cask | `stats` | Stats menu-bar monitors |
| cask | `iina` | IINA media player |
| cask | `wezterm` | WezTerm |
| cask | `kitty` | Kitty terminal |
| cask | `alacritty` | Alacritty terminal |
| cask | `neovide` | Neovide (Neovim GUI) |
| cask | `fork` | Fork git client |
| cask | `sublime-merge` | Sublime Merge |
| cask | `figma` | Figma |
| cask | `brave-browser` | Brave Browser |
| cask | `firefox` | Firefox |
| cask | `utm` | UTM virtual machines |
| cask | `jan` | Homebrew cask jan |
| cask | `gpt4all` | Homebrew cask gpt4all |
| cask | `anythingllm` | Homebrew cask anythingllm |
| formula | `jq` | jq JSON processor |
| formula | `neovim` | Neovim |
| formula | `go` | Go language |
| formula | `cmake` | CMake |
| formula | `ninja` | Ninja build |
| formula | `tree` | tree directory listing |
| formula | `watch` | watch repeating command |
| formula | `wget` | wget |
| formula | `curl` | curl |
| formula | `ripgrep` | ripgrep (rg) |
| formula | `fd` | fd file finder |
| formula | `tmux` | tmux |
| formula | `starship` | Starship prompt |
| formula | `eza` | eza (ls) |
| formula | `bat` | bat (cat) |
| formula | `git-delta` | delta git pager |
| formula | `gh` | Homebrew formula gh |
| formula | `git` | git |
| formula | `lazygit` | lazygit |
| formula | `helix` | Helix editor |
| formula | `mise` | mise runtime manager |
| formula | `direnv` | direnv |
| formula | `just` | just command runner |
| formula | `pnpm` | pnpm |
| formula | `yarn` | yarn |
| formula | `podman` | Podman |
| formula | `kubectl` | kubectl |
| formula | `helm` | Helm |
| formula | `terraform` | Terraform |

