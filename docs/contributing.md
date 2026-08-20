# Contributing

Default use is local. You do not need to fork, sign in, or run an AI.

If you add tools or categories:

1. Edit `macos/aiup` (`TOOLS_CATALOG`, `catalog_category`, `catalog_label`, install/remove).
2. Run `scripts/sync-public-docs` so README, `docs/catalog.md`, and `site/catalog.json` match the script.
3. Keep catalog ids stable.
4. Never add telemetry. Never `sudo`.
5. Detect PATH, app bundles, *and* package managers — Homebrew is not the only way an app exists.
6. Every catalog entry must have a complete updater/install path and a remover. Dedicated app updaters must verify the vendor artifact before replacing the bundle.
7. Switching an existing app to Homebrew must keep settings (`--adopt`, never `--zap`).
8. If Homebrew reports an installed tap as untrusted, aiup must prompt before trusting it. Never silently trust a newly added tap.
