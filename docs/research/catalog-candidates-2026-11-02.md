# Catalog candidates (2026-11-02)

This is a research pass, not a catalog change. I looked for maintained, notable tools that fit the [catalog policy](../catalog-research.md) and are missing from `macos/catalog/manifest.tsv` (259 entries in 20 categories at the time of writing). Linux-only and Windows-only tools now qualify, so each row lists the best channel per platform. I also checked existing entries for archived repos, renames and stale releases.

How I checked: GitHub repository and release data, Homebrew's formula and cask API, npm and PyPI metadata, Arch `pacman -Si`, the AUR RPC, the Flathub API, and read-only `winget search` on a Windows machine. Dates are the newest release I saw, checked on 2026-11-02 and 2026-11-03. "Not checked" means I did not confirm that channel. Nothing was installed.

Rules I applied: a release within about six months; an official repo or site; publisher-run Homebrew taps only; no background services; no unreviewed curl installers; and no Playwright, Puppeteer, Selenium or anything built on them (rule 9 and my standing browser rules).

Name collisions to watch when someone adds these:

- Homebrew cask `orca` is plotly/orca, not Stably's Orca.
- Homebrew cask `bifrost` is a different app from Maxim's Bifrost gateway.
- Homebrew formula `cortex` is Prometheus storage.
- AUR `goose-bin` and winget `Pressly.Goose` are the pressly/goose database tool.
- AUR `nono` is a different project.
- npm `paseo` and `toad-cli` are unrelated. Use `@getpaseo/cli`, and PyPI `batrachian-toad` for Toad.
- PyPI `exo`, `nexa` and `vane` are unrelated projects.
- winget `Chia-Lung.Kaku` looks like a different app from tw93's Kaku.
- The catalog id `vibe` is already Mistral Vibe, so the Vibe transcription app needs another id.

## Coding agents (`coding-agents`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `oh-my-pi` | oh-my-pi | Terminal coding agent based on pi, with IDE features built in | coding-agents | mac, linux, win | npm `@oh-my-pi/pi-coding-agent` (all) | https://github.com/can1357/oh-my-pi/releases | v18.16.0, 2026-11-02 (npm same day) | add: 37.6k stars, ships several times a week |
| `freebuff` | Freebuff | Free coding agent from the Codebuff team; the Codebuff repo was renamed to it | coding-agents | mac, linux, win | npm `freebuff` (all) | https://github.com/CodebuffAI/freebuff | npm 0.2.35, 2026-10-29 | add as the successor to `codebuff` (see retire section). It was deferred on 2026-10-14 while the move was underway; the rename is now done |
| `mini-swe-agent` | mini-swe-agent | Small coding agent from the SWE-agent team that fixes issues from the command line | coding-agents | mac, linux, win | uv `mini-swe-agent` (all) | https://github.com/SWE-agent/mini-swe-agent/releases | v2.4.6, 2026-07-23 | add |
| `bob` | IBM Bob Shell | IBM's coding agent for the terminal | coding-agents | mac, linux, win | npm `@ibm/bob` (all) | https://www.npmjs.com/package/@ibm/bob | 2.0.9, 2026-10-23 | maybe: the earlier deferral may now be resolved; confirm account and license terms on IBM's docs |
| `mimo-code` | MiMo Code | Xiaomi's terminal coding agent | coding-agents | mac, linux, win | GitHub releases; npm `@xiaomi-mimo/cli` is only `0.3.0-alpha.0` from 2026-05-11 | https://github.com/XiaomiMiMo/MiMo-Code/releases | v0.1.16, 2026-10-26 | maybe: 13.7k stars, but the npm channel trails GitHub by months |
| `every-code` | Every Code | Community fork of Codex CLI with extra validation and automation | coding-agents | mac, linux, win | npm `@just-every/code` (all) | https://github.com/just-every/code | 0.6.196, 2026-09-29 | maybe: overlaps with `codex` |
| `kode` | Kode CLI | General terminal agent for coding and computer tasks | coding-agents | mac, linux, win | npm `@shareai-lab/kode` (all) | https://github.com/shareAI-lab/Kode-CLI | npm 2.2.1, 2026-06-05 | maybe: repo active, releases have slowed |
| `ante` | Ante | Self-contained agent harness for the shell | coding-agents | mac, linux | GitHub releases (package channel not checked) | https://github.com/AntigmaLabs/ante/releases | v0.3.2, 2026-11-01 | maybe: 2k stars, channel not reviewed |
| `claurst` | Claurst | Rust coding agent for the terminal | coding-agents | mac, linux, win | GitHub releases (package channel not checked) | https://github.com/Kuberwastaken/claurst/releases | v0.2.1, 2026-10-26 | maybe: 10k stars; review its license and code origin first |
| `opensquilla` | OpenSquilla | General AI agent tuned to spend fewer tokens | automation | not checked | GitHub releases | https://github.com/TokenRhythm/opensquilla/releases | v0.5.7, 2026-10-23 | maybe: 7.1k stars, purpose and channels need a closer look |
| `cecli` | cecli | Community fork of aider (aider-ce was renamed to this) | coding-agents | mac, linux, win | uv `cecli-dev` (all) | https://pypi.org/project/cecli-dev/ | 1.11.0, 2026-11-01 | maybe: possible home for aider users if aider stays quiet |
| `agentcore` | AWS AgentCore CLI | Build and deploy agents on Amazon Bedrock AgentCore | automation | mac, linux, win | npm `@aws/agentcore` (all) | https://www.npmjs.com/package/@aws/agentcore | 1.0.1, 2026-10-27 | maybe: needs an AWS account and is billed by use |
| `qodo` | Qodo Command | Qodo's agent CLI | coding-agents | mac, linux, win | npm `@qodo/command` | https://github.com/qodo-ai/command | npm 0.36.0, 2026-01-11 | skip: no npm release in nearly ten months |
| `claw-code` | claw-code | Rust project with 195k stars | coding-agents | not checked | GitHub releases | https://github.com/ultraworkers/claw-code | v0.1.10, 2026-11-02 | skip: its own description calls it a museum exhibit; unclear as a tool |
| `dexto` | Dexto | Toolkit and CLI for building agents | automation | not checked | npm | https://github.com/truffle-ai/dexto | 2026-11-02 | skip: small, more framework than tool |
| | Plandex | Long-task coding agent | | | | https://github.com/plandex-ai/plandex | cli/v2.2.1, 2025-07-16 | skip: no release in over a year |
| | SWE-agent | Issue-fixing agent | | | | https://github.com/SWE-agent/SWE-agent | v1.1.0, 2025-05-22 | skip: stale; mini-swe-agent is the active one |
| | Trae Agent | ByteDance's research agent | | | | https://github.com/bytedance/trae-agent | no releases; last push 2026-02-05 | skip |
| | Neovate Code | Coding agent | | | | https://github.com/neovateai/neovate-code | 0.28.5, 2026-02-26 | skip: stale |
| | Groq Code CLI | Coding CLI for Groq models | | | | https://github.com/build-with-groq/groq-code-cli | no releases; last push 2025-12-19 | skip |
| | RA.Aid | Coding agent | | | | https://github.com/ai-christianson/RA.Aid | v0.30.2, 2025-05-07 | skip: stale |
| | OpenHands CLI | OpenHands terminal client | | | | https://github.com/OpenHands/OpenHands-CLI | 1.16.0, 2026-05-08 | skip: still marked unmaintained (removed 2026-09-29) |

Channel note: Factory's `droid` also ships as npm `@factory/cli` (1.2.0), which could be an alternate channel for the existing entry.

## Agent orchestrators and multi-agent workspaces (`orchestrators`, new; or `workspaces` and `agent-tools`)

These run several coding agents side by side, usually one worktree each. Today they are split between `workspaces` (desktop apps) and `agent-tools` (claude-squad, agent-deck, git-gtr, worktrunk). See the cleanup section for the proposed category.

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `orca` | Orca | Desktop app for running a fleet of coding agents side by side | orchestrators (or workspaces) | mac, linux, win | win: winget `StablyAI.Orca` (1.4.246); mac: GitHub DMG (no publisher tap found; cask `orca` is a different app); linux: release assets (not checked) | https://github.com/stablyai/orca/releases | v1.4.247, 2026-11-03 | add: 113.8k stars, daily releases; mac channel needs a decision |
| `herdr` | herdr | Terminal runtime that hosts and switches between many coding agents | orchestrators (or agent-tools) | mac, linux, win | mac/linux: formula `herdr` (0.9.5); linux: AUR `herdr`; win: winget `Herdr.Herdr.Preview` only | https://github.com/herdrdev/herdr/releases | v0.9.5, 2026-10-14 | add: 47.7k stars |
| `multica` | Multica | Self-hostable app where people and agents share one task board | orchestrators (or workspaces) | mac, linux, win | win: winget `Multica.MulticaDesktop` and `Multica.MulticaCLI` (0.7.2); linux: AUR `multica-bin`; mac: not checked | https://github.com/multica-ai/multica/releases | v0.7.2, 2026-10-30 | add: 54.7k stars |
| `paseo` | Paseo | Run and watch several coding agents from desktop and phone | orchestrators (or workspaces) | mac, linux, win | mac: cask `paseo` (0.14.0); win: winget `Paseo.Paseo`; linux: AUR `paseo-bin`; CLI: npm `@getpaseo/cli` | https://github.com/getpaseo/paseo/releases | v0.14.0, 2026-10-29; npm CLI 0.15.0, 2026-11-03 | add: 22.9k stars |
| `openchamber` | OpenChamber | Desktop and web app for the OpenCode agent | workspaces | mac, linux, win | mac: cask `openchamber` (2.6.0); web: npm `@openchamber/web`; win/linux: not checked | https://github.com/openchamber/openchamber/releases | v2.6.0, 2026-11-02 | add: pairs with `opencode` |
| `happy` | Happy | Phone and web client for Claude Code, Codex and Grok that uses your existing subscriptions | orchestrators (or agent-tools) | mac, linux, win | npm `happy` (all); `happy-coder` is the old package name | https://github.com/slopus/happy | npm 1.2.6, 2026-10-27 | add: 24.5k stars |
| `ruflo` | Ruflo (formerly Claude Flow) | Multi-agent swarm harness for Claude Code and other agents | orchestrators (or agent-tools) | mac, linux, win | npm `ruflo` (all) | https://github.com/ruvnet/ruflo/releases | v3.71.0, 2026-11-01 | add: 80.7k stars |
| `aionui` | AionUi | Desktop app that runs Claude Code, Codex, OpenCode, Hermes and other agents in one place | workspaces | mac, linux, win | mac: cask `aionui` (2.2.2); win: winget `iOfficeAI.AionUi`; linux: AUR `aionui-bin` | https://github.com/iOfficeAI/AionUi/releases | v2.2.2, 2026-09-09 | add: 34k stars. winget also lists a community fork (`Lumysia.AionUiCommunity`); use the official id |
| `openwork` | OpenWork | Open-source desktop cowork app built on OpenCode | workspaces | mac, win | mac: cask `openwork` (0.18.63); win: winget `DifferentAI.OpenWork` | https://github.com/different-ai/openwork/releases | v0.18.63, 2026-10-26 | add: 24.4k stars |
| `goose-app` | Goose desktop | Desktop app for the Goose agent | workspaces | mac, linux, win | mac: cask `block-goose` (1.57.0); win/linux: release assets (not checked) | https://github.com/aaif-goose/goose/releases | v1.57.0, 2026-10-28 | add: the CLI is already in the catalog as `goose` |
| `agent-of-empires` | Agent of Empires | TUI and web app to manage many Claude Code and OpenCode sessions | orchestrators (or agent-tools) | mac, linux | formula `aoe` (1.21.0) | https://github.com/agent-of-empires/agent-of-empires/releases | v1.21.0, 2026-10-21 | add |
| `supacode` | Supacode | macOS command center for worktree coding agents | workspaces | mac | cask `supacode` (0.11.6) | https://github.com/supabitapp/supacode/releases | v0.11.6, 2026-10-25 | add |
| `cao` | CLI Agent Orchestrator | AWS Labs tool that coordinates Claude Code, Kiro, Codex and others in tmux | orchestrators (or agent-tools) | mac, linux | uv `cli-agent-orchestrator` (2.5.4) | https://github.com/awslabs/cli-agent-orchestrator/releases | v2.5.3 on GitHub, 2026-10-08 | add |
| `gastown` | Gas Town | Multi-agent workspace manager | orchestrators (or agent-tools) | mac, linux | formula `gastown` (1.1.0); AUR `gastown` (1.2.1) | https://github.com/gastownhall/gastown/releases | v1.2.1, 2026-06-06 | add: 18.7k stars; repo pushed 2026-10-28 |
| `agent-orchestrator` | Agent Orchestrator | Plan, run and supervise fleets of agents from task to merged PR | orchestrators | mac, linux, win | desktop release assets (not checked) | https://github.com/OrchestratorInc/agent-orchestrator/releases | v0.14.8, 2026-10-30 | maybe: 14k stars, formerly under ComposioHQ; channels not reviewed |
| `xum` | xum (formerly mux) | Coder's desktop app for parallel agent work in isolated workspaces | workspaces | mac, linux, win | release assets (not checked) | https://github.com/coder/xum/releases | v0.32.1, 2026-10-27 | maybe |
| `jean` | Jean | Desktop dev environment for AI agents | workspaces | not checked | release assets | https://github.com/coollabsio/jean/releases | v1.0.13, 2026-10-28 | maybe |
| `parallel-code` | Parallel Code | Run Claude Code, Codex and Gemini side by side, one worktree each | orchestrators | not checked | not checked | https://github.com/johannesjo/parallel-code/releases | v5.1.0, 2026-10-29 | maybe |
| `agent-sessions` | Agent Sessions | macOS app to browse, search and resume coding agent sessions | agent-tools | mac | not checked | https://github.com/jazzyalex/agent-sessions/releases | v6.2, 2026-10-27 | maybe |
| `traycer` | Traycer | Desktop app for planning and handing work to coding agents | workspaces | not checked | release assets | https://github.com/traycerai/traycer/releases | desktop-v1.5.2, 2026-11-01 | maybe: account needed |
| `codenomad` | CodeNomad | Desktop command center for OpenCode | workspaces | not checked | release assets | https://github.com/NeuralNomadsAI/CodeNomad/releases | v1.0.1, 2026-10-29 | maybe |
| `ntm` | Named Tmux Manager | Spawn, tile and coordinate coding agents in tmux | orchestrators | mac, linux | not checked | https://github.com/Dicklesworthstone/ntm/releases | v1.38.0, 2026-10-31 | maybe: small (465 stars) |
| `hcom` | hcom | Lets agents message, watch and start each other across terminals | orchestrators | mac, linux | not checked | https://github.com/aannoo/hcom/releases | v0.7.31, 2026-10-21 | maybe |
| `squad` | Squad | Sets up AI agent teams for a project | agent-tools | not checked | not checked | https://github.com/bradygaster/squad/releases | v1.1.0, 2026-10-20 | maybe |
| `toad` | Toad | One terminal UI for many agents over ACP | adapters | mac, linux | uv `batrachian-toad` | https://github.com/batrachianai/toad/releases | v0.6.20, 2026-05-26 | maybe: near the six-month line |
| `ralph-orchestrator` | Ralph Orchestrator | Runs an agent in a loop until a task is done | orchestrators | not checked | not checked | https://github.com/mikeyobrien/ralph-orchestrator/releases | v2.10.1, 2026-06-23 | maybe |
| `ralph-tui` | Ralph TUI | Terminal UI for loop-style agent runs | orchestrators | mac, linux, win | npm `ralph-tui` | https://github.com/subsy/ralph-tui | 0.12.0, 2026-05-13 | maybe: near the six-month line |
| `dmux` | dmux | Multiplexer for git worktrees and coding agents | orchestrators | mac, linux | not checked | https://github.com/standardagents/dmux/releases | v5.11.1, 2026-08-16 | maybe |
| `gh-aw` | GitHub Agentic Workflows | `gh` extension that writes agent workflows for GitHub Actions | agent-tools | mac, linux, win | `gh extension install github/gh-aw` | https://github.com/github/gh-aw/releases | v1.0.1, 2026-10-27 | maybe: the workflows it creates use hosted Actions minutes |
| `claudecodeui` | CloudCLI (Claude Code UI) | Web and phone UI for Claude Code, OpenCode, Cursor CLI and Codex | workspaces | mac, linux, win | not checked | https://github.com/siteboon/claudecodeui/releases | v1.37.7, 2026-10-31 | maybe: runs a local web server while in use |
| `berd` | Berd | Block's desktop app for getting work done with any model | workspaces | not checked | release assets | https://github.com/block/berd/releases | v0.6.4, 2026-09-10 | maybe |
| `symphony` | Symphony | OpenAI's tool that turns project work into isolated agent runs | orchestrators | not checked | not checked | https://github.com/openai/symphony/releases | v0.0.3, 2026-09-15 | maybe: early and Codex-only |
| | opcode | Claude Code desktop GUI | | | | https://github.com/winfunc/opcode | v0.2.0, 2025-08-31 | skip: stale |
| | Crystal | Worktree agent app | | | | https://github.com/stravu/crystal | v0.3.5, 2026-02-26 | skip: became Nimbalyst, already in the catalog |
| | Automaker | Agent studio | | | | https://github.com/AutoMaker-Org/automaker | v1.0.0, 2026-03-15 | skip: quiet since May |
| | ClawTeam | Agent teams | | | | https://github.com/HKUDS/ClawTeam | v0.2.0, 2026-03-23 | skip: stale |
| | HumanLayer | Agent approvals | | | | https://github.com/humanlayer/humanlayer | pro-0.20.0, 2025-12-23 | skip: no release in over ten months |
| | Vibe Kanban | Agent task board | | | | https://github.com/BloopAI/vibe-kanban | April 2026 | skip: inactive (same as 2026-10-14) |

## MCP tools and servers (`mcp`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `mcpjam` | MCPJam Inspector | Local web UI to test, debug and evaluate MCP servers and MCP apps | mcp | mac, linux, win | npm `@mcpjam/inspector` (all) | https://github.com/MCPJam/inspector/releases | v3.18.0, 2026-10-28 | add |
| `fastmcp` | FastMCP | Python framework and CLI to build, run and inspect MCP servers | mcp | mac, linux, win | uv `fastmcp` (4.1.6); formula `fastmcp` (4.1.4, trails) | https://github.com/PrefectHQ/fastmcp/releases | v4.1.6, 2026-11-03 | add: 28k stars |
| `serena` | Serena | MCP server that gives agents symbol-level code search and editing through language servers | mcp | mac, linux, win | uv `serena-agent` (all) | https://github.com/oraios/serena/releases | v2.1.0, 2026-10-19 | add: 31k stars |
| `desktop-commander` | Desktop Commander | MCP server that lets an agent run terminal commands and edit files | mcp | mac, linux, win | npm `@wonderwhy-er/desktop-commander` (all) | https://github.com/wonderwhy-er/DesktopCommanderMCP/releases | v0.3.1, 2026-10-22 | add: 10.2k stars |
| `windows-mcp` | Windows-MCP | MCP server that controls Windows apps and the desktop | mcp | win | uv `windows-mcp` | https://github.com/CursorTouch/Windows-MCP/releases | v0.8.8, 2026-10-10 | add (Windows only) |
| `terraform-mcp` | Terraform MCP Server | HashiCorp's MCP server for Terraform and the registry | mcp | mac, linux, win | formula `terraform-mcp-server` (1.4.1); release binaries | https://github.com/hashicorp/terraform-mcp-server/releases | v1.4.1, 2026-10-23 | add |
| `mcp-grafana` | Grafana MCP | Grafana's MCP server for dashboards, metrics and logs | mcp | mac, linux, win | formula `mcp-grafana` (2.2.0); release binaries | https://github.com/grafana/mcp-grafana/releases | v2.2.0, 2026-11-02 | add |
| `kubernetes-mcp` | Kubernetes MCP Server | MCP server for Kubernetes and OpenShift clusters | mcp | mac, linux, win | npm `kubernetes-mcp-server` (all); formula of the same name | https://github.com/containers/kubernetes-mcp-server/releases | v0.1.1, 2026-10-29 | add |
| `mcp-scanner` | Cisco MCP Scanner | Scans MCP servers and tools for risky behavior | mcp | mac, linux, win | uv `cisco-ai-mcp-scanner` | https://github.com/cisco-ai-defense/mcp-scanner/releases | 4.8.7, 2026-10-20 | maybe: check which scan modes need an API key |
| `docker-mcp` | Docker MCP Gateway | `docker mcp` plugin that runs MCP servers in containers behind one gateway | mcp | mac, linux, win | ships with Docker Desktop; standalone plugin from releases | https://github.com/docker/mcp-gateway | v0.44.3, 2026-10-26 | maybe: tied to Docker Desktop |
| `1mcp` | 1MCP agent | Combines many MCP servers into one endpoint | mcp | mac, linux, win | npm `@1mcp/agent` (all) | https://github.com/1mcp-app/agent/releases | v0.39.8, 2026-11-01 | maybe |
| `mongodb-mcp` | MongoDB MCP Server | MongoDB's official MCP server | mcp | mac, linux, win | npm `mongodb-mcp-server` | https://github.com/mongodb-js/mongodb-mcp-server/releases | npm 3.2.2, 2026-10-29 | maybe: only useful with MongoDB |
| `azure-mcp` | Azure MCP Server | Microsoft's MCP server for Azure | mcp | mac, linux, win | npm `@azure/mcp` (4.0.0-beta.4) | https://github.com/microsoft/mcp/releases | 2026-11-02 | maybe: current line is beta |
| `supabase-mcp` | Supabase MCP | Supabase's MCP server | mcp | mac, linux, win | npm `@supabase/mcp-server-supabase` | https://github.com/supabase/mcp/releases | v0.15.0, 2026-10-29 | maybe: the Supabase CLI is already in the catalog |
| `mcp-reference-servers` | MCP reference servers | Filesystem, git, fetch and memory servers from the MCP project | mcp | mac, linux, win | npm `@modelcontextprotocol/server-*` (for example `server-filesystem` 2.1.0, 2026-10-28) | https://github.com/modelcontextprotocol/servers/releases | v2.2.0, 2026-10-28 | maybe: several packages, so one entry is awkward |
| `aws-mcp` | AWS MCP servers | AWS Labs' MCP servers | mcp | mac, linux, win | uvx per server | https://github.com/awslabs/mcp/releases | 2026-10-30 | maybe: many separate servers, no single package |
| `firecrawl` | Firecrawl CLI | Web scraping CLI and MCP server | mcp | mac, linux, win | npm `firecrawl-cli` (1.26.24) | https://github.com/firecrawl/firecrawl-mcp-server | MCP repo release v3.2.1, 2025-09-26; CLI 1.26.24 on npm | maybe: needs an account and API key |
| `contextforge` | IBM ContextForge | Gateway and registry in front of MCP, A2A and REST APIs | mcp | linux, mac | server install (not checked) | https://github.com/IBM/mcp-context-forge/releases | v1.1.0, 2026-10-20 | maybe: runs as a service |
| `mcpjungle` | MCPJungle | Self-hosted registry and gateway for MCP servers | mcp | mac, linux | not checked | https://github.com/mcpjungle/MCPJungle/releases | 0.4.7, 2026-10-30 | maybe: runs as a service |
| `agentgateway` | agentgateway | Proxy for agents and MCP servers | mcp | linux, mac | release binaries | https://github.com/agentgateway/agentgateway/releases | v1.7.0, 2026-10-27 | maybe: runs as a service |
| `smithery` | Smithery CLI | Install and run servers from the Smithery registry | mcp | mac, linux, win | npm `@smithery/cli` (4.11.1, April) | https://github.com/arcadeai-labs/smithery-cli | v1.2.0 on GitHub, 2026-05-31 | maybe: repo moved; npm and GitHub versions disagree |
| | Snyk Agent Scan (formerly mcp-scan) | MCP and agent config scanner | | | uv `snyk-agent-scan` | https://github.com/snyk/agent-scan/releases | v0.6.10, 2026-10-30 | skip: still needs a Snyk token (same as 2026-10-14) |
| | Context7 MCP | Docs lookup server | | | npm `@upstash/context7-mcp` | | 4.4.4 | skip: covered by `ctx7` |
| | markitdown-mcp | MCP wrapper for MarkItDown | | | uv | | 0.0.1a8 | skip: alpha; `markitdown` is already in the catalog |
| | mcp-use | Framework for building MCP apps | | | | https://github.com/mcp-use/mcp-use | 2026-10-29 | skip: library |
| | Obot | AI governance platform | | | | https://github.com/obot-platform/obot | v0.27.0, 2026-10-20 | skip: hosted platform |
| | MCP Router | Desktop MCP manager | | | | https://github.com/mcp-router/mcp-router | archived | skip |
| | mcphost | MCP host CLI | | | | https://github.com/mark3labs/mcphost | archived | skip |
| | IBM mcp-cli | MCP CLI | | | | https://github.com/IBM/mcp-cli | archived | skip |
| | MetaMCP | MCP aggregator | | | | https://github.com/metatool-ai/metamcp | v2.4.22, 2025-12-19 | skip: stale |
| | mcptools | MCP CLI | | | | https://github.com/f/mcptools | v0.7.1, 2025-05-05 | skip: stale |

## Local models (`local-ai` and `local-apps`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `koboldcpp` | KoboldCpp | Single-file llama.cpp runner with its own web UI | local-ai | mac, linux, win | linux: AUR `koboldcpp`; mac/win: release binaries (no winget package found) | https://github.com/LostRuins/koboldcpp/releases | v1.124.2, 2026-10-31 | add: Linux through the AUR; mac and Windows need a reviewed binary download |
| `llamafile` | llamafile | Runs a model from one executable file | local-ai | mac, linux, win | win: winget `Mozilla.llamafile` (0.10.6); linux: AUR `llamafile`; mac: release binary | https://github.com/mozilla-ai/llamafile/releases | 0.10.6, 2026-09-15 | add |
| `lemonade` | Lemonade Server | Local model server for AMD GPUs and NPUs, also runs on other hardware | local-ai | win, linux, mac | win: winget `AMD.LemonadeServer` (2026.44.1); mac: cask `lemonade-server`; linux: release packages (not checked) | https://github.com/lemonade-sdk/lemonade/releases | v2026.44.1, 2026-10-28 | add for Windows and Linux; keep mac deferred (the pkg sets up a launchd service). winget `Lemonade.Lemonade` is a different app |
| `alpaca` | Alpaca | GNOME app to chat with local Ollama models and online models | local-apps | linux | flatpak `com.jeffser.Alpaca` | https://github.com/Jeffser/Alpaca/releases | 9.2.5, 2026-08-03 | add (Linux) |
| `newelle` | Newelle | GNOME assistant app for local and cloud models | local-apps | linux | flatpak `io.github.qwersyk.Newelle` (1.6.0) | https://github.com/qwersyk/Newelle/releases | 1.6.1 on GitHub, 2026-11-02 | add (Linux) |
| `moose` | Moose | GNOME app for chatting with Ollama models | local-apps | linux | flatpak `io.github.moooossee.Moose` | https://github.com/moooossee/moose | 0.7.5 on Flathub, 2026-10-29 | maybe: new and small |
| `vllm` | vLLM | High-throughput model server for NVIDIA and AMD GPUs | local-ai | linux | uv `vllm` (0.33.0) | https://github.com/vllm-project/vllm/releases | v0.33.0rc3, 2026-11-02 | maybe: Linux GPU machines only, large install; `vllm-metal` already covers Apple silicon |
| `sglang` | SGLang | Fast model serving framework | local-ai | linux | uv `sglang` (0.5.23) | https://github.com/sgl-project/sglang/releases | v0.5.23, 2026-11-02 | maybe: Linux GPU only |
| `docker-model` | Docker Model Runner | `docker model` plugin that pulls and serves models | local-ai | mac, linux, win | ships with Docker Desktop; Linux plugin package (not checked) | https://github.com/docker/model-runner/releases | v1.2.9, 2026-10-22 | maybe: tied to Docker |
| `geniex` | GenieX (formerly Nexa SDK) | Qualcomm's on-device model runner for NPUs, GPUs and CPUs | local-ai | not checked | not checked | https://github.com/qualcomm/GenieX/releases | v0.10.0, 2026-10-28 | maybe |
| `exo` | exo | Splits one model across several of your machines | local-ai | mac, linux | cask `exo` (1.0.71) | https://github.com/exo-explore/exo/releases | v1.0.71, 2026-04-23 | maybe: repo pushed 2026-11-03, but the last release is six months old |
| `harbor` | Harbor | One command starts a local LLM stack in containers | local-ai | mac, linux | GitHub releases; PyPI `llm-harbor` trails (0.3.34, January) | https://github.com/av/harbor/releases | v0.5.19, 2026-10-31 | maybe: needs Docker |
| `textgen` | textgen (formerly text-generation-webui) | Web UI for local models | local-apps | mac, linux, win | script or portable builds | https://github.com/oobabooga/textgen/releases | v4.9, 2026-05-20 | maybe: no package manager channel |
| `ai-playground` | Intel AI Playground | Windows starter app for image generation and chat on Intel Arc | local-apps | win | installer from releases (not on winget) | https://github.com/intel/AI-Playground/releases | v3.3.0-beta-rc2, 2026-10-30 | maybe: Intel hardware only, beta |
| `gaia` | AMD GAIA | Windows app for local agents on Ryzen AI PCs | local-apps | win | installer from releases | https://github.com/amd/gaia/releases | v0.25.3, 2026-10-30 | maybe: AMD hardware only |
| | mistral.rs | Rust model runner | | | | https://github.com/EricLBuehler/mistral.rs/releases | v0.9.5, 2026-10-19 | skip: still a curl installer only (same as 2026-10-14) |
| | TabbyML | Self-hosted code completion server | | | winget `TabbyML.Tabby` | https://github.com/TabbyML/tabby/releases | v0.32.0, 2026-01-25 | skip: no release in over nine months |
| | Khoj | Personal AI app | | | | https://github.com/khoj-ai/khoj | 2.0.0-beta.28, 2026-03-26 | skip: beta, PyPI stale |

New platform channels for existing entries: `ollama` is in Arch `extra` as `ollama`, `ollama-cuda` and `ollama-rocm` (0.40.7) and on winget as `Ollama.Ollama` (0.40.13). `lm-studio` is `ElementLabs.LMStudio` and `jan` is `Jan.Jan` on winget.

## Chat apps (`chat`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `deepchat` | DeepChat | Desktop chat app for cloud and local models, with MCP support | chat | mac, linux, win | mac: cask `deepchat` (1.1.3); win: winget `ThinkInAIXYZ.DeepChat`; linux: release assets (not checked) | https://github.com/ThinkInAIXYZ/deepchat/releases | v1.1.3, 2026-10-09 | add |
| `witsy` | Witsy | Desktop AI assistant for many providers | chat | mac, linux, win | mac: cask `witsy` (3.5.2); linux: AUR `witsy-bin` | https://github.com/Kochava-Studios/witsy | cask 3.5.2; AUR updated in April | maybe: the repo moved; confirm release dates at the new home |
| `5ire` | 5ire | Desktop chat app with MCP support | chat | mac, linux, win | cask `5ire` | https://github.com/nanbingxyz/5ire/releases | v0.15.4, 2026-03-18 | maybe: past the six-month line; watch |
| `raycast` | Raycast | Launcher with built-in AI chat | chat | mac, win (beta) | mac: cask `raycast`; win: not on winget | https://www.raycast.com | not checked | maybe: the AI features are part of a paid plan |
| | LibreChat | Self-hosted chat server | | | | https://github.com/LibreChat-AI/LibreChat | active | skip: server |

## Voice and dictation (`voice`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `voxtype` | Voxtype | Push-to-talk dictation for Wayland desktops | voice | linux | AUR `voxtype` or `voxtype-bin` | https://github.com/peteonrails/voxtype/releases | v1.1.1, 2026-10-15 | add (Linux) |
| `hyprwhspr` | hyprwhspr | System-wide local dictation for Linux, Hyprland first | voice | linux | AUR `hyprwhspr` | https://github.com/goodroot/hyprwhspr/releases | v1.52.0, 2026-11-02 | add (Linux) |
| `speech-note` | Speech Note | Linux app for offline speech to text, text to speech and translation | voice | linux | flatpak `net.mkiol.SpeechNote` (4.8.4) | https://github.com/mkiol/dsnote/releases | v4.9.0 on GitHub, 2026-06-28 | add (Linux) |
| `vibe-transcribe` | Vibe | Offline transcription of audio and video files with Whisper | voice | mac, linux, win | win: winget `Thewh1teagle.vibe` (3.3.0); linux: AUR `vibe-bin`; mac: release DMG (cask not checked) | https://github.com/thewh1teagle/vibe/releases | v3.3.0, 2026-10-29 | add: 8k stars. Needs an id other than `vibe` |
| `voicetypr` | VoiceTypr | Offline dictation app for mac and Windows | voice | mac, win | release assets (not on winget) | https://github.com/ideaplexa/voicetypr/releases | v2.0.11, 2026-11-02 | maybe: no package manager channel found |
| `whisrs` | whisrs | Dictation, read-aloud and voice commands for Wayland | voice | linux | AUR (package name not checked) | https://github.com/y0sif/whisrs/releases | v0.2.0, 2026-10-31 | maybe: small (147 stars) |
| `whisperx` | WhisperX | Transcription with word timestamps and speaker labels | voice | mac, linux, win | uv `whisperx` | https://github.com/m-bain/whisperX/releases | v3.8.6, 2026-05-25 | maybe: large PyTorch install |
| `f5-tts` | F5-TTS | Text to speech with voice cloning | voice | mac, linux, win | uv `f5-tts` | https://github.com/SWivid/F5-TTS/releases | 1.1.22, 2026-07-23 | maybe: large PyTorch install |
| `chatterbox` | Chatterbox | Resemble AI's open text-to-speech model | voice | mac, linux, win | uv `chatterbox-tts` (0.1.7, March) | https://github.com/resemble-ai/chatterbox | PyPI 0.1.7, March 2026 | maybe: past the six-month line |
| | Whispering (Epicenter) | Dictation app | | | | https://github.com/EpicenterHQ/epicenter/releases | v7.11.0, 2025-12-27 | skip: no release in over ten months |
| | Kokoro | Text-to-speech model | | | | https://github.com/hexgrad/kokoro | PyPI 2025-04 | skip: stale |
| | openai-whisper | Whisper reference package | | | | https://github.com/openai/whisper/releases | v20250625 | skip: stale; `whisper-cpp` and others cover it |

New platform channels for existing voice entries: `handy` is winget `cjpais.Handy` (0.10.0) and AUR `handy-bin`; `openwhispr` is winget `OpenWhispr.OpenWhispr` (1.11.0) and on the AUR; `buzz` is winget `ChidiWilliams.Buzz` (1.4.4) and flatpak `io.github.chidiwilliams.Buzz`; `wispr-flow` is winget `WisprFlow.WisprFlow`; the new Hex (below) has Windows and Linux builds.

## Image and video AI (`image-gen`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `invokeai` | InvokeAI | Local image generation studio | image-gen | mac, linux, win | win: winget `InvokeAI,Inc.InvokeCommunityEdition` (launcher 1.8.5); mac/linux: launcher download; uv `invokeai` | https://github.com/invoke-ai/InvokeAI/releases | v6.14.4, 2026-11-03 | add: 29k stars |
| `chainner` | chaiNNer | Node-based image processing app (upscaling, conversions, batches) | image-gen | mac, linux, win | mac: cask `chainner` (0.25.1); win: winget `chaiNNer-org.chaiNNer` (0.25.1); linux: release assets | https://github.com/chaiNNer-org/chaiNNer/releases | v0.26.1, 2026-10-27 | add: covers the upscaling gap left by Upscayl |
| `pinokio` | Pinokio | App that installs and runs community AI apps in one click | image-gen (or local-apps) | mac, linux, win | win: winget `pinokiocomputer.pinokio` (8.3.1); linux: AUR `pinokio-bin`; mac: release DMG | https://github.com/pinokiocomputer/pinokio/releases | v8.3.1, 2026-11-02 | maybe: the apps it installs run community scripts aiup cannot review |
| `amuse` | Amuse | Windows app for image and video generation on AMD hardware | image-gen | win | release installer (not on winget) | https://github.com/saddam213/AmuseAI/releases | v3.8.6, 2026-10-29 | maybe: Windows only, no package channel |
| | WanGP | Video generation for small GPUs | | | script install | https://github.com/deepbeepmeep/WanGP | manager-v0.1.13, 2026-11-01 | skip: source install only |
| | SD.Next | Image generation web UI | | | git install | https://github.com/vladmandic/sdnext | no releases | skip: source install only |
| | SwarmUI | Image generation web UI | | | | https://github.com/mcmonkeyprojects/SwarmUI/releases | 0.9.8-Beta, 2026-02-06 | skip: no release in nine months |
| | Fooocus | Image generation | | | | https://github.com/lllyasviel/Fooocus/releases | v2.5.5, 2024-08-12 | skip: stale |
| | krita-ai-diffusion | Krita plugin | | | | https://github.com/Acly/krita-ai-diffusion/releases | v1.53.0, 2026-08-22 | skip: a plugin installed inside Krita |

New platform channels for existing entries: `comfyui` is winget `Comfy.ComfyUI-Desktop` (1.1.8) and AUR `comfyui` (0.43.0); `stability-matrix` was not found on winget.

## Terminals (`terminals`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `windows-terminal` | Windows Terminal | Microsoft's terminal for Windows | terminals | win | winget `Microsoft.WindowsTerminal` (1.25.2733.0) | https://github.com/microsoft/terminal/releases | v1.25.2733.0, 2026-10-02 | add (Windows) |
| `rio` | Rio | GPU-accelerated terminal | terminals | mac, linux, win | mac: cask `rio`; linux: Arch `extra/rio`; win: winget `raphamorim.rio` (0.5.28) | https://github.com/raphamorim/rio/releases | v0.5.29, 2026-11-01 | add |
| `tabby-terminal` | Tabby | Terminal and SSH client | terminals | mac, linux, win | mac: cask `tabby`; win: winget `Eugeny.Tabby` (1.0.238); linux: AUR `tabby-bin` | https://github.com/Eugeny/tabby/releases | v1.0.238, 2026-10-07 | add: 75k stars. Not related to TabbyML |
| `kaku` | Kaku | Mac terminal tuned for working with AI agents | terminals | mac | cask `kaku` (0.27.1) | https://github.com/tw93/Kaku/releases | V0.27.1, 2026-10-27 | add |
| `alacritty` | Alacritty | GPU-accelerated terminal | terminals | linux, win | linux: Arch `extra/alacritty` (0.17.0); win: winget `Alacritty.Alacritty` (0.17.0); mac cask is disabled | https://github.com/alacritty/alacritty/releases | v0.17.0, 2026-04-06 | add for Linux and Windows only; keep it out on mac (cask disabled for failing Gatekeeper) |
| `zellij` | Zellij | Terminal workspace and multiplexer | dev-utils (next to `tmux`) | mac, linux, win | formula `zellij`; Arch `extra/zellij`; winget `Zellij.Zellij` (0.45.1) | https://github.com/zellij-org/zellij/releases | v0.45.1, 2026-08-28 | add |
| `contour` | Contour | Modern terminal emulator | terminals | mac, linux, win | mac: cask `contour`; win: winget `contour-terminal.Contour` | https://github.com/contour-terminal/contour/releases | v0.8.0.9335, 2026-10-23 | maybe |
| `foot` | foot | Fast, light Wayland terminal | terminals | linux | Arch `extra/foot` (1.28.0) | https://codeberg.org/dnkl/foot | 1.28.0 (Arch) | maybe: Linux only |
| `ptyxis` | Ptyxis | GNOME terminal that knows about containers | terminals | linux | flatpak `app.devsuite.Ptyxis` (50.1) | https://flathub.org/apps/app.devsuite.Ptyxis | 50.1 | maybe |
| `wave` | Wave | Terminal with built-in AI and file previews | terminals | mac, linux, win | mac: cask `wave` (0.14.5); win: winget `CommandLine.Wave` | https://github.com/wavetermdev/waveterm/releases | v0.14.5, 2026-04-16 | maybe: left out on 2026-10-14 as inactive; it has shipped since, but six months ago |
| | WezTerm | Terminal | | | | https://github.com/wezterm/wezterm/releases | 20240203 | skip: no release since February 2024 |

New platform channels for existing entries: `ghostty` is in Arch `extra` (1.3.1); `warp-app` is winget `Warp.Warp` and AUR `warp-terminal-bin`; `kitty` is in Arch `extra`.

## Sandboxes and VMs (`sandboxes`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `microsandbox` | microsandbox | Runs untrusted code in fast microVMs | sandboxes | mac, linux, win | linux: AUR `microsandbox`; win: winget `SuperRadCompany.Microsandbox` (0.7.13); mac: install script (not reviewed) | https://github.com/superradcompany/microsandbox/releases | v0.7.13, 2026-11-01 | add: confirm it does not need a long-running server |
| `nono` | nono | Kernel-level sandbox for agents (Landlock on Linux, Seatbelt on mac) | sandboxes | mac, linux | formula `nono` (0.81.0); AUR `nono` is a different project | https://github.com/nolabs-ai/nono/releases | v0.81.0, 2026-10-29 | add |
| `devcontainer` | Dev Containers CLI | Builds and runs dev containers from `devcontainer.json` | sandboxes | mac, linux, win | npm `@devcontainers/cli` (0.90.0); formula `devcontainer`; AUR `devcontainer-cli` | https://github.com/devcontainers/cli | npm 0.90.0, 2026-10-28 | add |
| `podman` | Podman | Daemonless containers | sandboxes | mac, linux, win | formula `podman`; Arch `extra/podman`; win: installer | https://github.com/podman-container-tools/podman/releases | v6.1.4, 2026-10-12 | add |
| `podman-desktop` | Podman Desktop | Desktop app for containers and Kubernetes | sandboxes | mac, linux, win | mac: cask `podman-desktop`; win: winget `RedHat.Podman-Desktop` (1.30.5); linux: flatpak `io.podman_desktop.PodmanDesktop` | https://github.com/podman-desktop/podman-desktop/releases | v1.30.5, 2026-10-13 | add |
| `lima` | Lima | Linux VMs with file sharing and port forwarding | sandboxes | mac, linux, win | formula `lima` (2.2.1); win: winget `Lima.Lima` (2.2.0); linux: AUR `lima-bin` | https://github.com/lima-vm/lima/releases | v2.2.1, 2026-10-03 | add |
| `colima` | Colima | Container runtime on top of Lima | sandboxes | mac, linux | formula `colima` | https://github.com/abiosoft/colima/releases | v0.10.3, 2026-06-04 | add |
| `multipass` | Multipass | Ubuntu VMs on demand | sandboxes | mac, linux, win | mac: cask `multipass`; win: winget `Canonical.Multipass` (1.16.4, trails) | https://github.com/canonical/multipass/releases | v1.17.0, 2026-10-19 | maybe: runs a background daemon |
| `docker-desktop` | Docker Desktop | Docker engine, CLI and GUI in one app | sandboxes | mac, linux, win | mac: cask `docker-desktop` (4.97.0); win: winget `Docker.DockerDesktop` (4.97.0) | https://docs.docker.com/desktop/release-notes/ | 4.97.0 | maybe: needs a paid plan at larger companies, and runs a background VM and helper service |
| `boxlite` | BoxLite | Embeddable microVM for agents | sandboxes | not checked | not checked | https://github.com/boxlite-ai/boxlite/releases | v0.11.0, 2026-10-30 | maybe |
| `shuru` | Shuru | Mac microVM sandbox | sandboxes | mac | Homebrew (not checked) | https://github.com/superhq-ai/shuru | not verified | maybe: release date not verified |
| `cua` | Cua CLI | Sandboxed desktops for computer-use agents | sandboxes | mac, linux | uv `cua-cli` (0.10.1) | https://github.com/trycua/cua/releases | 2026-11-03 | maybe |
| `bubblewrap` | bubblewrap | Unprivileged Linux sandbox tool | sandboxes | linux | Arch `extra/bubblewrap` (0.13.1) | https://github.com/containers/bubblewrap/releases | v0.13.1, 2026-10-14 | maybe: usually already installed as a dependency |
| `firejail` | Firejail | Linux sandbox for apps | sandboxes | linux | Arch `extra/firejail` | https://github.com/netblue30/firejail/releases | 0.9.82, 2026-11-02 | maybe |
| `distrobox` | Distrobox | Run any Linux distro in a container | sandboxes | linux | Arch `extra/distrobox` | https://github.com/89luca89/distrobox/releases | 1.8.2.5, 2026-04-27 | maybe |
| | gVisor | Container sandbox runtime | | linux | | https://github.com/google/gvisor/releases | 2026-11-02 | skip: server runtime |
| | Firecracker | microVM monitor | | linux | | https://github.com/firecracker-microvm/firecracker/releases | v1.17.0, 2026-09-10 | skip: server building block |
| | container-use | Dagger's agent containers | | | formula `container-use` (0.4.2) | https://github.com/dagger/container-use/releases | v0.4.2, 2025-08-19 | skip: no release in over a year |
| | DevPod | Dev environments | | | cask `devpod` | https://github.com/loft-sh/devpod/releases | v0.6.15, 2025-03-10 | skip: stale (an active fork exists at skevetter/devpod but is small) |
| | Leash | Agent sandbox | | | | https://github.com/strongdm/leash/releases | v1.1.7, 2026-03-11 | skip: quiet since spring |

## AI browsers (`browsers`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `lightpanda` | Lightpanda | Headless browser built for AI and automation | browsers | mac, linux | linux: AUR `lightpanda-bin`; mac: release binary | https://github.com/lightpanda-io/browser/releases | 1.0.2, 2026-10-23 | maybe: it now has stable releases (the 2026-10-14 reason is gone), but it is a browser engine, so it needs my call against the no-browser-runtime rule |
| `fellou` | Fellou | Agent browser | browsers | mac, win | vendor download (not on winget) | https://fellou.ai/download | not checked | maybe: no package channel |
| `genspark` | Genspark browser | Agent browser | browsers | mac, win | vendor download (not on winget) | https://www.genspark.ai | not checked | maybe: no package channel |
| `opera-neon` | Opera Neon | Opera's agent browser | browsers | mac, win | vendor download (not on winget) | https://www.operaneon.com | not checked | maybe: paid subscription |
| | dev-browser | Browser skill for agents | | | npm `dev-browser` | https://github.com/SawyerHood/dev-browser | v0.2.9, 2026-07-15 | skip: built on Playwright (rule 9) |
| | ChatGPT Atlas | OpenAI browser | | | | https://formulae.brew.sh/cask/chatgpt-atlas | discontinued 2026-08 | skip: retired |

New platform channels for existing entries: `browseros` is winget `BrowserOS.BrowserOS` and AUR `browseros-bin`. Comet and Dia were not found on winget.

## AI utilities and agent helpers (`llm-utils` and `agent-tools`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `claude-mem` | claude-mem | Saves what an agent did and feeds it back in later sessions | agent-tools | mac, linux, win | npm `claude-mem` (all) | https://github.com/thedotmack/claude-mem/releases | v15.9.0, 2026-11-02 | add: 111k stars |
| `ccstatusline` | ccstatusline | Custom status line for Claude Code | agent-tools | mac, linux, win | npm `ccstatusline` (all) | https://github.com/sirmalloc/ccstatusline/releases | v2.2.33, 2026-10-30 | add |
| `bmad` | BMAD Method | Spec-driven agile workflow kit for coding agents | agent-tools | mac, linux, win | npm `bmad-method` (all) | https://github.com/bmad-code-org/BMAD-METHOD/releases | v6.12.4, 2026-10-14 | add: next to `specify` and `openspec` |
| `basic-memory` | Basic Memory | Local Markdown memory for agents, served over MCP | agent-tools | mac, linux, win | uv `basic-memory` | https://github.com/basicmachines-co/basic-memory/releases | v1.0.0, 2026-10-29 | add |
| `code2prompt` | code2prompt | Packs a codebase into one prompt | llm-utils | mac, linux, win | formula `code2prompt` (4.3.0) | https://github.com/mufeedvh/code2prompt | formula 4.3.0; last GitHub release v4.2.0, 2025-12-11 | maybe: overlaps `repomix` |
| `yek` | yek | Fast tool that packs repo files for a model | llm-utils | mac, linux, win | formula `yek` (0.25.5) | https://github.com/mohsen1/yek/releases | v0.25.5, 2026-06-29 | maybe: overlaps `repomix` |
| `ttok` | ttok | Counts and trims tokens from the command line | llm-utils | mac, linux, win | uv `ttok` | https://github.com/simonw/ttok/releases | 1.0, 2026-10-09 | add: small, pairs with `llm` |
| `ck` | ck | Local semantic and keyword code search | dev-utils | mac, linux, win | GitHub releases (cargo) | https://github.com/BeaconBay/ck/releases | 0.8.1, 2026-10-11 | maybe: channel not reviewed |
| `probe` | Probe | Semantic code search for large codebases | dev-utils | mac, linux, win | npm `@probelabs/probe` | https://github.com/probelabs/probe/releases | v0.6.0-rc344, 2026-10-28 | maybe: only release candidates |
| `inspect-ai` | Inspect | UK AISI's framework for running model evals | llm-utils | mac, linux, win | uv `inspect-ai` (0.3.287) | https://github.com/UKGovernmentBEIS/inspect_ai/releases | 0.3.287, 2026-10-31 | add: next to `promptfoo` |
| `garak` | garak | NVIDIA's LLM vulnerability scanner | llm-utils | mac, linux, win | uv `garak` (0.17.1) | https://github.com/NVIDIA/garak/releases | v0.17.1, 2026-10-16 | add |
| `deepeval` | DeepEval | Eval framework for LLM apps | llm-utils | mac, linux, win | uv `deepeval` | https://github.com/confident-ai/deepeval/releases | python-v4.2.4, 2026-09-22 | maybe: more library than tool |
| `lm-eval` | lm-evaluation-harness | Standard benchmark runner for models | llm-utils | mac, linux, win | uv `lm-eval` (0.4.13) | https://github.com/EleutherAI/lm-evaluation-harness/releases | v0.4.13, 2026-08-31 | maybe |
| `phoenix` | Arize Phoenix | Local tracing and eval UI for LLM apps | llm-utils | mac, linux, win | uv `arize-phoenix` | https://github.com/Arize-ai/phoenix/releases | 2026-11-02 | maybe: runs a local server while in use |
| `marker` | Marker | Converts PDFs to Markdown | llm-utils | mac, linux, win | uv `marker-pdf` (2.1.0) | https://github.com/datalab-to/marker/releases | v2.1.0, 2026-10-29 | add: next to `docling` and `markitdown` |
| `mineru` | MinerU | Converts PDFs and documents to Markdown | llm-utils | mac, linux, win | uv `mineru` | https://github.com/opendatalab/MinerU/releases | 4.1.4, 2026-11-02 | maybe: overlaps docling and marker |
| `trafilatura` | Trafilatura | Pulls the main text out of web pages | llm-utils | mac, linux, win | formula `trafilatura` (2.3.1); uv `trafilatura` | https://github.com/adbar/trafilatura/releases | v2.3.1, 2026-10-06 | maybe: overlaps `defuddle` |
| `claude-monitor` | Claude Code Usage Monitor | Live usage and limit predictions for Claude Code | agent-tools | mac, linux, win | uv `claude-monitor` | https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor/releases | v4.0.0, 2026-06-27 | maybe: overlaps `ccusage` |
| `task-master` | Task Master | Task lists and planning for coding agents | agent-tools | mac, linux, win | npm `task-master-ai` | https://github.com/eyaltoledano/claude-task-master/releases | 0.43.1, 2026-03-31 | maybe: past the six-month line |
| `bifrost` | Bifrost | LLM gateway that fronts many providers | llm-utils | mac, linux, win | npm `@maximhq/bifrost` (1.6.3, May) | https://github.com/maximhq/bifrost/releases | repo releases 2026-11-02 | maybe: runs as a gateway service; cask `bifrost` is a different app |
| | gitingest | Repo to prompt text | | | formula and uv | https://github.com/coderamp-labs/gitingest/releases | v0.3.1, 2025-07-31 | skip: no release in over a year |
| | files-to-prompt | Files to prompt text | | | | https://github.com/simonw/files-to-prompt | 0.6, 2025-02-19 | skip: stale |
| | mgrep | Semantic grep | | | npm | https://github.com/mixedbread-ai/mgrep/releases | v0.1.13, 2026-04-25 | skip: quiet since April; needs an account |
| | Portkey gateway | LLM gateway | | | | https://github.com/Portkey-AI/gateway/releases | v1.15.2, 2026-01-12 | skip: stale |
| | Flowise | Visual agent builder | | | | https://github.com/FlowiseAI/Flowise | archived | skip |
| | any-llm | Provider library | | | | https://github.com/mozilla-ai/any-llm | 1.41.0, 2026-10-30 | skip: library |

## Automation and general agents (`automation`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `eigent` | Eigent | Open-source cowork desktop app for multi-agent tasks | automation | mac, win | mac: cask `eigent` (1.0.7); win: winget `Eigent.Eigent` (1.0.5, trails) | https://github.com/eigent-ai/eigent/releases | v1.0.7, 2026-10-30 | add |
| `ui-tars` | UI-TARS Desktop | ByteDance's desktop app that drives your computer from screenshots | automation | mac, win | mac: cask `ui-tars` (0.2.4); win: not on winget | https://github.com/bytedance/UI-TARS-desktop/releases | v0.3.1, 2026-10-08 | maybe: computer control, review carefully |
| `agent-tars` | Agent TARS CLI | Multimodal agent for the terminal and browser | automation | mac, linux, win | npm `@agent-tars/cli` (0.3.1) | https://www.npmjs.com/package/@agent-tars/cli | 0.3.1, 2026-10-08 | maybe: check that it does not pull in Playwright or Puppeteer before adding |
| `crewai` | crewAI | Framework and CLI for multi-agent crews | automation | mac, linux, win | uv `crewai` (1.15.34) | https://github.com/crewAIInc/crewAI/releases | 1.15.34, 2026-11-01 | maybe: mostly a library |
| `ufo` | Microsoft UFO | Windows desktop agent that drives apps through UI Automation | automation | win | source install | https://github.com/microsoft/UFO/releases | v3.0.10, 2026-09-22 | maybe: no package channel |
| | Agent S | Computer-use agent | | | | https://github.com/simular-ai/Agent-S/releases | v0.3.2, 2025-12-16 | skip: no release in over ten months |
| | Dify | Agent app platform | | | | https://github.com/langgenius/dify | 1.18.0, 2026-10-23 | skip: server platform |

## Editors (`editors`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `positron` | Positron | Posit's data science IDE with built-in AI assistant | editors | mac, linux, win | mac: cask `positron`; win: winget `Posit.Positron` (2026.10.2) | https://github.com/posit-dev/positron/releases | 2026.10.2-3, 2026-10-26 | add |
| `vscodium` | VSCodium | VS Code built without Microsoft telemetry | editors | mac, linux, win | mac: cask `vscodium`; win: winget `VSCodium.VSCodium`; linux: flatpak `com.vscodium.codium` | https://github.com/VSCodium/vscodium/releases | 1.143.17232, 2026-10-28 | add |
| `neovim` | Neovim | Terminal editor used with many AI plugins | editors | mac, linux, win | formula `neovim`; Arch `extra/neovim` | https://github.com/neovim/neovim/releases | v0.12.6, 2026-10-09 | maybe: not AI-specific |
| | Helix | Terminal editor | | | | https://github.com/helix-editor/helix/releases | 25.07.1, 2025-07-18 | skip: no release in over a year |
| | Theia IDE | Eclipse IDE with AI features | | | | https://github.com/eclipse-theia/theia-ide | no GitHub releases seen | skip for now: release channel not confirmed |
| | Void | AI editor | | | | https://github.com/voideditor/void | archived | skip |
| | PearAI | AI editor | | | | https://github.com/trypear/pearai-app | v1.8.9, 2025-05-02 | skip: stale |

## Essentials for Linux and Windows (`infra`)

| Proposed id | Name | What it does | Category | Platforms | Install channels | Evidence | Last release seen | Recommendation |
|---|---|---|---|---|---|---|---|---|
| `winget` | winget | Windows package manager most Windows entries above use | infra | win | ships with Windows (App Installer) | https://github.com/microsoft/winget-cli/releases | v1.29.380, 2026-09-21 | add when Windows support lands: needed as a prerequisite, like `brew` |
| `flatpak` | Flatpak | Linux app sandbox and package format several Linux entries use | infra | linux | Arch `extra/flatpak` | https://flatpak.org | current in Arch | add when Linux support lands |
| `powershell` | PowerShell | Cross-platform shell | infra | mac, linux, win | formula `powershell` (7.6.9); winget `Microsoft.PowerShell` (7.6.9.0) | https://github.com/PowerShell/PowerShell/releases | 7.6.9 | maybe |
| `powertoys` | PowerToys | Windows utilities, including Command Palette and an AI paste tool | dev-utils | win | winget `Microsoft.PowerToys` (0.102.3001) | https://github.com/microsoft/PowerToys/releases | v0.102.3001, 2026-10-27 | maybe |

Linux note: most `dev-utils` and `infra` formulae already have Arch `extra` packages under the same names. `pandoc` is the exception on Arch, where the current build is AUR `pandoc-bin`.

## Existing entries to retire or rename

| Entry | What changed | Evidence | Suggested action |
|---|---|---|---|
| `hex` | kitlangton/Hex is archived. Its README says Hex moved to anomalyco/hex and the Swift app is no longer maintained. The `kitlangton-hex` cask still ships the legacy 0.8.5 (2026-08-27). The new Hex is v3.3.0 (2026-11-02, 4.1k stars) for mac, Windows and Linux, and hex.kitlangton.com now redirects to anoma.ly/hex. | https://github.com/kitlangton/Hex and https://github.com/anomalyco/hex/releases | Retarget: mac to the publisher tap cask `anomalyco/tap/hex` (Apple silicon, macOS 15+); Windows installer; Linux AUR `hex-bin` (3.3.0) or `.deb`. Update the docs URL and label floor |
| `superset` | Repo renamed to ParadevAI/Paradev ("formerly Superset"). Cask token is still `superset` and its homepage is now paradev.com. | https://github.com/ParadevAI/Paradev (desktop-v2.0.3, 2026-11-01) | Relabel as Paradev and update the docs URL; the id and cask can stay |
| `codebuff` | The CodebuffAI/codebuff repo was renamed to CodebuffAI/freebuff. npm `codebuff` last shipped 1.0.688 on 2026-09-08; npm `freebuff` shipped 0.2.35 on 2026-10-29. | https://github.com/CodebuffAI/freebuff | Add `freebuff` and set `codebuff` to sunset, then remove it if npm `codebuff` stays quiet |
| `daytona` | daytonaio/daytona was archived in July 2026; its README says core development moved to a private codebase in June 2026. The CLI tap `daytonaio/homebrew-cli` is still active (v0.227.3, commit 2026-11-02). | https://github.com/daytonaio/daytona and https://github.com/daytonaio/homebrew-cli | Keep. Point the docs URL at the CLI docs or tap, and note the closed core |
| `aider` | No GitHub release since v0.86.0 (2025-08-09). PyPI `aider-chat` 0.86.2 came out 2026-02-12; last repo push 2026-05-22. | https://github.com/Aider-AI/aider/releases and https://pypi.org/project/aider-chat/ | Watch. It reaches the one-year line in February 2027. `cecli` (above) is the active fork if a successor is needed |
| `sgpt` | Last release 1.5.1 on 2026-05-06. | https://pypi.org/project/shell-gpt/ | Watch |
| `gemini` | Already sunset after Homebrew deprecated the formula. npm `@google/gemini-cli` is still shipping (0.66.0, 2026-10-27). | https://www.npmjs.com/package/@google/gemini-cli | No change. Recheck whether the sunset reason still applies, since the npm channel is active |
| `kimi` | MoonshotAI/kimi-cli (Python) is archived and replaced by kimi-code. | https://www.npmjs.com/package/@moonshot-ai/kimi-code | No change: the entry already uses `@moonshot-ai/kimi-code` (2.4.1, 2026-10-30) |
| `comfyui` | Comfy-Org/desktop is archived and replaced by Comfy-Org/Comfy-Desktop (v1.1.8, 2026-10-22). The `comfy` cask still works. | https://github.com/Comfy-Org/Comfy-Desktop/releases | Update the docs URL |
| `mcp-remote` | Repo moved from geelen to punkpeye. | https://github.com/punkpeye/mcp-remote | Update the docs URL |
| `mcporter`, `peekaboo` | Repos moved to the openclaw organization. | https://github.com/openclaw | Update the docs URLs |
| `forgecode` | Repo is tailcallhq/forgecode. | https://github.com/tailcallhq/forgecode | Check the docs URL |
| `whisperkit` | Repo is now argmax-oss-swift. | https://github.com/argmaxinc | No change if the manifest already points there (it does) |
| `browser-use` | Not checked in this pass. Rule 9 says no tool whose install pulls in Playwright. | https://github.com/browser-use/browser-use | Confirm its current package does not depend on Playwright |

Repos that moved but are not catalog entries (use the new names if they are added): Tart to openai/tart, Nexa SDK to qualcomm/GenieX, text-generation-webui to oobabooga/textgen, Perplexica to Vane, Witsy to Kochava-Studios/witsy, smithery-cli to arcadeai-labs, coder/mux to coder/xum.

Everything else I checked looked healthy. Every npm and uv entry has shipped within roughly six months. No core Homebrew formula or cask in the catalog is deprecated or disabled apart from `gemini`'s formula. The earlier exclusions still hold: the `alacritty` cask is disabled (it fails Gatekeeper, 2026-09-01), `chatgpt-atlas` is disabled (Atlas was discontinued in August 2026), `codex-app` is deprecated, and `devpod` is stale.

## Category cleanup suggestions

Current sizes: coding-agents 40, voice 24, local-ai 22, agent-tools 17, workspaces 16, local-apps 16, mcp 14, dev-utils 14, media 12, llm-utils 11, chat 11, editors 10, sandboxes 9, infra 8, automation 7, media-tools 6, image-gen 6, adapters 6, terminals 5, browsers 5 (259 total).

1. **Add `orchestrators` ("Agent orchestrators").** Tools that run many agents at once are spread across `agent-tools` (claude-squad, agent-deck, git-gtr, worktrunk) and `workspaces` (conductor, emdash, superset, nimbalyst, commander). This pass adds about ten strong ones (Orca, herdr, Multica, Paseo, Happy, Ruflo, Agent of Empires, CLI Agent Orchestrator, Gas Town). A category for "run several agents side by side" would leave `workspaces` as one vendor's desktop app for its own agent, and `agent-tools` as add-ons such as usage, specs, rules and memory.
2. **Split `coding-agents` (40).** It is twice the size of any other category. One split: vendor agents (Claude Code, Codex, Copilot, Gemini, Kiro, Qwen, Kimi, MiniMax, CodeBuddy, Qoder, Devin, Junie, Auggie, Amp, Droid) and open-source or community agents (pi, opencode, crush, goose, cline, kilo, forgecode, vtcode, gptme, nanocoder and the rest). Each half lands near 20.
3. **Fold `adapters` (6) into `agent-tools` or rename it.** The display name "Integrations" hides what it is. Either rename it "ACP adapters" so the purpose is clear, or move its six entries into `agent-tools`. If Toad and other ACP clients are added, the rename is the better choice.
4. **Clarify `local-ai` (22) and `local-apps` (16).** The display names "Local models" and "Local AI apps" read alike, and both blurbs say "on your Mac". Suggest "Local model runtimes" (commands and servers) and "Local model apps" (desktop apps), and drop "on your Mac" once Linux and Windows entries exist.
5. **Merge `image-gen` (6) with `media-tools` (6), or rename them.** "Image and video AI", "Creative apps" and "Media tools" are three names for overlapping things. Either merge `image-gen` and `media-tools` into one "Media AI and tools" category, or keep them and rename `media` to "Creative apps (non-AI)" so the line is obvious. With InvokeAI, chaiNNer and Pinokio, `image-gen` grows to about 9, which is enough to stand alone.
6. **Leave `voice` (24) together but sort it.** It mixes dictation apps, meeting note takers (granola, meetily, anarlog), speech engines (whisper-cpp, parakeet-mlx, mlx-audio) and text to speech (piper, pocket-tts). If it grows past 30 with the Linux dictation tools, split meeting notes and speech engines into their own groups.
7. **Grow `terminals` (5) and `browsers` (5).** Both are small because they were mac-only. Terminals gains Windows Terminal, Rio, Tabby, Kaku and Alacritty (Linux and Windows). Browsers mostly gains maybes, so keep it as is.
8. **Move `tmux` and the proposed `zellij` next to the orchestrators, or keep them in `dev-utils`.** Several orchestrators depend on tmux, so a note in their dependency field is enough; no move needed.
9. **Do not add an `llm-gateways` category yet.** The gateway candidates (Bifrost, agentgateway, ContextForge, MCPJungle) are mostly services. Keep any that pass review in `llm-utils` or `mcp`.
10. **Make `infra` platform-aware.** When Linux and Windows support lands, `winget` and `flatpak` belong beside `brew`, `npm` and `uv` as prerequisites, and the blurb "Runtimes and installers other tools need" already fits.
11. **Update blurbs that say "on your Mac".** `local-ai`, `local-apps` and the `detected` and `homebrew/*` blurbs name the Mac. That will read wrong on Linux and Windows.

## What this pass did not confirm

- Channels marked "not checked", mostly Linux release assets and a few mac DMGs.
- Whether microsandbox, Lemonade on Linux, or the gateways need a long-running service.
- IBM Bob's account and license terms, and Claurst's code origin and license.
- Whether Agent TARS or the current Browser Use package pull in Playwright or Puppeteer.
- Shuru's release history.
- Winget ids were found with `winget search`; I did not open each manifest, so publisher ids should be checked against the vendor's own docs before use.
