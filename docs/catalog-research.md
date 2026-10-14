# Catalog research review

The complete dated disposition record for the 83-entry starting catalog is [Catalog accuracy audit (2026-08-25)](catalog-accuracy-2026-08-25.md). This file remains the standing policy and candidate notebook. The newest full pass is the [2026-10-14 catalog review](catalog-review-2026-10-14.md).

This is the review log for expanding aiup's managed catalog. The catalog is deliberately split into two evidence lanes:

- **Managed** entries have an official macOS installation/update path that aiup can execute and validate.
- **Detected** entries are discovered from the local Mac but remain detected-only until their owning distribution method and update/removal contract are reviewed. App bundles may expose a separate exact-path cleanup preview; that is not an update contract and never broad-deletes `~/Library`.

aiup does not turn a repository name into an updater automatically. A new managed entry must have a stable identifier, category, lifecycle, official documentation, dependency declaration, installer/updater, and remover. Package-manager entries inherit dependency resolution from Homebrew, npm, or uv; aiup does not attempt to reproduce those package managers' dependency solvers.

## Added in the 2026-08-21 review

| Entry | Decision | Install/update path | Evidence |
|---|---|---|---|
| `vibe` | Managed, active | `uv tool install/upgrade mistral-vibe` | [Mistral Vibe repository](https://github.com/mistralai/mistral-vibe) documents both the macOS installer and `uv tool install mistral-vibe`. |
| `llama-cpp` | Managed, active | Homebrew formula `llama.cpp` | [llama.cpp install guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md) documents `brew install llama.cpp`; Homebrew publishes the formula and its dependencies. |
| `llama-app` | Managed, active | Homebrew cask `llama-app` | [Homebrew's Llama cask](https://formulae.brew.sh/cask/llama-app) identifies the official `ggml-org/Llama-macOS` menu-bar app and its macOS/Apple Silicon requirements. |
| `openhands` | Managed, sunset | `uv tool install/upgrade openhands` for legacy compatibility | [OpenHands CLI repository](https://github.com/OpenHands/OpenHands-CLI) says the CLI is no longer actively maintained and directs users toward Agent Canvas. aiup lists it with a sunset warning and does not recommend it. |
| `bun`, `pnpm` | Managed, active | Homebrew formulae `bun` and `pnpm` | [Bun](https://formulae.brew.sh/formula/bun) and [pnpm](https://formulae.brew.sh/formula/pnpm) publish macOS bottles and package-manager install commands. Homebrew resolves pnpm's Node dependency. |
| `jq`, `yq` | Managed, active | Homebrew formulae `jq` and `yq` | [jq](https://formulae.brew.sh/formula/jq) and [yq](https://formulae.brew.sh/formula/yq) are official Homebrew formulae for structured-data work used by development tooling. |
| `ripgrep`, `fd`, `just` | Managed, active | Homebrew formulae `ripgrep`, `fd`, and `just` | [ripgrep](https://formulae.brew.sh/formula/ripgrep), [fd](https://formulae.brew.sh/formula/fd), and [just](https://formulae.brew.sh/formula/just) publish macOS bottles and stable upgrade paths. |
| `shellcheck`, `actionlint` | Managed, active | Homebrew formulae `shellcheck` and `actionlint` | [ShellCheck](https://formulae.brew.sh/formula/shellcheck) and [actionlint](https://formulae.brew.sh/formula/actionlint) provide shell and GitHub Actions validation. actionlint declares ShellCheck as a dependency, which Homebrew resolves. |
| `whisper-cpp` | Managed, active | Homebrew formula `whisper.cpp` (renamed from `whisper-cpp`) | [Homebrew's whisper.cpp formula](https://formulae.brew.sh/formula/whisper.cpp) supplies a macOS bottle and points to the official [whisper.cpp](https://github.com/ggml-org/whisper.cpp) project. Model files remain a separate user choice and are not downloaded by aiup. |

## 2026-09-29 review

Removed as archived, unmaintained or inactive: `mods` (archived; Homebrew-deprecated), `continue` (read-only, final release), `openhands` (CLI unmaintained; successor Agent Canvas ships only as a DMG), `interpreter` (the Python package stopped in 2024 and the repository became a different product), `aichat` (no release in over a year), `gpt4all` (no release since February 2025), `diffusionbee` (no release since 2024; Mochi Diffusion and Stability Matrix cover local image generation), `upscayl` (no code change in a year) and `sox` (last release 2015; replaced by the maintained `sox-ng`). aiup does not remove installed copies; Homebrew-installed ones still appear in the Homebrew view.

Channel and target fixes: `pnpm` and `wrangler` now install from their official npm packages, which publish releases before the Homebrew formulae (an existing Homebrew copy is removed once the npm copy is in place); `whisper-cpp` follows Homebrew's rename to `whisper.cpp`.

Added, each verified against Homebrew, npm or PyPI metadata and a release in the last three months: coding agents `devin-cli`, `auggie`, `junie`, `letta`, `qoder`; adapters `claude-acp`, `codex-acp`; editors `devin-desktop` (formerly Windsurf), `kiro-ide`, `jetbrains-air`; workspaces `conductor`, `emdash`, `superset`, `amp-app`, `factory-app`, `antigravity-app`; chat `gemini-app`, `cherry-studio`, `msty-studio`, `boltai`, `chatbox`, `lobehub`; local AI `localai`, `ramalama`, `osaurus`, `mlx-vlm`, `hf`, `open-webui`; media `whisperkit`, `handy`, `voiceink`, `wispr-flow`, `stability-matrix`, `mochi-diffusion`, `sox-ng`; infrastructure `mise`; LLM utilities `repomix`, `markitdown`.

Candidates for a later review: ToolHive Studio, kitty, claude-squad, ccusage, Trae, Dia, Poe and ComfyUI Desktop (confirm its current source first). All of them were added on 2026-10-14, Poe in the second pass. Not added: the Kimi desktop cask (an installer wrapper, not the app), casks that are disabled or discontinued (`codex-app`, `chatgpt-atlas`, `msty`, `alacritty`), inactive projects (`@google/jules`, `vibe-kanban`, `@iflow-ai/iflow-cli`, exo, Wave, WezTerm, vllm-metal, mlx-whisper; vllm-metal is active again and was added on 2026-10-14 from its own tap), and Codebuff while it moves to `freebuff`.

## 2026-10-14 review

The first pass added 87 entries across eight new categories (`agent-tools`, `mcp`, `sandboxes`, `browsers`, `local-apps`, `voice`, `image-gen`, `media-tools`), moved existing desktop model apps and media tools into them, and set `gemini` to sunset after Homebrew deprecated its formula. The second pass added 43 more: tools from taps their publishers run, browser automation tools (aiup installs only their command, never a browser), Poe, and others found while checking the taps. It also added install channels, so each tool installs from whichever official channel publishes first, with the others available through `aiup channel`. Tools that only offer an unreviewed installer are still held. The full record, with every addition's channel and each held tool's reason, is the [2026-10-14 catalog review](catalog-review-2026-10-14.md).

## Confirmed existing coverage

- Amazon Q Developer's command-line documentation now says that the Q CLI has become the Kiro CLI, so aiup manages it as the `kiro` entry. There is no separate `amazon-q` entry, since it would be a stale duplicate. See [AWS's upgrade note](https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/upgrade-to-kiro.html).
- GitHub Copilot CLI is already represented by `copilot`; its official repository documents macOS support, the official installer, Homebrew formula, and npm package. See [GitHub Copilot CLI](https://github.com/github/copilot-cli).
- `whisper.cpp` is managed through Homebrew's `whisper.cpp` formula (renamed from `whisper-cpp`). aiup updates the engine and leaves model-file selection/download to the user; it does not silently fetch large model weights. See [whisper.cpp](https://github.com/ggml-org/whisper.cpp) and [the formula](https://formulae.brew.sh/formula/whisper.cpp).

## Review rules for future additions

1. Prefer the vendor's official installer or an official Homebrew/npm/uv distribution.
2. Verify macOS architecture and minimum OS requirements before adding an entry.
3. Default to the official channel that publishes new releases first (often npm, PyPI or the vendor installer, since Homebrew can trail by hours to a day), and list the other official packages as alternates. Keep Homebrew as the default when its formula bundles something the other channels lack, such as plugins or a runtime.
4. Reject entries whose only practical path is an unreviewed source clone, an arbitrary third-party script, or a destructive replacement.
5. Remove products that are archived, declared unmaintained or end of life, or inactive for more than a year; the catalog carries only maintained software. The lifecycle column stays for short, documented transitions.
6. Keep research candidates in this document until the update/remove contract is complete; local discovery still makes installed candidates visible immediately.
7. A Homebrew tap must be run by the tool's own publisher. aiup asks before it adds and trusts a missing tap.
8. Put a macOS floor stricter than macOS 14, or an Apple silicon requirement, in the label.
