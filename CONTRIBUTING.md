# Contributing to aiup

aiup accepts focused fixes, documentation improvements, and evidence-backed catalog/tool requests for the current macOS implementation. Linux, Windows, tagged releases, packaged installers, CI architecture, and broad redesigns need separate project decisions before implementation.

## Before opening a pull request

1. Open or reference an issue when the change alters catalog lifecycle behavior, adds a tool, or changes an installer/remover contract.
2. Keep `macos/catalog/manifest.tsv` as the source of truth for catalog presentation, lifecycle, and package targets. Keep tool-specific execution adapters in `macos/aiup`.
3. Treat unknown local detections as detected-only until an update/removal contract is reviewed.
4. Never add telemetry, upload local inventory, invoke `sudo` directly, pass Homebrew `--zap`, or promise universal settings preservation.
5. Preserve exact-path, preview-first, confirmation-gated, Trash-recoverable behavior for app-bundle cleanup.
6. Do not silently add or trust a new Homebrew tap. An already installed tap represents prior user approval; a missing required tap must prompt before addition.

## Validate the change

Run the narrowest relevant checks and report exactly what ran:

```bash
scripts/sync-public-docs
scripts/check-catalog-contracts
scripts/check-site
scripts/capture-media --check
scripts/build-brand-assets --check
scripts/test-aiup-launcher
scripts/test-aiup
git diff --check
```

Run `scripts/sync-public-docs` twice when generated catalog facts change and confirm the second run is clean. Do not regenerate accepted media or brand assets unless the issue explicitly requires and reviews that work.

## Pull requests

Keep the diff scoped and explain behavior, safety boundaries, validation, and any known limitations. Do not include personal paths, machine names, credentials, private logs, local inventory, or unrelated formatting changes.

For a bug, use the [bug report form](https://github.com/travisjneuman/aiup/issues/new?template=bug.yml). For a catalog candidate, use the [catalog/tool request form](https://github.com/travisjneuman/aiup/issues/new?template=catalog-tool.yml). Security vulnerabilities follow [`SECURITY.md`](SECURITY.md), not public issues.
