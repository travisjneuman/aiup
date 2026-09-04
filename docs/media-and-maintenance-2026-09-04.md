# Media, categories, and maintenance — 2026-09-04

Runtime/catalog: `2026.09.04-04`. This extends the [previous efficiency review](maintenance-and-performance-2026-09-04.md).

## Category review

All 82 prior managed entries were reviewed by primary user purpose. Four additions bring the total to 86. The complete per-item assignment is generated in [catalog.md](catalog.md).

| Category | Decision |
|---|---|
| media | Remotion first; move MacWhisper and whisper.cpp from local-ai. Add DiffusionBee and Upscayl for AI image work, FFmpeg and Audacity as explicitly labeled supporting utilities. |
| automation | Move Hermes, OpenClaw, Open Interpreter, Grok Bot, and n8n here. Their primary scope extends beyond coding or desktop agent hubs. |
| dev-utils | Move GitHub CLI, Wrangler, jq, yq, ripgrep, fd, just, ShellCheck, and actionlint out of infrastructure. |
| infra | Keep required package/runtime tooling: Homebrew, Node/npm, uv, fzf, Deno, Bun, pnpm. |
| coding-agents | Retain coding-first terminal agents; lifecycle labels remain unchanged. |
| workspaces | Retain desktop clients/hubs for coding/agent work, including Hermes Desktop. |
| editors / terminals / chat | Retain primary editing, shell-hosting, and cloud conversational apps. |
| local-ai | Retain local inference/models/chat and Screenpipe's contextual screen/audio capture. Capture for contextual memory is distinct from media production. |
| llm-utils / adapters | Retain pipe-oriented language-model tools and editor/agent integration glue. |
| homebrew / detected | Preserve inventory source groupings and explicit management boundaries. These are not speculative catalog contracts. |

Remotion itself is React video tooling, not an AI model. Media intentionally accommodates AI workflows and their supporting tools. No cloud subscriptions or browser-only services were presented as installed apps; no media tools or models were installed by this change.

## Implemented behavior

- Read-only `check` takes one Homebrew installed-info snapshot for uncached selected packages, distributes independent checks across the existing bounded worker count (default two, maximum three), and emits results in the requested order. Fresh failures never reuse old cache as proof of current. Mutations remain serialized and revalidated.
- `--timings` exposes inventory/version/provider phases and per-tool update phases. Individual external operations log elapsed seconds; result/history JSON stores per-tool duration. No universal speed multiplier is claimed.
- Search matches only names, package aliases and descriptions. Exact IDs rank first; then aliases, name prefixes, name substrings and descriptive matches. Multiple query words use AND matching; status/category text is excluded. Category navigation returns on an empty query. The existing protected session helper performs ranking.
- `coverage` gives a compact summary (`--all` expands all rows), including categories, installed management boundaries, Homebrew extras, and detected-only adapter candidates. It never claims detection grants a safe update contract.
- `doctor` surfaces PATH shadowing, broken links among inspected installed tools, duplicate npm prefixes/app copies, and saved setup warnings. `doctor --details` retains the prior complete detection view and no longer reconciles shell profiles.
- Local JSON preferences support exclusions, inclusive dated holds, and named groups. Writes are locked/atomic, malformed data blocks updates, and no shell code is evaluated. CLI checks, picker previews, bulk eligibility, and fresh mutation checks honor policies. Force does not override holds. Missing held infrastructure prevents dependent updates.
- `retry` selects only failures from the latest inactive structured run, resolves current catalog IDs, and uses normal update logic. Successful rows are not replayed. Retry can reinstall a failed absent tool; explicit `--no-install` preserves the no-install boundary. In-progress/unrecorded operations require inspection rather than guessing whether to repeat them. Required fzf infrastructure retains its normal handling.
- `project DIRECTORY` is explicit, read-only package.json inspection. It displays declared npm ranges, not resolved installed versions or available updates. It executes no project scripts and recursively scans no repositories.
- Typed package targets are now canonical manifest data; dedicated migration aliases stay in runtime adapters. The public launcher remains a two-file paired distribution.

## Source evidence

Public official Homebrew pages read through built-in web/API on TJNMPM, 2026-09-04. Capture succeeded; no authenticated read, browser, fallback, or external mutation. This verifies packaging/documentation, not an actual vendor install/render or owner acceptance.

- [DiffusionBee](https://formulae.brew.sh/cask/diffusionbee): cask `diffusionbee`, `/Applications/DiffusionBee.app`.
- [Upscayl](https://formulae.brew.sh/cask/upscayl): cask `upscayl`, `/Applications/Upscayl.app`.
- [FFmpeg](https://formulae.brew.sh/formula/ffmpeg): formula `ffmpeg`.
- [Audacity](https://formulae.brew.sh/cask/audacity): cask `audacity`, `/Applications/Audacity.app`.

## Evidence and recovery

Focused existing maintenance/report checks passed; dedicated preference/search/retry checks passed. Live read-only `check remotion fzf --refresh --timings` reported both current in approximately 7.5 seconds on this device (not a comparative benchmark). The first protected picker run was invalidated by a concurrent task-owned runtime edit; the fixed-runtime rerun passed the existing dynamic Updates checks (including synthetic failures and bulk-update boundaries).

No live package upgrade, model download, render, broad benchmark campaign, new CI, or new provider resource was used. Source changes roll back by Git revert. Preference changes reverse through include/unhold/group remove; user preferences and logs remain local and are not removed by a source rollback. Owner visual acceptance and real vendor installation remain separate evidence lanes.
