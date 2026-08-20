# Contributing

Default use is local and private. You do not need to fork, sign in, or run an AI.

If you **do** fork to add tools or port Linux/Windows:

1. Keep catalog ids stable (`grok`, `hermes-desktop`, `mlx-lm`, …).
2. Never add telemetry.
3. Never `sudo`.
4. Detect installs via PATH, app bundles, and package managers — not by assuming Homebrew is the only way an app exists.
5. Document new tools in `docs/catalog.md`.

macOS implementation: `macos/aiup` (bash).
