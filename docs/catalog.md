# Catalog (2026.09.29-05)

Generated from `macos/aiup` via `aiup catalog --markdown`.

## ⚙️ infra

Runtimes and installers other tools need

| Id | Label |
|---|---|
| `brew` | Homebrew — required for formulae, casks, and Node/npm on this system (not removable) |
| `npm` | Node/npm via Homebrew (infrastructure; update-only, not removable) |
| `uv` | Astral uv/uvx — Python toolchain (also installs the uv-tool items) |
| `fzf` | fzf fuzzy finder — required interactive catalog |
| `deno` | Deno runtime |
| `bun` | Bun JavaScript runtime, bundler, test runner, and package manager |
| `pnpm` | pnpm fast, disk-efficient JavaScript package manager (official npm package) |
| `mise` | mise — polyglot runtime/tool version manager |

## 🤖 coding-agents

Agents that write and edit code in the terminal

| Id | Label |
|---|---|
| `claude` | Claude Code — Anthropic native CLI |
| `copilot` | GitHub Copilot CLI — @github/copilot |
| `codex` | OpenAI Codex CLI — @openai/codex |
| `antigravity` | Google Antigravity CLI (agy) |
| `grok` | Grok Build — xAI official CLI |
| `gemini` | Google Gemini CLI — official npm package (macOS 15+) |
| `pi` | Pi coding agent — @earendil-works/pi-coding-agent |
| `kilo` | Kilo Code CLI — @kilocode/cli |
| `gsd2` | GSD (gsd-pi) — @opengsd/gsd-pi |
| `opencode` | OpenCode — official installer |
| `warp` | Warp Agent CLI (warp / Oz TUI) |
| `aider` | Aider — git-native pair programming CLI |
| `goose` | Goose — open-source agent CLI |
| `cursor` | Cursor Agent CLI (cursor-agent / cursor-cli cask) |
| `qwen` | Qwen Code — @qwen-code/qwen-code |
| `crush` | Crush — Charm agentic TUI (@charmland/crush) |
| `amp` | Amp — Sourcegraph frontier coding agent |
| `kiro` | Kiro CLI — Amazon Q Developer CLI successor |
| `droid` | Factory Droid — Factory.ai coding agent |
| `kimi` | Kimi Code CLI — Moonshot (kimi-code) |
| `cline` | Cline CLI — npm cline |
| `vibe` | Mistral Vibe — open-source CLI coding assistant |
| `devin-cli` | Devin CLI — Cognition coding agent |
| `auggie` | Auggie — Augment Code CLI (@augmentcode/auggie) |
| `junie` | Junie CLI — JetBrains coding agent (@jetbrains/junie) |
| `letta` | Letta Code — stateful agent CLI (@letta-ai/letta-code) |
| `qoder` | Qoder CLI — @qoder-ai/qodercli |

## 🖥️ workspaces

Desktop hubs that drive those agents

| Id | Label |
|---|---|
| `t3-code` | T3 Code — desktop hub that drives Codex/Claude/Grok/OpenCode |
| `t3-nightly` | T3 Code Nightly — desktop hub (nightly build) |
| `opencode-desktop` | OpenCode desktop client |
| `hermes-desktop` | Hermes Desktop — official Nous GUI for the same agent as the Hermes CLI |
| `conductor` | Conductor — run parallel Claude Code/Codex agents in worktrees |
| `emdash` | Emdash — run multiple coding agents in parallel |
| `superset` | Superset — terminal workspace for orchestrating coding agents |
| `amp-app` | Amp desktop app — Sourcegraph agent environment (macOS 26+) |
| `factory-app` | Factory desktop — native interface for Factory Droids |
| `antigravity-app` | Google Antigravity 2 — agent orchestration hub app |

## ✏️ editors

Places you type code

| Id | Label |
|---|---|
| `vscode` | Visual Studio Code |
| `vscode-insiders` | VS Code Insiders |
| `cursor-ide` | Cursor IDE app (Homebrew cask) |
| `zed` | Zed editor app (Homebrew cask) |
| `antigravity-ide` | Google Antigravity IDE |
| `devin-desktop` | Devin Desktop — agentic IDE (formerly Windsurf) |
| `kiro-ide` | Kiro IDE — spec-driven agentic IDE (distinct from Kiro CLI) |
| `jetbrains-air` | JetBrains Air — agentic development environment |

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
| `gemini-app` | Google Gemini desktop app (macOS 15+) |
| `cherry-studio` | Cherry Studio — multi-provider LLM desktop client |
| `msty-studio` | Msty Studio — local and online model desktop app |
| `boltai` | BoltAI — native macOS AI chat client |
| `chatbox` | Chatbox — multi-provider AI chat desktop app |
| `lobehub` | LobeHub — open-source AI chat/agent desktop app |

## 🎬 media

Video, images, audio, transcription, and AI creation tools

| Id | Label |
|---|---|
| `remotion` | Remotion CLI — React video tooling (@remotion/cli); projects need matching local dependencies |
| `macwhisper` | MacWhisper — local speech-to-text |
| `whisper-cpp` | whisper.cpp local speech-to-text engine (model files are separate) |
| `ffmpeg` | FFmpeg — audio/video conversion and encoding (media utility) |
| `audacity` | Audacity — audio editing and recording (media utility) |
| `draw-things` | Draw Things — local AI image generation; models downloaded separately |
| `superwhisper` | Superwhisper — AI dictation and LLM reformatting; vendor licensing applies |
| `buzz` | Buzz — audio transcription and translation; models downloaded separately |
| `obs` | OBS Studio — recording and streaming (media utility) |
| `blender` | Blender — 3D modeling, animation, and rendering (media utility) |
| `losslesscut` | LosslessCut — lossless audio/video trimming (media utility) |
| `handbrake-app` | HandBrake — desktop video transcoding (media utility) |
| `shotcut` | Shotcut — video editing (media utility) |
| `kdenlive` | Kdenlive — non-linear video editing (media utility) |
| `krita` | Krita — digital painting and illustration (media utility; AI plugins are separate) |
| `inkscape` | Inkscape — vector graphics and SVG editing (media utility) |
| `imagemagick` | ImageMagick — command-line image conversion and processing (magick) |
| `yt-dlp` | yt-dlp — command-line audio/video downloads (media utility) |
| `vips` | libvips — efficient image processing CLI/library (media utility) |
| `whisperkit` | WhisperKit CLI — Argmax on-device speech recognition (models separate) |
| `handy` | Handy — open-source local speech-to-text dictation |
| `voiceink` | VoiceInk — local AI dictation (macOS 15+) |
| `wispr-flow` | Wispr Flow — AI dictation; vendor account required |
| `stability-matrix` | Stability Matrix — Stable Diffusion package manager and inference UI |
| `mochi-diffusion` | Mochi Diffusion — native Core ML Stable Diffusion (macOS 15+) |
| `sox-ng` | SoX NG — maintained SoX fork for command-line audio processing (replaces sox) |

## 🧠 local-ai

Local models, inference engines, and contextual capture

| Id | Label |
|---|---|
| `ollama` | Ollama local-model CLI |
| `lm-studio` | LM Studio — local LLM desktop app |
| `jan` | Jan — local ChatGPT-style app |
| `anythingllm` | AnythingLLM — private local RAG/chat app |
| `mlx` | MLX — Apple Silicon engine for running local AI (not a chat app) |
| `mlx-lm` | mlx-lm — chat/generate/serve local LLMs on Apple Silicon using MLX |
| `ollama-app` | Ollama desktop app (Homebrew cask) |
| `screenpipe` | screenpipe — local screen/audio capture (official stable DMG updater) |
| `llama-cpp` | llama.cpp — local LLM inference engine and server |
| `llama-app` | Llama — official local LLM menu-bar app |
| `localai` | LocalAI — OpenAI-compatible local inference server |
| `ramalama` | RamaLama — run local models via containers |
| `osaurus` | Osaurus — MLX-based local LLM server app (macOS 15+) |
| `mlx-vlm` | mlx-vlm — vision-language models on Apple Silicon via MLX |
| `hf` | Hugging Face CLI (hf) — model download and hub management |
| `open-webui` | Open WebUI — self-hosted chat UI for Ollama/OpenAI-compatible APIs (Python 3.11–3.12) |

## ⚡ automation

General-purpose agents and workflow automation

| Id | Label |
|---|---|
| `hermes` | Hermes Agent — Nous Research |
| `openclaw` | OpenClaw — personal/local AI assistant CLI |
| `grokbot` | Grok Bot — xAI teammates that work across your apps |
| `n8n` | n8n — workflow automation via the official npm package |

## 🔧 llm-utils

Unix-pipe LLM CLIs

| Id | Label |
|---|---|
| `llm` | llm — Simon Willison Unix LLM CLI |
| `fabric` | fabric-ai — Daniel Miessler prompt-pattern CLI |
| `sgpt` | shell-gpt (sgpt) via uv |
| `repomix` | Repomix — pack a repository into one AI-friendly file |
| `markitdown` | MarkItDown — Microsoft file-to-Markdown converter for LLMs |

## 🛠️ dev-utils

Development, search, data, and deployment utilities

| Id | Label |
|---|---|
| `gh` | GitHub CLI |
| `wrangler` | Cloudflare Workers CLI — official npm package (wrangler) |
| `jq` | jq command-line JSON processor |
| `yq` | yq command-line YAML, JSON, XML, CSV, and properties processor |
| `ripgrep` | ripgrep fast recursive search (rg) |
| `fd` | fd fast, user-friendly find replacement |
| `just` | just project command runner |
| `shellcheck` | ShellCheck shell-script static analyzer |
| `actionlint` | actionlint GitHub Actions workflow checker |
| `mcp-inspector` | MCP Inspector — visual testing tool for MCP servers |

## 🔌 adapters

Glue between agents and editors

| Id | Label |
|---|---|
| `pi-acp` | Pi ACP adapter (pi-acp) for T3 Code / editors |
| `claude-acp` | Claude Agent ACP adapter (@agentclientprotocol/claude-agent-acp) for Zed / editors |
| `codex-acp` | Codex ACP adapter (@agentclientprotocol/codex-acp) for Zed / editors |

## 🍺 homebrew

Homebrew extras outside the managed catalog, plus a short recommended list

| Child | What |
|---|---|
| `casks` | GUI apps Homebrew already installed on your Mac |
| `fonts` | Fonts installed via Homebrew, plus available font casks in the full catalog view |
| `formulae` | CLI formulae Homebrew already installed on your Mac |
| `libraries` | Libraries Homebrew already installed on your Mac |
| `recommended` | Popular extras you can add — aiup does not pass --zap or directly delete ~/Library; Homebrew/vendor behavior can vary |
| `available` | Formulae and non-font casks available from your installed Homebrew taps |

Recommended extras:

| Type | Id | Label |
|---|---|---|
| cask | `raycast` | Raycast launcher |
| cask | `obsidian` | Obsidian notes |
| cask | `docker` | Docker Desktop |
| cask | `linear` | Linear issue tracker |
| cask | `notion` | Notion |
| cask | `copilot-cli` | GitHub Copilot CLI (Homebrew cask) |
| cask | `cursor-cli` | Cursor Agent CLI cask |
| cask | `claude-code` | Claude Code cask |
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
| cask | `kitty` | Kitty terminal |
| cask | `neovide` | Neovide (Neovim GUI) |
| cask | `fork` | Fork git client |
| cask | `sublime-merge` | Sublime Merge |
| cask | `figma` | Figma |
| cask | `brave-browser` | Brave Browser |
| cask | `firefox` | Firefox |
| cask | `utm` | UTM virtual machines |
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
| formula | `direnv` | direnv |
| formula | `just` | just command runner |
| formula | `yarn` | yarn |
| formula | `podman` | Podman |
| formula | `kubectl` | kubectl |
| formula | `helm` | Helm |
| formula | `terraform` | Terraform |

