# Catalog accuracy audit — 2026-08-25

This is the dated accuracy record for all **83 entries in aiup 2026.08.25-01**. The resulting 2026.08.25-02 managed catalog contains **81 entries**.

## Outcome

| Disposition | Starting entries | Meaning |
|---|---:|---|
| Confirmed | 73 | The existing stable id and managed contract remained supportable. |
| Corrected | 7 | Material lifecycle, distribution, or canonical-source data changed. |
| Downgraded | 1 | Still managed, but no longer represented as actively maintained. |
| Removed | 2 | Removed from managed actions; a local copy can still appear as detected-only. |
| Blocked / unverifiable | 0 | No starting entry was left managed with an unverified contract. |
| **Total** | **83** | Every starting entry has exactly one disposition below. |

The seven corrected ids are `gemini`, `pi`, `gsd2`, `opencode`, `goose`, `continue`, and `n8n`. `gpt4all` was downgraded to maintenance-only. `omp` and `plandex` were removed from the managed manifest.

## Method and contract notation

The audit used only current, read-only primary evidence: official vendor documentation and repositories, official npm and PyPI metadata, and Homebrew's formula/cask API and package pages. GitHub repository archive state, redirects, latest releases, and recent activity were checked where lifecycle mattered. No catalog software was installed, updated, removed, adopted, or trusted.

For every starting id, the review checked its label, category, lifecycle, official URL, macOS/architecture constraints, exact distribution target, update and removal route, version evidence, direct prerequisites, delegated dependency closure, account/license/download conditions, and whether aiup's implementation actually exposed those actions. The authoritative post-audit label/category/lifecycle/URL values are in [`macos/catalog/manifest.tsv`](../macos/catalog/manifest.tsv); [`scripts/check-catalog-contracts`](../scripts/check-catalog-contracts) verifies that every remaining row has non-empty version/install/update/remove contracts.

Contract abbreviations:

- **HBF `x`**: Homebrew formula `x`; version from Homebrew's installed formula record; install/update/remove delegated to Homebrew. Direct prerequisite `brew`; transitive closure is Homebrew's dependency solver.
- **HBC `x`**: Homebrew cask `x`; version from the installed cask record or app presence; install/update/remove delegated to Homebrew. Direct prerequisite `brew`.
- **NPM `x`**: official npm package `x` in aiup's isolated prefix; version from its package metadata; npm installs, updates, and removes it. Direct closure is `brew` → Homebrew Node/npm.
- **UV `x`**: PyPI package `x` managed with `uv tool`; version from uv/package or CLI evidence; uv installs, upgrades, and removes it. Direct prerequisite `uv`.
- **INST**: documented vendor installer or self-update adapter, with bounded user-path removal and CLI version evidence.
- **SPECIAL**: a reviewed tool-specific install/update/remove adapter and CLI/package version evidence.
- **APP**: a reviewed vendor-app updater with metadata/artifact validation, bundle version evidence, and exact-bundle removal.

`macOS 14+` is aiup's runtime baseline. A row lists a stricter minimum or architecture when primary metadata materially narrows that baseline. “Account” includes a vendor login or provider credentials; “plan” means features can depend on a paid subscription. “Large” means a desktop artifact or optional model download can be substantial. Homebrew's initial installer may request administrator authentication; aiup itself does not invoke `sudo`.

## All 83 starting dispositions

| Id | Category / lifecycle | Disposition | Exact managed contract | Material platform and use conditions | Primary evidence |
|---|---|---|---|---|---|
| `brew` | infra / active | Confirmed | SPECIAL official Homebrew installer/update; not removable by aiup | macOS 14+, Xcode CLT; installer may authenticate admin | [Homebrew](https://github.com/Homebrew/brew) |
| `npm` | infra / active | Confirmed | SPECIAL Homebrew `node`; npm version; update-only | Homebrew dependency; not removable by aiup because it is shared infrastructure | [Node.js](https://github.com/nodejs/node) |
| `uv` | infra / active | Confirmed | INST `https://astral.sh/uv/install.sh`; `uv self update`; bounded `uv`/`uvx` removal | macOS arm64/x86_64 | [Astral uv](https://github.com/astral-sh/uv) |
| `fzf` | infra / active | Confirmed | HBF `fzf` | Required interactive dependency | [fzf](https://formulae.brew.sh/formula/fzf) |
| `gh` | infra / active | Confirmed | HBF `gh` | GitHub account/auth needed for account operations | [GitHub CLI](https://formulae.brew.sh/formula/gh) |
| `wrangler` | infra / active | Confirmed | HBF `cloudflare-wrangler` | Node dependency delegated by Homebrew; Cloudflare account for provider work | [Wrangler](https://formulae.brew.sh/formula/cloudflare-wrangler) |
| `deno` | infra / active | Confirmed | HBF `deno` | Homebrew build metadata includes Xcode build requirements | [Deno](https://formulae.brew.sh/formula/deno) |
| `bun` | infra / active | Confirmed | HBF `bun` | macOS arm64/x86_64 | [Bun](https://formulae.brew.sh/formula/bun) |
| `pnpm` | infra / active | Confirmed | HBF `pnpm` | Node ecosystem package manager | [pnpm](https://formulae.brew.sh/formula/pnpm) |
| `jq` | infra / active | Confirmed | HBF `jq` | macOS arm64/x86_64 | [jq](https://formulae.brew.sh/formula/jq) |
| `yq` | infra / active | Confirmed | HBF `yq` | macOS arm64/x86_64 | [yq](https://formulae.brew.sh/formula/yq) |
| `ripgrep` | infra / active | Confirmed | HBF `ripgrep` | macOS arm64/x86_64 | [ripgrep](https://formulae.brew.sh/formula/ripgrep) |
| `fd` | infra / active | Confirmed | HBF `fd` | macOS arm64/x86_64 | [fd](https://formulae.brew.sh/formula/fd) |
| `just` | infra / active | Confirmed | HBF `just` | macOS arm64/x86_64 | [just](https://formulae.brew.sh/formula/just) |
| `shellcheck` | infra / active | Confirmed | HBF `shellcheck` | macOS arm64/x86_64 | [ShellCheck](https://formulae.brew.sh/formula/shellcheck) |
| `actionlint` | infra / active | Confirmed | HBF `actionlint` | ShellCheck dependency delegated to Homebrew | [actionlint](https://formulae.brew.sh/formula/actionlint) |
| `claude` | coding-agents / active | Confirmed | SPECIAL Anthropic native installer/self-update; bounded vendor paths | Account; product access/plan may apply | [Claude Code](https://github.com/anthropics/claude-code) |
| `copilot` | coding-agents / active | Confirmed | SPECIAL NPM `@github/copilot` in aiup prefix | Node 22+; GitHub account and Copilot plan/policy | [GitHub Copilot CLI](https://github.com/github/copilot-cli) |
| `codex` | coding-agents / active | Confirmed | SPECIAL NPM `@openai/codex` in aiup prefix | Node 16+ package floor; OpenAI account/auth | [OpenAI Codex](https://github.com/openai/codex) |
| `antigravity` | coding-agents / active | Confirmed | SPECIAL official `agy` installer; bounded vendor paths | Google account/product availability | [Google Antigravity](https://antigravity.google/) |
| `grok` | coding-agents / active | Confirmed | SPECIAL official installer and `grok update`; remove vendor user paths | xAI account/product access | [Grok Build](https://x.ai/build) |
| `gemini` | coding-agents / active | **Corrected** | SPECIAL NPM `@google/gemini-cli`; prior false sunset removed | **macOS 15+, Node 20+**; Google account or API credentials | [Gemini CLI](https://github.com/google-gemini/gemini-cli) |
| `pi` | coding-agents / active | **Corrected** | SPECIAL NPM `@earendil-works/pi-coding-agent`; old package migration retained | Node 22.19+; provider credentials | [Pi](https://github.com/earendil-works/pi) |
| `kilo` | coding-agents / active | Confirmed | SPECIAL NPM `@kilocode/cli` | macOS arm64/x86_64; account/provider access | [Kilo Code](https://github.com/Kilo-Org/kilocode) |
| `gsd2` | coding-agents / active | **Corrected** | SPECIAL NPM `@opengsd/gsd-pi`; old package migration retained | Node 22.18+; provider credentials | [GSD](https://github.com/open-gsd/gsd-pi) |
| `opencode` | coding-agents / active | **Corrected** | SPECIAL official installer/self-update/remove | macOS arm64/x86_64; provider credentials | [OpenCode](https://github.com/anomalyco/opencode) |
| `hermes` | coding-agents / active | Confirmed | SPECIAL official installer and `hermes update`; bounded vendor paths | Account/provider credentials; optional model downloads | [Hermes Agent](https://github.com/NousResearch/hermes-agent) |
| `omp` | coding-agents / active | **Removed** | No public initial installer existed; self-update alone was not an install contract | Existing binary can remain detected-only | [Oh My Pi](https://pi.dev/) |
| `warp` | coding-agents / active | Confirmed | SPECIAL official installer/self-updating vendor path | Warp account for cloud/agent features | [Warp](https://github.com/warpdotdev/warp) |
| `aider` | coding-agents / active | Confirmed | SPECIAL official installer with uv-based fallback/removal | Python tool; provider credentials | [Aider](https://github.com/Aider-AI/aider) |
| `goose` | coding-agents / active | **Corrected** | SPECIAL prefers HBF `block-goose-cli`, with canonical installer fallback | Provider credentials; canonical project moved organizations | [Goose](https://github.com/aaif-goose/goose) |
| `cursor` | coding-agents / active | Confirmed | SPECIAL official Cursor Agent installer; cask/source migration handled | Cursor account/product terms | [Cursor CLI](https://cursor.com/docs/cli) |
| `qwen` | coding-agents / active | Confirmed | SPECIAL NPM `@qwen-code/qwen-code` | Node 22+; account/API credentials as used | [Qwen Code](https://github.com/QwenLM/qwen-code) |
| `crush` | coding-agents / active | Confirmed | NPM `@charmland/crush` | Provider credentials | [Crush](https://www.npmjs.com/package/@charmland/crush) |
| `amp` | coding-agents / active | Confirmed | INST `https://ampcode.com/install.sh` | Account/product access | [Amp](https://ampcode.com/) |
| `kiro` | coding-agents / active | Confirmed | HBC `kiro-cli` | macOS 11+; AWS Builder ID/account features | [Kiro CLI](https://formulae.brew.sh/cask/kiro-cli) |
| `droid` | coding-agents / active | Confirmed | INST `https://app.factory.ai/cli` | Factory account/product access | [Factory Droid](https://github.com/Factory-AI/factory) |
| `kimi` | coding-agents / active | Confirmed | HBF `kimi-code` | Node delegated by Homebrew; Moonshot account/auth | [Kimi Code](https://formulae.brew.sh/formula/kimi-code) |
| `openclaw` | coding-agents / active | Confirmed | HBF `openclaw-cli` | Node delegated by Homebrew; account/provider setup | [OpenClaw](https://formulae.brew.sh/formula/openclaw-cli) |
| `plandex` | coding-agents / maintenance | **Removed** | Documented installer endpoint could not be validated as available; no unverified managed fallback retained | Existing binary can remain detected-only; repository/release activity was materially stale | [Plandex](https://github.com/plandex-ai/plandex) |
| `cline` | coding-agents / active | Confirmed | NPM `cline` | Account/provider credentials | [Cline](https://www.npmjs.com/package/cline) |
| `continue` | coding-agents / active | **Corrected** | NPM `@continuedev/cli`; false acquisition/sunset claim removed | Node 20+; provider credentials | [Continue CLI](https://www.npmjs.com/package/@continuedev/cli) |
| `pi-acp` | adapters / active | Confirmed | NPM `pi-acp` | Node 20+; Pi/editor integration | [pi-acp](https://www.npmjs.com/package/pi-acp) |
| `llm` | llm-utils / active | Confirmed | HBF `llm` | Python dependency delegated by Homebrew; provider credentials for remote models | [llm](https://formulae.brew.sh/formula/llm) |
| `mods` | llm-utils / archived | Confirmed | HBF `mods` remains available; archived warning retained | Official repository archived; provider credentials | [mods](https://github.com/charmbracelet/mods) |
| `aichat` | llm-utils / active | Confirmed | HBF `aichat` | Provider credentials | [aichat](https://formulae.brew.sh/formula/aichat) |
| `fabric` | llm-utils / active | Confirmed | HBF `fabric-ai` | Provider credentials | [fabric](https://formulae.brew.sh/formula/fabric-ai) |
| `sgpt` | llm-utils / active | Confirmed | UV `shell-gpt` | Python 3.10+; provider credentials | [shell-gpt](https://pypi.org/project/shell-gpt/) |
| `ollama` | local-ai / active | Confirmed | HBF `ollama` | Large model downloads are separate | [Ollama](https://formulae.brew.sh/formula/ollama) |
| `lm-studio` | local-ai / active | Confirmed | HBC `lm-studio` | macOS 12+, Apple Silicon only; large model downloads and license terms | [LM Studio](https://formulae.brew.sh/cask/lm-studio) |
| `jan` | local-ai / active | Confirmed | HBC `jan` | arm64/x86_64; large model downloads separate | [Jan](https://formulae.brew.sh/cask/jan) |
| `gpt4all` | local-ai / maintenance | **Downgraded** | HBC `gpt4all` vendor installer cask | macOS 12+; large models; last official release observed February 2025 | [GPT4All](https://github.com/nomic-ai/gpt4all) |
| `anythingllm` | local-ai / active | Confirmed | HBC `anythingllm` | arm64/x86_64; account/provider/model storage varies | [AnythingLLM](https://formulae.brew.sh/cask/anythingllm) |
| `mlx` | local-ai / active | Confirmed | HBF `mlx` | Apple Silicon only | [MLX](https://formulae.brew.sh/formula/mlx) |
| `mlx-lm` | local-ai / active | Confirmed | HBF `mlx-lm` | Apple Silicon; depends on MLX; large model downloads separate | [MLX LM](https://formulae.brew.sh/formula/mlx-lm) |
| `chatgpt` | chat / active | Confirmed | HBC `chatgpt` | macOS 13+; account; feature/plan availability varies | [ChatGPT](https://formulae.brew.sh/cask/chatgpt) |
| `claude-app` | chat / active | Confirmed | HBC `claude` | macOS 12+; account; plan limits vary | [Claude desktop](https://formulae.brew.sh/cask/claude) |
| `copilot-app` | chat / active | Confirmed | HBC `github-copilot-app` | GitHub account and Copilot eligibility/plan | [GitHub Copilot app](https://formulae.brew.sh/cask/github-copilot-app) |
| `perplexity` | chat / active | Confirmed | HBC `perplexity` | macOS 15+; account/plan features | [Perplexity](https://formulae.brew.sh/cask/perplexity) |
| `vscode` | editors / active | Confirmed | HBC `visual-studio-code` | arm64/x86_64 | [Visual Studio Code](https://formulae.brew.sh/cask/visual-studio-code) |
| `vscode-insiders` | editors / active | Confirmed | HBC `visual-studio-code@insiders` | macOS 12+; prerelease channel | [VS Code Insiders](https://formulae.brew.sh/cask/visual-studio-code@insiders) |
| `cursor-ide` | editors / active | Confirmed | HBC `cursor` | macOS 12+; account/product access | [Cursor](https://formulae.brew.sh/cask/cursor) |
| `zed` | editors / active | Confirmed | HBC `zed` | arm64/x86_64; account optional/features vary | [Zed](https://formulae.brew.sh/cask/zed) |
| `antigravity-ide` | editors / active | Confirmed | HBC `antigravity-ide` | macOS 12+; Google account/product access | [Antigravity IDE](https://formulae.brew.sh/cask/antigravity-ide) |
| `t3-code` | workspaces / active | Confirmed | HBC `t3-code` | macOS 12+; external agent credentials/subscriptions | [T3 Code](https://formulae.brew.sh/cask/t3-code) |
| `t3-nightly` | workspaces / active | Confirmed | HBC `t3-code@nightly` | macOS 12+; nightly/pre-release channel | [T3 Code Nightly](https://formulae.brew.sh/cask/t3-code@nightly) |
| `grokbot` | workspaces / active | Confirmed | HBC `grok-bot` | macOS 12+; xAI account/product access | [Grok Bot](https://formulae.brew.sh/cask/grok-bot) |
| `opencode-desktop` | workspaces / active | Confirmed | HBC `opencode-desktop` | macOS 12+; provider credentials | [OpenCode desktop](https://formulae.brew.sh/cask/opencode-desktop) |
| `hermes-desktop` | workspaces / active | Confirmed | HBC `hermes-desktop` | macOS 11+; cask does not declare auto-update; provider/model requirements vary | [Hermes Desktop](https://formulae.brew.sh/cask/hermes-desktop) |
| `cmux` | terminals / active | Confirmed | HBC `cmux` | macOS 14+ | [cmux](https://formulae.brew.sh/cask/cmux) |
| `warp-app` | terminals / active | Confirmed | HBC `warp` | macOS 11+; account for cloud/agent features | [Warp](https://formulae.brew.sh/cask/warp) |
| `ghostty` | terminals / active | Confirmed | HBC `ghostty` | macOS 13+ | [Ghostty](https://formulae.brew.sh/cask/ghostty) |
| `iterm2` | terminals / active | Confirmed | HBC `iterm2` | macOS 12+ | [iTerm2](https://formulae.brew.sh/cask/iterm2) |
| `ollama-app` | local-ai / active | Confirmed | HBC `ollama-app` | macOS 14+; large model downloads separate | [Ollama app](https://formulae.brew.sh/cask/ollama-app) |
| `macwhisper` | local-ai / active | Confirmed | HBC `macwhisper` | macOS 14+; vendor license tiers; model downloads | [MacWhisper](https://formulae.brew.sh/cask/macwhisper) |
| `screenpipe` | local-ai / active | Confirmed | APP official stable metadata/DMG; bundle version; exact app-bundle removal | macOS arm64/x86_64; large capture storage; account/provider features vary | [screenpipe](https://github.com/screenpipe/screenpipe) |
| `n8n` | workspaces / active | **Corrected** | **NPM `n8n`**; nonexistent Homebrew formula contract removed | Node 24+; account/auth varies by integrations; server/data footprint | [n8n](https://www.npmjs.com/package/n8n) |
| `interpreter` | coding-agents / active | Confirmed | UV `open-interpreter` | Python 3.9+; provider credentials; computer-control permissions | [Open Interpreter](https://pypi.org/project/open-interpreter/) |
| `vibe` | coding-agents / active | Confirmed | UV `mistral-vibe` | Python 3.12+; Mistral/provider account | [Mistral Vibe](https://pypi.org/project/mistral-vibe/) |
| `llama-cpp` | local-ai / active | Confirmed | HBF `llama.cpp` | macOS arm64/x86_64; model files are separate/large | [llama.cpp](https://formulae.brew.sh/formula/llama.cpp) |
| `llama-app` | local-ai / active | Confirmed | HBC `llama-app` | macOS 15+, Apple Silicon only; large model downloads | [Llama app](https://formulae.brew.sh/cask/llama-app) |
| `whisper-cpp` | local-ai / active | Confirmed | HBF `whisper-cpp` | Model files are separate/large | [whisper.cpp](https://formulae.brew.sh/formula/whisper-cpp) |
| `openhands` | coding-agents / sunset | Confirmed | UV `openhands`, retained only for legacy compatibility | Python exactly 3.12 in package metadata; official CLI repository says not actively maintained and points to Agent Canvas | [OpenHands CLI](https://github.com/OpenHands/OpenHands-CLI) |

## Material corrections

- Gemini CLI and Continue CLI are active upstream products. The prior sunset/acquisition language was unsupported and removed.
- `n8n` has no current Homebrew formula in official metadata. Its managed contract now uses the official `n8n` npm package.
- Pi, GSD, OpenCode, and Goose now use their canonical current repository organizations/URLs. Goose's official installer URL moved with the repository.
- GPT4All remains available as a Homebrew cask but is labeled maintenance-only because the latest official release observed during this audit was from February 2025.
- `omp` and Plandex no longer appear as managed actions. aiup will not call a self-updater without an initial installer or retain an installer endpoint it could not validate.
- Homebrew adoption language now states the operation aiup controls: aiup does not pass `--zap` or directly delete `~/Library`. It no longer promises that every vendor/Homebrew path preserves every setting.

## Limitations and maintenance risks

- This is a **2026-08-25 snapshot**, not a perpetual guarantee. Registry versions, macOS floors, cask artifacts, repository ownership, authentication, pricing, and vendor installers can change without an aiup release.
- Homebrew metadata is authoritative for the formula/cask contract aiup invokes, but a vendor may impose additional account, regional, licensing, hardware, or runtime requirements after installation.
- Version detection is package-record based for Homebrew/npm/uv entries and CLI/app-metadata based elsewhere. A vendor CLI that changes or removes `--version` can degrade to presence evidence until the adapter is updated.
- Homebrew casks that auto-update internally or use vendor installer packages may not offer a simple upstream version comparison. aiup delegates their lifecycle to Homebrew and does not claim to govern vendor-internal data behavior.
- Local-model and desktop products may require downloads far larger than the installer; aiup does not download model files merely by auditing or listing them.
- No authenticated product flows, paid entitlements, first-run onboarding, or real software mutations were exercised. Those remain vendor/user acceptance lanes, separate from this source-and-metadata audit.

Future catalog maintenance should rerun the primary-source checks, the executable contract report, generated-surface synchronization, and misleading-claim scan together. Unverifiable entries should be weakened or removed, not carried forward on reputation.
