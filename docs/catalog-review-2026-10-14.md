# Catalog review | 2026-10-14

Status date: **2026-10-14**. Runtime version: **2026.09.29-06** (unreleased changes).

I went through what has shipped since the 2026-09-29 review: new coding agents, agent add-ons, MCP tools, sandboxes, AI browsers, dictation and meeting apps, local model servers, and image and video generators. This record lists what I added, what moved, and what I left out and why.

The review ran in two passes on the same day. The first pass added 87 entries (131 to 218). The second pass added 43 more (218 to 261): tools that needed a Homebrew tap, five browser automation tools, Poe, and others I found while checking taps. It also gave tools a choice of install channel, so a tool can install from npm, PyPI or its own installer when Homebrew is behind. Nothing was removed. The current list is in [catalog.md](catalog.md).

## How each addition was checked

Every new entry passed the same checks as the earlier reviews ([catalog research](catalog-research.md)):

- It installs from an official channel aiup already handles: a core Homebrew formula or cask, an npm package, or a PyPI package through uv. I read the Homebrew metadata (`brew info --json=v2`), the formula source, `npm view` or the PyPI JSON for each one.
- It had a release in the last three months, and Homebrew does not mark it deprecated or disabled.
- The command name or app bundle aiup looks for matches what the package really installs, so detection and removal point at the right thing.
- Nothing needs a `curl | sh` installer aiup has not reviewed, or a background service. In the first pass nothing needed a Homebrew tap either. The second pass allowed taps run by the tool's own publisher (see [Second pass](#second-pass-taps-browser-tools-and-poe)).

macOS floors that are stricter than aiup's own macOS 14 baseline are in the labels, for example `(macOS 15+)` or `(Apple silicon, macOS 26+)`.

## New categories

The list had grown to the point where `media`, `local-ai` and `dev-utils` mixed very different things. I split them and added categories for kinds of tools that did not have a home. The old category ids stay, so `--category` filters and scripts that read `catalog --json` still work. Tools that moved now answer to their new id, for example `aiup list --category voice` for MacWhisper.

| Category | Id | What moved in |
|---|---|---|
| Agent helpers | `agent-tools` | New: usage reports, spec kits, task boards and rules sync for coding agents |
| MCP tools | `mcp` | `mcp-inspector` from `dev-utils`, plus new MCP proxies, clients and ToolHive |
| Sandboxes | `sandboxes` | New: Anthropic's Sandbox Runtime, Apple container and OrbStack |
| AI browsers | `browsers` | New: Dia, Comet and BrowserOS |
| Local AI apps | `local-apps` | Desktop apps from `local-ai`: LM Studio, Jan, AnythingLLM, the Ollama and Llama apps, Osaurus, screenpipe and Open WebUI |
| Voice and dictation | `voice` | From `media`: MacWhisper, Superwhisper, Buzz, Handy, VoiceInk, Wispr Flow, whisper.cpp and WhisperKit |
| Image and video AI | `image-gen` | From `media`: Draw Things, Mochi Diffusion and Stability Matrix |
| Media tools | `media-tools` | From `media`: FFmpeg, ImageMagick, libvips, yt-dlp and SoX NG |

Renamed headings: `workspaces` is now **Agent workspaces**, `local-ai` is **Local models** (runtimes and servers), and `media` is **Creative apps** (editors and recorders).

## Added

### Coding assistants

| Id | What | Installs from |
|---|---|---|
| `muse-code` | [Muse Code: Meta terminal coding agent (muse)](https://dev.meta.ai/) | Homebrew cask `muse-code` |
| `minimax-code` | [MiniMax Code: open-source terminal coding agent (mcode)](https://agent.minimax.io/docs/cli/quick-start) | npm `@minimax-ai/code` |
| `codebuddy-code` | [CodeBuddy Code: Tencent terminal coding agent (codebuddy)](https://www.npmjs.com/package/@tencent-ai/codebuddy-code) | npm `@tencent-ai/codebuddy-code` |
| `codewhale` | [Codewhale: terminal coding agent (formerly DeepSeek TUI)](https://github.com/codewhale-hq/Codewhale) | npm `codewhale` |
| `dcode` | [Deep Agents Code: LangChain terminal coding agent (dcode)](https://docs.langchain.com/oss/deepagents/code/overview) | uv (PyPI) `deepagents-code` |
| `forgecode` | [Forge Code: terminal coding agent (forge)](https://forgecode.dev/) | Homebrew formula `forgecode` |
| `vtcode` | [VT Code: Rust terminal coding agent with ACP](https://github.com/vinhnx/VTCode) | Homebrew formula `vtcode` |
| `jcode` | [jcode: Rust coding agent for the terminal](https://jcode.sh) | Homebrew formula `jcode` |
| `gptme` | [gptme: open-source AI assistant in your terminal](https://gptme.org/docs/) | uv (PyPI) `gptme` (Homebrew alternate) |
| `code-puppy` | [Code Puppy: open-source terminal coding agent](https://github.com/mpfaffenberger/code_puppy) | uv (PyPI) `code-puppy` |
| `command-code` | [Command Code: terminal coding agent (commandcode)](https://commandcode.ai/docs) | npm `command-code` |
| `nanocoder` | [Nanocoder: local-first terminal coding agent](https://github.com/Nano-Collective/nanocoder) | npm `@nanocollective/nanocoder` |
| `codebuff` | [Codebuff: terminal coding agent](https://www.codebuff.com/) | npm `codebuff` |

### Agent helpers (new)

| Id | What | Installs from |
|---|---|---|
| `ccusage` | [ccusage: token and cost reports from local agent logs](https://github.com/ccusage/ccusage) | npm `ccusage` (Homebrew `ccusage` as an alternate) |
| `claude-squad` | [Claude Squad: run several agents in tmux and git worktrees (cs)](https://smtg-ai.github.io/claude-squad/) | Homebrew formula `claude-squad` |
| `claude-code-router` | [Claude Code Router: send Claude Code requests to other model providers (ccr)](https://github.com/musistudio/claude-code-router) | npm `@musistudio/claude-code-router` (Homebrew alternate) |
| `skills` | [skills: Vercel CLI that adds agent skills to a project](https://github.com/vercel-labs/skills) | npm `skills` |
| `specify` | [Spec Kit (specify): GitHub toolkit for spec-driven development](https://github.com/github/spec-kit) | uv (PyPI) `specify-cli` |
| `openspec` | [OpenSpec: spec-driven development for coding agents](https://openspec.dev/) | npm `@fission-ai/openspec` (Homebrew alternate) |
| `beads` | [Beads: issue tracker that coding agents use as memory (bd)](https://github.com/gastownhall/beads) | Homebrew formula `beads` |
| `backlog-md` | [Backlog.md: Markdown task board inside a Git repository (backlog)](https://github.com/MrLesk/Backlog.md) | npm `backlog.md` (Homebrew alternate) |
| `rulesync` | [rulesync: one set of rules, written out for each coding agent](https://github.com/dyoshikawa/rulesync) | npm `rulesync` |

### Agent workspaces

| Id | What | Installs from |
|---|---|---|
| `cline-app` | [Cline desktop app: coding agent](https://cline.bot/) | Homebrew cask `cline-app` |
| `kiro-crew` | [KiroCrew: multi-agent development workspace](https://kiro.dev/docs/crew/) | Homebrew cask `kirocrew` |
| `nimbalyst` | [Nimbalyst: visual workspace for Codex and Claude Code](https://nimbalyst.com/) | Homebrew cask `nimbalyst` |
| `commander` | [Commander: AI agent operator app (macOS 15+)](https://thecommander.app/) | Homebrew cask `commander` |
| `zcode` | [ZCode: Z.ai agentic development environment](https://zcode.z.ai/en/) | Homebrew cask `zcode` |

### Code editors

| Id | What | Installs from |
|---|---|---|
| `trae` | [Trae: AI IDE from ByteDance](https://www.trae.ai/) | Homebrew cask `trae` |
| `codebuddy-ide` | [CodeBuddy IDE: Tencent AI IDE](https://www.codebuddy.ai/ide/) | Homebrew cask `codebuddy` |

### Terminals

| Id | What | Installs from |
|---|---|---|
| `kitty` | [kitty: GPU-based terminal](https://sw.kovidgoyal.net/kitty/) | Homebrew cask `kitty` |

### MCP tools (new)

| Id | What | Installs from |
|---|---|---|
| `ctx7` | [Context7 CLI (ctx7): current library docs for agents](https://github.com/upstash/context7) | npm `ctx7` |
| `mcp-proxy` | [mcp-proxy: bridge stdio and HTTP MCP transports](https://github.com/sparfenyuk/mcp-proxy) | uv (PyPI) `mcp-proxy` (Homebrew alternate) |
| `mcp-remote` | [mcp-remote: connect local MCP clients to remote servers that use OAuth](https://github.com/geelen/mcp-remote) | npm `mcp-remote` (Homebrew alternate) |
| `mcpc` | [mcpc: Apify command-line MCP client](https://github.com/apify/mcpc) | npm `@apify/mcpc` (Homebrew alternate) |
| `supergateway` | [Supergateway: serve stdio MCP servers over SSE or WebSocket](https://github.com/supercorp-ai/supergateway) | npm `supergateway` |
| `toolhive-studio` | [ToolHive: desktop app to install and run MCP servers (macOS 13+)](https://github.com/stacklok/toolhive-studio) | Homebrew cask `toolhive-studio` |

### Sandboxes (new)

| Id | What | Installs from |
|---|---|---|
| `srt` | [Sandbox Runtime (srt): Anthropic file and network sandbox for agents](https://github.com/anthropics/sandbox-runtime) | npm `@anthropic-ai/sandbox-runtime` |
| `container` | [Apple container: Linux containers in lightweight VMs (Apple silicon, macOS 26+)](https://github.com/apple/container) | Homebrew formula `container` |
| `orbstack` | [OrbStack: Docker containers and Linux machines (macOS 14+)](https://orbstack.dev/) | Homebrew cask `orbstack` |

### Integrations

| Id | What | Installs from |
|---|---|---|
| `amp-acp` | [Amp ACP adapter (amp-acp, community) for Zed and editors](https://github.com/tao12345666333/amp-acp) | npm `amp-acp` |
| `acpx` | [acpx: headless ACP client for driving agents from scripts](https://github.com/openclaw/acpx) | npm `acpx` |
| `fast-agent` | [fast-agent: MCP-native agent framework that also runs over ACP](https://fast-agent.ai/) | uv (PyPI) `fast-agent-mcp` |

### AI browsers (new)

| Id | What | Installs from |
|---|---|---|
| `dia` | [Dia: AI browser from The Browser Company (macOS 14+)](https://www.diabrowser.com/) | Homebrew cask `thebrowsercompany-dia` |
| `comet` | [Comet: Perplexity browser with a built-in assistant](https://www.perplexity.ai/comet) | Homebrew cask `comet` |
| `browseros` | [BrowserOS: open-source agentic browser](https://www.browseros.com/) | Homebrew cask `browseros` |

### Automation

| Id | What | Installs from |
|---|---|---|
| `manus` | [Manus Studio: Manus agent for tasks on your computer](https://manus.im/desktop) | Homebrew cask `manus` |
| `langflow` | [Langflow Desktop: low-code AI workflow builder](https://www.langflow.org/desktop) | Homebrew cask `langflow` |

### Local models

| Id | What | Installs from |
|---|---|---|
| `apfel` | [apfel: Apple Intelligence from the command line, with an OpenAI-compatible server (macOS 26+)](https://apfel.franzai.com) | Homebrew formula `apfel` |
| `rapid-mlx` | [Rapid-MLX: local MLX inference server with an OpenAI-compatible API (macOS 14+)](https://github.com/raullenchai/Rapid-MLX) | uv (PyPI) `rapid-mlx` (Homebrew alternate) |
| `tei` | [Text Embeddings Inference: Hugging Face embeddings server](https://huggingface.co/docs/text-embeddings-inference/quick_tour) | Homebrew formula `text-embeddings-inference` |
| `shimmy` | [Shimmy: small OpenAI-compatible server for GGUF models](https://github.com/Michael-A-Kuykendall/shimmy) | Homebrew formula `shimmy` |
| `gollama` | [Gollama: manage Ollama models in a terminal UI](https://github.com/sammcj/gollama) | Homebrew formula `gollama` |
| `llmfit` | [llmfit: find which models run on your hardware](https://github.com/AlexsJones/llmfit) | Homebrew formula `llmfit` |
| `mlx-knife` | [MLX Knife (mlxk): manage and run MLX models](https://github.com/mzau/mlx-knife) | uv (PyPI) `mlx-knife` |

### Local AI apps (new)

| Id | What | Installs from |
|---|---|---|
| `vmlx` | [vMLX: run local models on Apple silicon (macOS 14+)](https://mlx.studio/) | Homebrew cask `vmlx` |
| `swama` | [Swama: MLX model runtime app (macOS 15+)](https://github.com/Trans-N-ai/swama) | Homebrew cask `swama` |
| `nativ` | [Nativ: run models locally (macOS 26+)](https://blaizzy.github.io/nativ/) | Homebrew cask `nativ` |
| `dayflow` | [Dayflow: a timeline of your day from your screen activity (macOS 14+)](https://github.com/JerryZLiu/Dayflow) | Homebrew cask `dayflow` |

### Voice and dictation (new)

| Id | What | Installs from |
|---|---|---|
| `fluidvoice` | [FluidVoice: open-source offline dictation (macOS 15+)](https://github.com/altic-dev/FluidVoice) | Homebrew cask `fluidvoice` |
| `spokenly` | [Spokenly: dictation with local and cloud models](https://spokenly.app/) | Homebrew cask `spokenly` |
| `typeless` | [Typeless: cloud AI dictation that drops filler words](https://typeless.com/) | Homebrew cask `typeless` |
| `hex` | [Hex: open-source push-to-talk dictation (macOS 14+)](https://hex.kitlangton.com/) | Homebrew cask `kitlangton-hex` |
| `amical` | [Amical: open-source local dictation and notes](https://amical.ai/) | Homebrew cask `amical` |
| `openwhispr` | [OpenWhispr: open-source dictation with local or cloud models](https://github.com/OpenWhispr/openwhispr) | Homebrew cask `openwhispr` |
| `aqua-voice` | [Aqua Voice: cloud voice typing](https://aquavoice.com/) | Homebrew cask `aqua-voice` |
| `monologue` | [Monologue: AI dictation from Every (macOS 14+)](https://www.monologue.to/) | Homebrew cask `monologue` |
| `granola` | [Granola: AI meeting notes without a bot in the call](https://www.granola.ai/) | Homebrew cask `granola` |
| `meetily` | [Meetily: open-source local meeting transcription](https://meetily.ai/) | Homebrew cask `meetily` |
| `anarlog` | [Anarlog: open-source local meeting notes, formerly Hyprnote (macOS 15+)](https://anarlog.so/) | Homebrew cask `anarlog` |
| `mlx-audio` | [mlx-audio: speech-to-text and text-to-speech on Apple silicon](https://github.com/Blaizzy/mlx-audio) | uv (PyPI) `mlx-audio` |
| `parakeet-mlx` | [parakeet-mlx: NVIDIA Parakeet transcription on MLX](https://github.com/senstella/parakeet-mlx) | uv (PyPI) `parakeet-mlx` |
| `piper` | [Piper: fast local text-to-speech](https://github.com/OHF-Voice/piper1-gpl) | uv (PyPI) `piper-tts` |
| `pocket-tts` | [Pocket TTS: Kyutai text-to-speech that runs on the CPU](https://github.com/kyutai-labs/pocket-tts) | uv (PyPI) `pocket-tts` (Homebrew alternate) |
| `speech-swift` | [speech-swift: on-device transcription, speech and speaker labels (Apple silicon, macOS 15+)](https://soniqo.audio) | Homebrew formula `speech` |

### Image and video AI (new)

| Id | What | Installs from |
|---|---|---|
| `comfyui` | [Comfy Desktop: official ComfyUI app for image, video and audio generation (Apple silicon)](https://docs.comfy.org/installation/desktop/macos) | Homebrew cask `comfy` |
| `ltx-desktop` | [LTX Desktop: Lightricks video generation on your Mac](https://github.com/Lightricks/LTX-Desktop) | Homebrew cask `ltx-desktop` |
| `mflux` | [mflux: FLUX image generation on MLX](https://github.com/mflux-community/mflux) | uv (PyPI) `mflux` |

### Creative apps

| Id | What | Installs from |
|---|---|---|
| `gimp` | [GIMP: open-source image editor](https://www.gimp.org/) | Homebrew cask `gimp` |
| `cap` | [Cap: open-source screen recorder](https://cap.so/) | Homebrew cask `cap` |

### Media tools (new)

| Id | What | Installs from |
|---|---|---|
| `mkvtoolnix` | [MKVToolNix: Matroska video tools (mkvmerge)](https://mkvtoolnix.download/) | Homebrew formula `mkvtoolnix` |

### AI utilities

| Id | What | Installs from |
|---|---|---|
| `docling` | [Docling: turn PDFs and office documents into text for models (large install)](https://github.com/docling-project/docling) | uv (PyPI) `docling` |
| `pandoc` | [Pandoc: convert between document formats](https://pandoc.org/) | Homebrew formula `pandoc` |
| `defuddle` | [Defuddle: pull the main content of a web page as Markdown](https://github.com/kepano/defuddle) | npm `defuddle` |

### Developer tools

| Id | What | Installs from |
|---|---|---|
| `ast-grep` | [ast-grep: structural code search and rewrite (sg)](https://ast-grep.github.io/) | npm `@ast-grep/cli` (Homebrew alternate) |
| `tmux` | [tmux: terminal multiplexer](https://github.com/tmux/tmux) | Homebrew formula `tmux` |
| `supabase` | [Supabase CLI: local Postgres development and deploys](https://supabase.com/docs/reference/cli/about) | Homebrew formula `supabase` |
| `vercel` | [Vercel CLI: deploy and manage Vercel projects](https://vercel.com/docs/cli) | npm `vercel` |

`kitty` and `tmux` were on the Homebrew recommended list. They are catalog entries now, so they left that list.

## Label and lifecycle changes

- `gemini` is now **sunset**. Homebrew deprecated the `gemini-cli` formula on 2026-06-18 as unsupported and plans to disable it on 2026-12-18; Google moved personal accounts to Antigravity CLI. The npm package still works for enterprise and API key accounts, so aiup keeps updating installed copies and asks before a new install from the list.
- `cursor` now says `agent`, the command Cursor installs today, and keeps `cursor-agent` as the older name.
- `amp` and `amp-app` no longer name Sourcegraph.
- `warp` drops the old Oz TUI name.
- `opencode` moved to OpenCode 2. The first pass said the installer gave you the 1.x line; the second pass switched aiup to the v2 installer (see below).
- `chatgpt` notes that the desktop app includes Codex.
- `pi-acp` is marked community, since the Pi project does not publish it.
- `perplexity` shows its macOS 15 floor.
- Labels lost their "(Homebrew cask)" and "(media utility)" tags. The category says what kind of tool it is now.

## Runtime fixes found during the review

- Hermes: the installer now comes from Nous Research's own address (`hermes-agent.nousresearch.com/install.sh`). It serves the same file as the GitHub copy.
- Two leftover ChatGPT Atlas helper lines were removed. The cask was discontinued and was never a catalog entry.

## Second pass: taps, browser tools and Poe

### Install channels

Homebrew is often a few hours (casks) to about a day (formulae) behind a tool's own release, and some formulae lag longer. So each tool now installs from whichever official channel gets new releases first, and tools with more than one official package list the others as alternates.

- `aiup channel` lists the tools with more than one channel.
- `aiup channel TOOL` shows each channel's package and latest version, with `*` on the one in use.
- `aiup channel TOOL brew|npm|uv|vendor` picks one, and `aiup channel TOOL default` goes back. Then `aiup only TOOL` moves it. The old copy is removed after the new one is in place, and settings stay.
- Choices are kept in `channels.tsv` in aiup's state folder.

Defaults after this pass:

| Default | Tools |
|---|---|
| Vendor installer | Claude Code, OpenCode, Antigravity, Warp, Cursor, Droid, Hermes |
| npm | Codex, Copilot, Pi, Qwen, Letta, codex-acp, Wrangler, Vercel, ctx7, pnpm, Defuddle, rulesync, skills, mise, Repomix, mcp-remote, mcpc, OpenSpec, ccusage, Claude Code Router, MCP Inspector, ast-grep, OpenClaw, Kimi, Backlog.md, Crush, E2B, promptfoo, Peekaboo, MCPorter, Oracle, agent-browser, Playwright CLI, Playwright MCP, Chrome DevTools MCP |
| PyPI (uv) | Mistral Vibe, Spec Kit, Rapid-MLX, gptme, mcp-proxy, Pocket TTS, Hugging Face CLI |
| Homebrew, with a uv alternate | llm, RamaLama, yt-dlp (the formulae bundle plugins or extras) |
| Homebrew, with an npm alternate | Bun |

Seventeen entries moved from a Homebrew formula to npm or PyPI by default: Kimi, OpenClaw, MCP Inspector, mise, Repomix, ccusage, Claude Code Router, OpenSpec, Backlog.md, mcp-remote, mcpc and ast-grep to npm, and the Hugging Face CLI, gptme, mcp-proxy, Rapid-MLX and Pocket TTS to PyPI. On the next run aiup installs the new default, then removes the Homebrew copy aiup had recorded. `aiup channel TOOL brew` keeps a tool on Homebrew.

### OpenCode 2

OpenCode 2 and 1.x cannot share the `opencode` command, and the project says to remove package-managed copies before using the v2 installer. aiup now installs OpenCode with the v2 installer. On the first run it removes a Homebrew or npm copy, then installs. After that it runs `opencode upgrade` and falls back to the installer if that fails.

### Homebrew taps

When a tool needs a tap that is missing, aiup asks before it adds it (`brew tap`) and trusts it (`brew trust --tap`), and does neither without a yes. A tap you already added counts as your approval. A tap is allowed only when the tool's own publisher runs it. Three taps live in repositories that are not named `homebrew-*`, so aiup taps them from their GitHub address: `jundot/omlx`, `vllm-project/vllm-metal` and `ddalcu/mlx-serve`.

Two fixes came out of this. The installed check now uses the formula's short name, so a tap-qualified target such as `stacklok/tap/thv` is seen as installed. Installs and upgrades pass `--formula` when a name exists as both a formula and a cask, so `mlx-serve` the formula is not confused with `mlx-serve` the app.

### Added

| Id | Category | What | Installs from |
|---|---|---|---|
| `agent-browser` | `browsers` | [agent-browser: Vercel browser automation CLI for coding agents](https://github.com/vercel-labs/agent-browser) | npm `agent-browser` |
| `agent-deck` | `agent-tools` | [Agent Deck: one terminal UI for many coding agent sessions](https://github.com/asheshgoplani/agent-deck) | Homebrew formula `asheshgoplani/tap/agent-deck` |
| `android-cli` | `dev-utils` | [Android CLI: Google tool for Android development with agents (android)](https://developer.android.com/tools/agents/android-cli) | Homebrew cask `android-cli` |
| `apm` | `agent-tools` | [APM: Microsoft package manager for agent configuration](https://microsoft.github.io/apm/) | Homebrew formula `apm` |
| `arcbox` | `sandboxes` | [ArcBox: containers, Linux VMs and agent sandboxes (Apple silicon, macOS 15+)](https://arcbox.dev/) | Homebrew cask `arcbox` |
| `browser-use` | `browsers` | [Browser Use: lets an agent drive your own Chrome from the terminal](https://github.com/browser-use/browser-use) | uv (PyPI) `browser-use` |
| `cactus` | `local-ai` | [Cactus: on-device AI inference CLI (Apple silicon, macOS 14+)](https://cactuscompute.com) | Homebrew formula `cactus-compute/cactus/cactus` |
| `chrome-devtools-mcp` | `mcp` | [Chrome DevTools MCP: Google server that lets agents inspect and debug Chrome](https://github.com/ChromeDevTools/chrome-devtools-mcp) | npm `chrome-devtools-mcp` |
| `coderabbit` | `agent-tools` | [CodeRabbit CLI: AI code review in the terminal (account required)](https://www.coderabbit.ai/cli) | Homebrew cask `coderabbit` |
| `codexbar` | `agent-tools` | [CodexBar: menu bar view of coding agent limits and usage (macOS 14+)](https://codexbar.app/) | Homebrew cask `codexbar` |
| `cq` | `agent-tools` | [cq: shared knowledge store so agents avoid known mistakes](https://docs.mozilla.ai/cq) | Homebrew cask `mozilla-ai/tap/cq` |
| `daytona` | `sandboxes` | [Daytona CLI: manage cloud sandboxes for AI-generated code (account required)](https://www.daytona.io/docs/en/tools/cli/) | Homebrew formula `daytonaio/cli/daytona` |
| `docker-agent` | `automation` | [Docker Agent: build and run AI agents from a config file](https://docker.github.io/docker-agent/) | Homebrew formula `docker-agent` |
| `e2b` | `sandboxes` | [E2B CLI: manage cloud sandboxes and templates (account required)](https://e2b.dev/docs/cli) | npm `@e2b/cli` |
| `foundry-local` | `local-ai` | [Foundry Local: Microsoft CLI for running models locally (preview, macOS 15+)](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-local/) | Homebrew formula `microsoft/foundrylocal/foundrylocal` |
| `git-gtr` | `agent-tools` | [git-gtr: CodeRabbit git worktree runner for parallel agents (gtr)](https://github.com/coderabbitai/git-worktree-runner) | Homebrew formula `coderabbitai/tap/git-gtr` |
| `github-mcp-server` | `mcp` | [GitHub MCP Server: GitHub tools for AI clients](https://github.com/github/github-mcp-server) | Homebrew formula `github-mcp-server` |
| `llama-swap` | `local-ai` | [llama-swap: swap models behind one OpenAI-compatible endpoint](https://github.com/mostlygeek/llama-swap) | Homebrew formula `mostlygeek/llama-swap/llama-swap` |
| `lm-studio-bionic` | `local-apps` | [Bionic: LM Studio agent that works with open models (Apple silicon)](https://lmstudio.ai/bionic) | Homebrew cask `lm-studio-bionic` |
| `lume` | `sandboxes` | [Lume: macOS and Linux VMs for agents, from Cua (Apple silicon, macOS 15+)](https://cua.ai/docs/lume) | Homebrew formula `lume` |
| `mcp-publisher` | `mcp` | [MCP Publisher: publish servers to the official MCP Registry](https://github.com/modelcontextprotocol/registry) | Homebrew formula `mcp-publisher` |
| `mcp-toolbox` | `mcp` | [MCP Toolbox: Google MCP server for databases (toolbox)](https://github.com/googleapis/mcp-toolbox) | Homebrew formula `mcp-toolbox` |
| `mcpd` | `mcp` | [mcpd: Mozilla.ai tool to define and run MCP servers from one config file](https://github.com/mozilla-ai/mcpd) | Homebrew cask `mozilla-ai/tap/mcpd` |
| `mcporter` | `mcp` | [MCPorter: call MCP servers from the terminal or TypeScript](https://mcporter.sh) | npm `mcporter` |
| `mlx-serve` | `local-apps` | [MLX-Serve: local model server app with OpenAI and Anthropic APIs (macOS 26+)](https://mlxserve.com/) | Homebrew cask `ddalcu/mlx-serve/mlx-serve` |
| `mlx-serve-cli` | `local-ai` | [mlx-serve: the MLX-Serve model server without the app (macOS 26.2+)](https://mlxserve.com/) | Homebrew formula `ddalcu/mlx-serve/mlx-serve` |
| `nvidia-pair` | `local-apps` | [NVIDIA PAIR: share local inference across your computers (macOS 13+)](https://github.com/NVIDIA/Personal-AI-Router) | Homebrew cask `nvidia-pair` |
| `omlx` | `local-ai` | [oMLX: MLX inference server with batching and an SSD cache (macOS 15+, builds from source)](https://omlx.ai) | Homebrew formula `jundot/omlx/omlx` |
| `openshell` | `sandboxes` | [OpenShell: NVIDIA private runtime for autonomous agents (early release)](https://docs.nvidia.com/openshell/latest/) | Homebrew formula `openshell` |
| `oracle` | `llm-utils` | [Oracle: send prompts and files to a second model for review (API key required)](https://askoracle.sh) | npm `@steipete/oracle` |
| `peekaboo` | `agent-tools` | [Peekaboo: screenshots and UI automation for agents (macOS 15+)](https://peekaboo.sh/) | npm `@steipete/peekaboo` |
| `playwright-cli` | `browsers` | [Playwright CLI: Microsoft browser automation commands for coding agents](https://github.com/microsoft/playwright-cli) | npm `@playwright/cli` |
| `playwright-mcp` | `mcp` | [Playwright MCP: Microsoft browser control server for MCP clients](https://github.com/microsoft/playwright-mcp) | npm `@playwright/mcp` |
| `poe` | `chat` | [Poe: Quora chat app with models from many providers](https://poe.com/) | Homebrew cask `poe` |
| `promptfoo` | `llm-utils` | [promptfoo: test and red-team LLM prompts locally](https://www.promptfoo.dev/docs/) | npm `promptfoo` |
| `rtk` | `llm-utils` | [RTK: cut the tokens dev commands send to agents](https://www.rtk-ai.app) | Homebrew formula `rtk` |
| `sbx` | `sandboxes` | [Docker Sandboxes (sbx): run coding agents in isolated sandboxes (Apple silicon, macOS 14+)](https://docs.docker.com/ai/sandboxes/) | Homebrew cask `docker/tap/sbx` |
| `splash` | `local-ai` | [Splash: Inco AI local inference engine for coding agents (M3 or newer, macOS 26.4+)](https://inco.ai/blog/splash/) | Homebrew formula `incoai/tap/splash` |
| `thv` | `mcp` | [ToolHive CLI (thv): run and manage MCP servers from the terminal](https://docs.stacklok.com/toolhive/) | Homebrew formula `stacklok/tap/thv` |
| `unsloth` | `local-apps` | [Unsloth Studio: run and fine-tune models locally (beta, Apple silicon)](https://unsloth.ai/docs/new/studio) | Homebrew cask `unsloth` |
| `vllm-metal` | `local-ai` | [vLLM Metal: vLLM inference server on Apple silicon (macOS 15+, large install)](https://docs.vllm.ai/projects/vllm-metal) | Homebrew formula `vllm-project/vllm-metal/vllm-metal` |
| `worktrunk` | `agent-tools` | [Worktrunk: git worktrees for parallel agent work (wt)](https://worktrunk.dev) | Homebrew formula `worktrunk` |
| `zed-delta` | `workspaces` | [Delta: multiplayer coding with agents (Apple silicon, macOS 13+)](https://delta.dev/) | Homebrew cask `zed-delta` |

### Looked at and left out

- Browserbase, Steel and Kernel: hosted browser services that need a paid or cloud account.
- poe-code: I could not confirm it is Poe's own package.
- Lightpanda: its tap ships only nightly builds.
- Lemonade: I could not confirm its command name or app path.
- Block's Buzz cask: its app is also `Buzz.app`, which collides with the existing `buzz` entry.

aiup never installs a browser runtime itself. The browser tools above install only their own command.

## Not added

### Needed a Homebrew tap (added in the second pass)

These waited for tap approval in the first pass and were added in the second: Docker Sandboxes (`sbx`), ToolHive CLI (`thv`), Daytona, vLLM Metal, oMLX, Splash, mlx-serve, Foundry Local and llama-swap.

### Browser automation tools (added in the second pass)

agent-browser and browser-use waited because each one can download its own browser. They are in now. aiup installs only the command and never runs their browser download step (`agent-browser install`, `browser-use install`); you run that yourself if you want it.

### Deferred to a later review

- bob: I could not confirm its npm package is the official one.
- Pool: only a `curl` installer with a license agreement, which needs its own installer code.
- mistral.rs: only a `curl` installer.
- Lemonade Server: a `.pkg` that adds launchd jobs. aiup does not install background services.
- DeepSeek Harness: release candidates only so far.
- rtk: license not clear yet. Added in the second pass: the formula lists Apache-2.0.
- agent-scan: needs a Snyk token to do anything.
- Freebuff: the free, ad-funded version of Codebuff. Codebuff is in; Freebuff can follow.
- Docker Agent: an agent builder, which is a weak fit for this catalog. Added in the second pass under Automation.
- More chat clients and more media and voice apps that did not make this pass, plus audio-separator, Demucs and the Topaz apps.

### Left out

- Jules CLI and iFlow CLI: still inactive.
- Vibe Kanban: the company behind it shut down on 2026-04-10, and npm's latest release is still from April.
- Continue: its final release is out and the repository is read-only.
- Roo Code: archived on 2026-05-15 after its final release (3.54.0), and it has no CLI package.
- LiteLLM: two compromised PyPI releases on 2026-03-24, and it runs as a server.

## Watch list

- `aider`: no release since 2026-02-12. It stays active for now and gets removed if it reaches a year without one.
- `sgpt`: the last PyPI release was 1.5.1 on 2026-05-06.
- Several tools that aiup installs with their own installer or npm also ship an official Homebrew package. The second pass handled this with install channels: the faster channel stays the default and Homebrew is an alternate you can pick with `aiup channel`.
- `junie`: the npm package lags behind JetBrains' own releases.
- `amp`: the npm package was renamed to `@ampcode/cli`.
