# Catalog research review

This is the review log for expanding aiup's managed catalog. The catalog is deliberately split into two evidence lanes:

- **Managed** entries have an official macOS installation/update path that aiup can execute and validate.
- **Detected** entries are discovered from the local Mac but remain read-only until their owning distribution method is reviewed.

aiup does not turn a repository name into an updater automatically. A new managed entry must have a stable identifier, category, lifecycle, official documentation, dependency declaration, installer/updater, and remover. Package-manager entries inherit dependency resolution from Homebrew, npm, or uv; aiup does not attempt to reproduce those package managers' dependency solvers.

## Added in the 2026-08-21 review

| Entry | Decision | Install/update path | Evidence |
|---|---|---|---|
| `vibe` | Managed, active | `uv tool install/upgrade mistral-vibe` | [Mistral Vibe repository](https://github.com/mistralai/mistral-vibe) documents both the macOS installer and `uv tool install mistral-vibe`. |
| `llama-cpp` | Managed, active | Homebrew formula `llama.cpp` | [llama.cpp install guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md) documents `brew install llama.cpp`; Homebrew publishes the formula and its dependencies. |
| `llama-app` | Managed, active | Homebrew cask `llama-app` | [Homebrew's Llama cask](https://formulae.brew.sh/cask/llama-app) identifies the official `ggml-org/Llama-macOS` menu-bar app and its macOS/Apple Silicon requirements. |
| `openhands` | Managed, sunset | `uv tool install/upgrade openhands` for legacy compatibility | [OpenHands CLI repository](https://github.com/OpenHands/OpenHands-CLI) says the CLI is no longer actively maintained and directs users toward Agent Canvas. aiup exposes it with a sunset warning rather than presenting it as a current recommendation. |
| `bun`, `pnpm` | Managed, active | Homebrew formulae `bun` and `pnpm` | [Bun](https://formulae.brew.sh/formula/bun) and [pnpm](https://formulae.brew.sh/formula/pnpm) publish macOS bottles and package-manager install commands. Homebrew resolves pnpm's Node dependency. |
| `jq`, `yq` | Managed, active | Homebrew formulae `jq` and `yq` | [jq](https://formulae.brew.sh/formula/jq) and [yq](https://formulae.brew.sh/formula/yq) are official Homebrew formulae for structured-data work used by development tooling. |
| `ripgrep`, `fd`, `just` | Managed, active | Homebrew formulae `ripgrep`, `fd`, and `just` | [ripgrep](https://formulae.brew.sh/formula/ripgrep), [fd](https://formulae.brew.sh/formula/fd), and [just](https://formulae.brew.sh/formula/just) publish macOS bottles and stable upgrade paths. |
| `shellcheck`, `actionlint` | Managed, active | Homebrew formulae `shellcheck` and `actionlint` | [ShellCheck](https://formulae.brew.sh/formula/shellcheck) and [actionlint](https://formulae.brew.sh/formula/actionlint) provide shell and GitHub Actions validation. actionlint declares ShellCheck as a dependency, which Homebrew resolves. |
| `whisper-cpp` | Managed, active | Homebrew formula `whisper-cpp` | [Homebrew's whisper-cpp formula](https://formulae.brew.sh/formula/whisper-cpp) supplies a macOS bottle and points to the official [whisper.cpp](https://github.com/ggml-org/whisper.cpp) project. Model files remain a separate user choice and are not downloaded by aiup. |

## Confirmed existing coverage

- Amazon Q Developer's command-line documentation now says that the Q CLI has become the Kiro CLI, so aiup's `kiro` entry is the current managed representation rather than adding a stale `amazon-q` duplicate. See [AWS's upgrade note](https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/upgrade-to-kiro.html).
- GitHub Copilot CLI is already represented by `copilot`; its official repository documents macOS support, the official installer, Homebrew formula, and npm package. See [GitHub Copilot CLI](https://github.com/github/copilot-cli).
- `whisper.cpp` is now managed through Homebrew's `whisper-cpp` formula. aiup updates the engine and leaves model-file selection/download to the user; it does not silently fetch large model weights. See [whisper.cpp](https://github.com/ggml-org/whisper.cpp) and [the formula](https://formulae.brew.sh/formula/whisper-cpp).

## Review rules for future additions

1. Prefer the vendor's official installer or an official Homebrew/npm/uv distribution.
2. Verify macOS architecture and minimum OS requirements before adding an entry.
3. Prefer package-manager updates when the package manager owns dependency closure.
4. Reject entries whose only practical path is an unreviewed source clone, an arbitrary third-party script, or a destructive replacement.
5. Mark products sunset, archived, or maintenance-mode when primary sources show that status.
6. Keep research candidates in this document until the update/remove contract is complete; local discovery still makes installed candidates visible immediately.
