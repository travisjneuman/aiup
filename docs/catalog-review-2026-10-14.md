# Catalog review | 2026-10-14

Status date: **2026-10-14**. Runtime version: **2026.09.29-06** (unreleased changes).

I went through what has shipped since the 2026-09-29 review: new coding agents, agent add-ons, MCP tools, sandboxes, AI browsers, dictation and meeting apps, local model servers, and image and video generators. This record lists what I added, what moved, and what I left out and why.

The catalog went from 131 to 218 entries (87 added, none removed). The current list is in [catalog.md](catalog.md).

## How each addition was checked

Every new entry passed the same checks as the earlier reviews ([catalog research](catalog-research.md)):

- It installs from an official channel aiup already handles: a core Homebrew formula or cask, an npm package, or a PyPI package through uv. I read the Homebrew metadata (`brew info --json=v2`), the formula source, `npm view` or the PyPI JSON for each one.
- It had a release in the last three months, and Homebrew does not mark it deprecated or disabled.
- The command name or app bundle aiup looks for matches what the package really installs, so detection and removal point at the right thing.
- Nothing needs a new Homebrew tap, a `curl | sh` installer aiup has not reviewed, or a background service.

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
| `gptme` | [gptme: open-source AI assistant in your terminal](https://gptme.org/docs/) | Homebrew formula `gptme` |
| `code-puppy` | [Code Puppy: open-source terminal coding agent](https://github.com/mpfaffenberger/code_puppy) | uv (PyPI) `code-puppy` |
| `command-code` | [Command Code: terminal coding agent (commandcode)](https://commandcode.ai/docs) | npm `command-code` |
| `nanocoder` | [Nanocoder: local-first terminal coding agent](https://github.com/Nano-Collective/nanocoder) | npm `@nanocollective/nanocoder` |
| `codebuff` | [Codebuff: terminal coding agent](https://www.codebuff.com/) | npm `codebuff` |

### Agent helpers (new)

| Id | What | Installs from |
|---|---|---|
| `ccusage` | [ccusage: token and cost reports from local agent logs](https://github.com/ccusage/ccusage) | Homebrew formula `ccusage` |
| `claude-squad` | [Claude Squad: run several agents in tmux and git worktrees (cs)](https://smtg-ai.github.io/claude-squad/) | Homebrew formula `claude-squad` |
| `claude-code-router` | [Claude Code Router: send Claude Code requests to other model providers (ccr)](https://github.com/musistudio/claude-code-router) | Homebrew formula `claude-code-router` |
| `skills` | [skills: Vercel CLI that adds agent skills to a project](https://github.com/vercel-labs/skills) | npm `skills` |
| `specify` | [Spec Kit (specify): GitHub toolkit for spec-driven development](https://github.com/github/spec-kit) | uv (PyPI) `specify-cli` |
| `openspec` | [OpenSpec: spec-driven development for coding agents](https://openspec.dev/) | Homebrew formula `openspec` |
| `beads` | [Beads: issue tracker that coding agents use as memory (bd)](https://github.com/gastownhall/beads) | Homebrew formula `beads` |
| `backlog-md` | [Backlog.md: Markdown task board inside a Git repository (backlog)](https://github.com/MrLesk/Backlog.md) | Homebrew formula `backlog-md` |
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
| `mcp-proxy` | [mcp-proxy: bridge stdio and HTTP MCP transports](https://github.com/sparfenyuk/mcp-proxy) | Homebrew formula `mcp-proxy` |
| `mcp-remote` | [mcp-remote: connect local MCP clients to remote servers that use OAuth](https://github.com/geelen/mcp-remote) | Homebrew formula `mcp-remote` |
| `mcpc` | [mcpc: Apify command-line MCP client](https://github.com/apify/mcpc) | Homebrew formula `mcpc` |
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
| `rapid-mlx` | [Rapid-MLX: local MLX inference server with an OpenAI-compatible API (macOS 14+)](https://github.com/raullenchai/Rapid-MLX) | Homebrew formula `rapid-mlx` |
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
| `pocket-tts` | [Pocket TTS: Kyutai text-to-speech that runs on the CPU](https://github.com/kyutai-labs/pocket-tts) | Homebrew formula `pocket-tts` |
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
| `ast-grep` | [ast-grep: structural code search and rewrite (sg)](https://ast-grep.github.io/) | Homebrew formula `ast-grep` |
| `tmux` | [tmux: terminal multiplexer](https://github.com/tmux/tmux) | Homebrew formula `tmux` |
| `supabase` | [Supabase CLI: local Postgres development and deploys](https://supabase.com/docs/reference/cli/about) | Homebrew formula `supabase` |
| `vercel` | [Vercel CLI: deploy and manage Vercel projects](https://vercel.com/docs/cli) | npm `vercel` |

`kitty` and `tmux` were on the Homebrew recommended list. They are catalog entries now, so they left that list.

## Label and lifecycle changes

- `gemini` is now **sunset**. Homebrew deprecated the `gemini-cli` formula on 2026-06-18 as unsupported and plans to disable it on 2026-12-18; Google moved personal accounts to Antigravity CLI. The npm package still works for enterprise and API key accounts, so aiup keeps updating installed copies and asks before a new install from the list.
- `cursor` now says `agent`, the command Cursor installs today, and keeps `cursor-agent` as the older name.
- `amp` and `amp-app` no longer name Sourcegraph.
- `warp` drops the old Oz TUI name.
- `opencode` says which line the official installer gives you (1.x).
- `chatgpt` notes that the desktop app includes Codex.
- `pi-acp` is marked community, since the Pi project does not publish it.
- `perplexity` shows its macOS 15 floor.
- Labels lost their "(Homebrew cask)" and "(media utility)" tags. The category says what kind of tool it is now.

## Runtime fixes found during the review

- Hermes: the installer now comes from Nous Research's own address (`hermes-agent.nousresearch.com/install.sh`). It serves the same file as the GitHub copy.
- Two leftover ChatGPT Atlas helper lines were removed. The cask was discontinued and was never a catalog entry.

## Not added

### Needs a new Homebrew tap

aiup adds a tap only when I approve it, so these wait: Docker Sandboxes (`sbx`), ToolHive CLI (`thv`), Daytona, vllm-metal, oMLX, Splash, mlx-serve, Foundry Local and llama-swap.

### Browser automation runtimes

agent-browser and browser-use install their own browser automation runtime. I am holding both until I decide whether aiup should install those.

### Deferred to a later review

- bob: I could not confirm its npm package is the official one.
- Pool: only a `curl` installer with a license agreement, which needs its own installer code.
- mistral.rs: only a `curl` installer.
- Lemonade Server: a `.pkg` that adds launchd jobs. aiup does not install background services.
- DeepSeek Harness: release candidates only so far.
- rtk: license not clear yet.
- agent-scan: needs a Snyk token to do anything.
- Freebuff: the free, ad-funded version of Codebuff. Codebuff is in; Freebuff can follow.
- Docker Agent: an agent builder, which is a weak fit for this catalog.
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
- Several tools that aiup installs with their own installer now also ship an official Homebrew package: `grok`, `antigravity`, `cursor`, `copilot`, `warp`, `droid`, `codex`, `pi`, `letta`, `vibe`, `qwen`, `goose` and `codex-acp`. Switching a tool's channel changes how existing installs update, so that is a separate change.
- `junie`: the npm package lags behind JetBrains' own releases.
- `amp`: the npm package was renamed to `@ampcode/cli`.
