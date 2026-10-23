# Catalog (2026.10.23-01)

Generated from `macos/aiup` via `scripts/sync-public-docs` (one `catalog --json` export).

## ⚙️ Essentials (`infra`)

Runtimes and installers other tools need

| Id | Label |
|---|---|
| `brew` | Homebrew: required for formulae, casks, and Node/npm on this system (not removable) |
| `npm` | Node/npm via Homebrew (infrastructure; update-only, not removable) |
| `uv` | Astral uv/uvx: Python toolchain (also installs the uv-tool items) |
| `fzf` | fzf fuzzy finder: required interactive catalog |
| `deno` | Deno runtime |
| `bun` | Bun JavaScript runtime, bundler, test runner, and package manager |
| `pnpm` | pnpm fast, disk-efficient JavaScript package manager (official npm package) |
| `mise` | mise: polyglot runtime/tool version manager |

## 🤖 Coding assistants (`coding-agents`)

Agents that write and edit code in the terminal

| Id | Label |
|---|---|
| `claude` | Claude Code: Anthropic native CLI |
| `copilot` | GitHub Copilot CLI: @github/copilot |
| `codex` | OpenAI Codex CLI: @openai/codex |
| `antigravity` | Google Antigravity CLI (agy) |
| `grok` | Grok Build: xAI official CLI |
| `gemini` | Google Gemini CLI: enterprise and API key accounts only; personal accounts moved to Antigravity CLI |
| `pi` | Pi coding agent: @earendil-works/pi-coding-agent |
| `kilo` | Kilo Code CLI: @kilocode/cli |
| `gsd2` | GSD (gsd-pi): @opengsd/gsd-pi |
| `opencode` | OpenCode 2: official installer |
| `warp` | Warp Agent CLI (warp) |
| `aider` | Aider: git-native pair programming CLI |
| `goose` | Goose: open-source agent CLI |
| `cursor` | Cursor CLI (agent; legacy cursor-agent) |
| `qwen` | Qwen Code: @qwen-code/qwen-code |
| `crush` | Crush: Charm agentic TUI (@charmland/crush) |
| `amp` | Amp: frontier coding agent CLI |
| `kiro` | Kiro CLI: Amazon Q Developer CLI successor |
| `droid` | Factory Droid: Factory.ai coding agent |
| `kimi` | Kimi Code CLI: Moonshot (kimi-code) |
| `cline` | Cline CLI: npm cline |
| `vibe` | Mistral Vibe: open-source CLI coding assistant |
| `devin-cli` | Devin CLI: Cognition coding agent |
| `auggie` | Auggie: Augment Code CLI (@augmentcode/auggie) |
| `junie` | Junie CLI: JetBrains coding agent (@jetbrains/junie) |
| `letta` | Letta Code: stateful agent CLI (@letta-ai/letta-code) |
| `qoder` | Qoder CLI: @qoder-ai/qodercli |
| `muse-code` | Muse Code: Meta terminal coding agent (muse) |
| `minimax-code` | MiniMax Code: open-source terminal coding agent (mcode) |
| `codebuddy-code` | CodeBuddy Code: Tencent terminal coding agent (codebuddy) |
| `codewhale` | Codewhale: terminal coding agent (formerly DeepSeek TUI) |
| `dcode` | Deep Agents Code: LangChain terminal coding agent (dcode) |
| `forgecode` | Forge Code: terminal coding agent (forge) |
| `vtcode` | VT Code: Rust terminal coding agent with ACP |
| `jcode` | jcode: Rust coding agent for the terminal |
| `gptme` | gptme: open-source AI assistant in your terminal |
| `code-puppy` | Code Puppy: open-source terminal coding agent |
| `command-code` | Command Code: terminal coding agent (commandcode) |
| `nanocoder` | Nanocoder: local-first terminal coding agent |
| `codebuff` | Codebuff: terminal coding agent |

## 🧰 Agent helpers (`agent-tools`)

Add-ons for coding agents: usage reports, specs, task lists, rules

| Id | Label |
|---|---|
| `ccusage` | ccusage: token and cost reports from local agent logs |
| `claude-squad` | Claude Squad: run several agents in tmux and git worktrees (cs) |
| `claude-code-router` | Claude Code Router: send Claude Code requests to other model providers (ccr) |
| `skills` | skills: Vercel CLI that adds agent skills to a project |
| `specify` | Spec Kit (specify): GitHub toolkit for spec-driven development |
| `openspec` | OpenSpec: spec-driven development for coding agents |
| `beads` | Beads: issue tracker that coding agents use as memory (bd) |
| `backlog-md` | Backlog.md: Markdown task board inside a Git repository (backlog) |
| `rulesync` | rulesync: one set of rules, written out for each coding agent |
| `cq` | cq: shared knowledge store so agents avoid known mistakes |
| `agent-deck` | Agent Deck: one terminal UI for many coding agent sessions |
| `git-gtr` | git-gtr: CodeRabbit git worktree runner for parallel agents (gtr) |
| `worktrunk` | Worktrunk: git worktrees for parallel agent work (wt) |
| `apm` | APM: Microsoft package manager for agent configuration |
| `peekaboo` | Peekaboo: screenshots and UI automation for agents (macOS 15+) |
| `codexbar` | CodexBar: menu bar view of coding agent limits and usage (macOS 14+) |
| `coderabbit` | CodeRabbit CLI: AI code review in the terminal (account required) |

## 🖥️ Agent workspaces (`workspaces`)

Desktop apps that run and manage coding agents

| Id | Label |
|---|---|
| `t3-code` | T3 Code: desktop hub that drives Codex/Claude/Grok/OpenCode |
| `t3-nightly` | T3 Code Nightly: desktop hub (nightly build) |
| `opencode-desktop` | OpenCode desktop client |
| `hermes-desktop` | Hermes Desktop: official Nous GUI for the same agent as the Hermes CLI |
| `conductor` | Conductor: run parallel Claude Code/Codex agents in worktrees |
| `emdash` | Emdash: run multiple coding agents in parallel |
| `superset` | Superset: terminal workspace for orchestrating coding agents |
| `amp-app` | Amp desktop app: agent environment (macOS 26+) |
| `factory-app` | Factory desktop: native interface for Factory Droids |
| `antigravity-app` | Google Antigravity 2: agent orchestration hub app |
| `cline-app` | Cline desktop app: coding agent |
| `kiro-crew` | KiroCrew: multi-agent development workspace |
| `nimbalyst` | Nimbalyst: visual workspace for Codex and Claude Code |
| `commander` | Commander: AI agent operator app (macOS 15+) |
| `zcode` | ZCode: Z.ai agentic development environment |
| `zed-delta` | Delta: multiplayer coding with agents (Apple silicon, macOS 13+) |

## ✏️ Code editors (`editors`)

Places you type code

| Id | Label |
|---|---|
| `vscode` | Visual Studio Code |
| `vscode-insiders` | VS Code Insiders |
| `cursor-ide` | Cursor IDE app |
| `zed` | Zed editor app |
| `antigravity-ide` | Google Antigravity IDE |
| `devin-desktop` | Devin Desktop: agentic IDE (formerly Windsurf) |
| `kiro-ide` | Kiro IDE: spec-driven agentic IDE (distinct from Kiro CLI) |
| `jetbrains-air` | JetBrains Air: agentic development environment |
| `trae` | Trae: AI IDE from ByteDance |
| `codebuddy-ide` | CodeBuddy IDE: Tencent AI IDE |

## ⌨️ Terminals (`terminals`)

Places you run commands

| Id | Label |
|---|---|
| `cmux` | cmux: terminal for running coding agents (not an agent itself) |
| `warp-app` | Warp terminal (desktop; distinct from Warp Agent CLI) |
| `ghostty` | Ghostty terminal |
| `iterm2` | iTerm2 terminal |
| `kitty` | kitty: GPU-based terminal |

## 🧩 MCP tools (`mcp`)

Tools to run, test and connect MCP servers

| Id | Label |
|---|---|
| `mcp-inspector` | MCP Inspector: visual testing tool for MCP servers |
| `ctx7` | Context7 CLI (ctx7): current library docs for agents |
| `mcp-proxy` | mcp-proxy: bridge stdio and HTTP MCP transports |
| `mcp-remote` | mcp-remote: connect local MCP clients to remote servers that use OAuth |
| `mcpc` | mcpc: Apify command-line MCP client |
| `supergateway` | Supergateway: serve stdio MCP servers over SSE or WebSocket |
| `toolhive-studio` | ToolHive: desktop app to install and run MCP servers (macOS 13+) |
| `playwright-mcp` | Playwright MCP: Microsoft browser control server for MCP clients |
| `chrome-devtools-mcp` | Chrome DevTools MCP: Google server that lets agents inspect and debug Chrome |
| `thv` | ToolHive CLI (thv): run and manage MCP servers from the terminal |
| `mcpd` | mcpd: Mozilla.ai tool to define and run MCP servers from one config file |
| `mcporter` | MCPorter: call MCP servers from the terminal or TypeScript |
| `github-mcp-server` | GitHub MCP Server: GitHub tools for AI clients |
| `mcp-toolbox` | MCP Toolbox: Google MCP server for databases (toolbox) |
| `mcp-publisher` | MCP Publisher: publish servers to the official MCP Registry |

## 🛡️ Sandboxes (`sandboxes`)

Containers and sandboxes for running agents apart from your files

| Id | Label |
|---|---|
| `srt` | Sandbox Runtime (srt): Anthropic file and network sandbox for agents |
| `container` | Apple container: Linux containers in lightweight VMs (Apple silicon, macOS 26+) |
| `orbstack` | OrbStack: Docker containers and Linux machines (macOS 14+) |
| `sbx` | Docker Sandboxes (sbx): run coding agents in isolated sandboxes (Apple silicon, macOS 14+) |
| `daytona` | Daytona CLI: manage cloud sandboxes for AI-generated code (account required) |
| `e2b` | E2B CLI: manage cloud sandboxes and templates (account required) |
| `openshell` | OpenShell: NVIDIA private runtime for autonomous agents (early release) |
| `lume` | Lume: macOS and Linux VMs for agents, from Cua (Apple silicon, macOS 15+) |
| `arcbox` | ArcBox: containers, Linux VMs and agent sandboxes (Apple silicon, macOS 15+) |

## 🔌 Integrations (`adapters`)

Glue between agents and editors (ACP)

| Id | Label |
|---|---|
| `pi-acp` | Pi ACP adapter (pi-acp, community) for T3 Code and editors |
| `claude-acp` | Claude Agent ACP adapter (@agentclientprotocol/claude-agent-acp) for Zed / editors |
| `codex-acp` | Codex ACP adapter (@agentclientprotocol/codex-acp) for Zed / editors |
| `amp-acp` | Amp ACP adapter (amp-acp, community) for Zed and editors |
| `acpx` | acpx: headless ACP client for driving agents from scripts |
| `fast-agent` | fast-agent: MCP-native agent framework that also runs over ACP |

## 💬 Chat assistants (`chat`)

Cloud chat apps

| Id | Label |
|---|---|
| `chatgpt` | ChatGPT desktop app (includes Codex) |
| `claude-app` | Claude desktop app (not Claude Code CLI) |
| `copilot-app` | GitHub Copilot native desktop app |
| `perplexity` | Perplexity desktop (Personal Computer agent, macOS 15+) |
| `gemini-app` | Google Gemini desktop app (macOS 15+) |
| `cherry-studio` | Cherry Studio: multi-provider LLM desktop client |
| `msty-studio` | Msty Studio: local and online model desktop app |
| `boltai` | BoltAI: native macOS AI chat client |
| `chatbox` | Chatbox: multi-provider AI chat desktop app |
| `lobehub` | LobeHub: open-source AI chat/agent desktop app |
| `poe` | Poe: Quora chat app with models from many providers |

## 🌐 AI browsers (`browsers`)

Web browsers with an AI assistant or agent built in

| Id | Label |
|---|---|
| `dia` | Dia: AI browser from The Browser Company (macOS 14+) |
| `comet` | Comet: Perplexity browser with a built-in assistant |
| `browseros` | BrowserOS: open-source agentic browser |
| `agent-browser` | agent-browser: Vercel browser automation CLI for coding agents |
| `browser-use` | Browser Use: lets an agent drive your own Chrome from the terminal |
| `playwright-cli` | Playwright CLI: Microsoft browser automation commands for coding agents |

## ⚡ Automation (`automation`)

General-purpose agents and workflow automation

| Id | Label |
|---|---|
| `hermes` | Hermes Agent: Nous Research |
| `openclaw` | OpenClaw: personal/local AI assistant CLI |
| `grokbot` | Grok Bot: xAI teammates that work across your apps |
| `n8n` | n8n: workflow automation via the official npm package |
| `manus` | Manus Studio: Manus agent for tasks on your computer |
| `langflow` | Langflow Desktop: low-code AI workflow builder |
| `docker-agent` | Docker Agent: build and run AI agents from a config file |

## 🧠 Local models (`local-ai`)

Model runtimes and servers that run on your Mac

| Id | Label |
|---|---|
| `ollama` | Ollama local-model CLI |
| `mlx` | MLX: Apple Silicon engine for running local AI (not a chat app) |
| `mlx-lm` | mlx-lm: chat/generate/serve local LLMs on Apple Silicon using MLX |
| `llama-cpp` | llama.cpp: local LLM inference engine and server |
| `localai` | LocalAI: OpenAI-compatible local inference server |
| `ramalama` | RamaLama: run local models via containers |
| `mlx-vlm` | mlx-vlm: vision-language models on Apple Silicon via MLX |
| `hf` | Hugging Face CLI (hf): model download and hub management |
| `apfel` | apfel: Apple Intelligence from the command line, with an OpenAI-compatible server (macOS 26+) |
| `rapid-mlx` | Rapid-MLX: local MLX inference server with an OpenAI-compatible API (macOS 14+) |
| `tei` | Text Embeddings Inference: Hugging Face embeddings server |
| `shimmy` | Shimmy: small OpenAI-compatible server for GGUF models |
| `gollama` | Gollama: manage Ollama models in a terminal UI |
| `llmfit` | llmfit: find which models run on your hardware |
| `mlx-knife` | MLX Knife (mlxk): manage and run MLX models |
| `vllm-metal` | vLLM Metal: vLLM inference server on Apple silicon (macOS 15+, large install) |
| `omlx` | oMLX: MLX inference server with batching and an SSD cache (macOS 15+, builds from source) |
| `splash` | Splash: Inco AI local inference engine for coding agents (M3 or newer, macOS 26.4+) |
| `mlx-serve-cli` | mlx-serve: the MLX-Serve model server without the app (macOS 26.2+) |
| `foundry-local` | Foundry Local: Microsoft CLI for running models locally (preview, macOS 15+) |
| `llama-swap` | llama-swap: swap models behind one OpenAI-compatible endpoint |
| `cactus` | Cactus: on-device AI inference CLI (Apple silicon, macOS 14+) |

## 💻 Local AI apps (`local-apps`)

Desktop apps for running models on your Mac

| Id | Label |
|---|---|
| `lm-studio` | LM Studio: local LLM desktop app |
| `jan` | Jan: local ChatGPT-style app |
| `anythingllm` | AnythingLLM: private local RAG/chat app |
| `ollama-app` | Ollama desktop app |
| `screenpipe` | screenpipe: local screen/audio capture (official stable DMG updater) |
| `llama-app` | Llama: official local LLM menu-bar app |
| `osaurus` | Osaurus: MLX-based local LLM server app (macOS 15+) |
| `open-webui` | Open WebUI: self-hosted chat UI for Ollama/OpenAI-compatible APIs (Python 3.11–3.12) |
| `vmlx` | vMLX: run local models on Apple silicon (macOS 14+) |
| `swama` | Swama: MLX model runtime app (macOS 15+) |
| `nativ` | Nativ: run models locally (macOS 26+) |
| `dayflow` | Dayflow: a timeline of your day from your screen activity (macOS 14+) |
| `mlx-serve` | MLX-Serve: local model server app with OpenAI and Anthropic APIs (macOS 26+) |
| `nvidia-pair` | NVIDIA PAIR: share local inference across your computers (macOS 13+) |
| `unsloth` | Unsloth Studio: run and fine-tune models locally (beta, Apple silicon) |
| `lm-studio-bionic` | Bionic: LM Studio agent that works with open models (Apple silicon) |

## 🎙️ Voice and dictation (`voice`)

Dictation, transcription, meeting notes and speech

| Id | Label |
|---|---|
| `macwhisper` | MacWhisper: local speech-to-text |
| `whisper-cpp` | whisper.cpp local speech-to-text engine (model files are separate) |
| `superwhisper` | Superwhisper: AI dictation and LLM reformatting; vendor licensing applies |
| `buzz` | Buzz: audio transcription and translation; models downloaded separately |
| `whisperkit` | WhisperKit CLI: Argmax on-device speech recognition (models separate) |
| `handy` | Handy: open-source local speech-to-text dictation |
| `voiceink` | VoiceInk: local AI dictation (macOS 15+) |
| `wispr-flow` | Wispr Flow: AI dictation; vendor account required |
| `fluidvoice` | FluidVoice: open-source offline dictation (macOS 15+) |
| `spokenly` | Spokenly: dictation with local and cloud models |
| `typeless` | Typeless: cloud AI dictation that drops filler words |
| `hex` | Hex: open-source push-to-talk dictation (macOS 14+) |
| `amical` | Amical: open-source local dictation and notes |
| `openwhispr` | OpenWhispr: open-source dictation with local or cloud models |
| `aqua-voice` | Aqua Voice: cloud voice typing |
| `monologue` | Monologue: AI dictation from Every (macOS 14+) |
| `granola` | Granola: AI meeting notes without a bot in the call |
| `meetily` | Meetily: open-source local meeting transcription |
| `anarlog` | Anarlog: open-source local meeting notes, formerly Hyprnote (macOS 15+) |
| `mlx-audio` | mlx-audio: speech-to-text and text-to-speech on Apple silicon |
| `parakeet-mlx` | parakeet-mlx: NVIDIA Parakeet transcription on MLX |
| `piper` | Piper: fast local text-to-speech |
| `pocket-tts` | Pocket TTS: Kyutai text-to-speech that runs on the CPU |
| `speech-swift` | speech-swift: on-device transcription, speech and speaker labels (Apple silicon, macOS 15+) |

## 🎨 Image and video AI (`image-gen`)

Apps and tools that generate images and video

| Id | Label |
|---|---|
| `draw-things` | Draw Things: local AI image generation; models downloaded separately |
| `stability-matrix` | Stability Matrix: Stable Diffusion package manager and inference UI |
| `mochi-diffusion` | Mochi Diffusion: native Core ML Stable Diffusion (macOS 15+) |
| `comfyui` | Comfy Desktop: official ComfyUI app for image, video and audio generation (Apple silicon) |
| `ltx-desktop` | LTX Desktop: Lightricks video generation on your Mac |
| `mflux` | mflux: FLUX image generation on MLX |

## 🎬 Creative apps (`media`)

Editors and recorders for video, images, audio and 3D

| Id | Label |
|---|---|
| `remotion` | Remotion CLI: React video tooling (@remotion/cli); projects need matching local dependencies |
| `audacity` | Audacity: audio editing and recording |
| `obs` | OBS Studio: recording and streaming |
| `blender` | Blender: 3D modeling, animation, and rendering |
| `losslesscut` | LosslessCut: lossless audio/video trimming |
| `handbrake-app` | HandBrake: desktop video transcoding |
| `shotcut` | Shotcut: video editing |
| `kdenlive` | Kdenlive: non-linear video editing |
| `krita` | Krita: digital painting and illustration (media utility; AI plugins are separate) |
| `inkscape` | Inkscape: vector graphics and SVG editing |
| `gimp` | GIMP: open-source image editor |
| `cap` | Cap: open-source screen recorder |

## 🎞️ Media tools (`media-tools`)

Command-line tools for converting and downloading media

| Id | Label |
|---|---|
| `ffmpeg` | FFmpeg: audio/video conversion and encoding |
| `imagemagick` | ImageMagick: command-line image conversion and processing (magick) |
| `yt-dlp` | yt-dlp: command-line audio/video downloads |
| `vips` | libvips: efficient image processing CLI/library |
| `sox-ng` | SoX NG: maintained SoX fork for command-line audio processing (replaces sox) |
| `mkvtoolnix` | MKVToolNix: Matroska video tools (mkvmerge) |

## 🔧 AI utilities (`llm-utils`)

Command-line LLM tools, and converters that turn files into text for models

| Id | Label |
|---|---|
| `llm` | llm: Simon Willison Unix LLM CLI |
| `fabric` | fabric-ai: Daniel Miessler prompt-pattern CLI |
| `sgpt` | shell-gpt (sgpt) via uv |
| `repomix` | Repomix: pack a repository into one AI-friendly file |
| `markitdown` | MarkItDown: Microsoft file-to-Markdown converter for LLMs |
| `docling` | Docling: turn PDFs and office documents into text for models (large install) |
| `pandoc` | Pandoc: convert between document formats |
| `defuddle` | Defuddle: pull the main content of a web page as Markdown |
| `oracle` | Oracle: send prompts and files to a second model for review (API key required) |
| `rtk` | RTK: cut the tokens dev commands send to agents |
| `promptfoo` | promptfoo: test and red-team LLM prompts locally |

## 🛠️ Developer tools (`dev-utils`)

Development, search, data, and deployment utilities

| Id | Label |
|---|---|
| `gh` | GitHub CLI |
| `wrangler` | Cloudflare Workers CLI: official npm package (wrangler) |
| `jq` | jq command-line JSON processor |
| `yq` | yq command-line YAML, JSON, XML, CSV, and properties processor |
| `ripgrep` | ripgrep fast recursive search (rg) |
| `fd` | fd fast, user-friendly find replacement |
| `just` | just project command runner |
| `shellcheck` | ShellCheck shell-script static analyzer |
| `actionlint` | actionlint GitHub Actions workflow checker |
| `ast-grep` | ast-grep: structural code search and rewrite (sg) |
| `tmux` | tmux: terminal multiplexer |
| `supabase` | Supabase CLI: local Postgres development and deploys |
| `vercel` | Vercel CLI: deploy and manage Vercel projects |
| `android-cli` | Android CLI: Google tool for Android development with agents (android) |

## 🍺 Other packages (`homebrew`)

Homebrew extras outside the managed catalog, plus a short recommended list

| Child | What |
|---|---|
| `casks` | GUI apps Homebrew already installed on your Mac |
| `fonts` | Fonts installed via Homebrew, plus available font casks in the full catalog view |
| `formulae` | CLI formulae Homebrew already installed on your Mac |
| `libraries` | Libraries Homebrew already installed on your Mac |
| `recommended` | Popular extras you can add. aiup does not pass --zap or directly delete ~/Library; Homebrew/vendor behavior can vary |
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
| cask | `monet` | Monet: mission control for coding agents |
| cask | `ollamac` | Ollamac local chat |
| cask | `notesollama` | NotesOllama |
| cask | `tableplus` | TablePlus database GUI |
| cask | `postman` | Postman API client |
| cask | `insomnia` | Insomnia API client |
| cask | `1password` | 1Password |
| cask | `secretive` | Secretive SSH keys |
| cask | `stats` | Stats menu-bar monitors |
| cask | `iina` | IINA media player |
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

