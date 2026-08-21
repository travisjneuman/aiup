# Contributing

Default use is local. You do not need to fork, sign in, or run an AI.

If you add tools or categories:

1. Add the stable id and descriptive metadata to `macos/catalog/manifest.tsv`. For package-managed entries, put the package target in the optional seventh field; keep only binary aliases and tool-specific installer/remover adapters in `macos/aiup` as the execution layer. The manifest is the presentation, lifecycle, and package-target source of truth.
2. Run `scripts/sync-public-docs` so README, `docs/catalog.md`, and `site/catalog.json` match the script.
3. Keep catalog ids stable.
4. Never add telemetry. Never `sudo`.
5. Detect PATH, app bundles, npm, uv, *and* package managers — Homebrew is not the only way an app exists. Unknown local detections are detected-only until their update/removal contract is reviewed. App-bundle cleanup must remain exact-path, preview-first, confirmation-gated, and recoverable via Trash.
6. Every catalog entry must have a complete updater/install path and a remover. Dedicated app updaters must verify the vendor artifact before replacing the bundle.
7. Switching an existing app to Homebrew must keep settings (`--adopt`, never `--zap`).
8. An installed Homebrew tap represents prior user approval, so aiup must trust it automatically without prompting. If a required tap is not installed, aiup must prompt before adding and trusting it. Never silently add or trust a newly introduced tap.

The Homebrew `available` view is intentionally dynamic: it reads formulae and casks from the user's installed taps instead of maintaining a second hardcoded package list.
