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

## Catalog admission and coverage quality

Before adding a managed tool, supply its official source, plain-language purpose, most appropriate category, supported OS/architecture, and installation owner. Review detection, version evidence, update, removal, app-close behavior and dependencies together. Detection alone is not an updater contract. Mark unsupported operations as manual or unavailable; never imply full lifecycle support from a name match. Avoid duplicate aliases for the same installation and distinguish project packages from global tools. Keep runtime/manifest versions paired and regenerate public catalog files with `scripts/sync-public-docs`. Add a focused check only when a concrete adapter issue warrants one.

The catalog carries only maintained software. Remove an entry when its project is archived, declared unmaintained or end of life, or has shipped no release and no code change for more than a year; name a maintained successor when one exists. Prefer the channel that publishes new releases first when it is also official (for example a vendor's npm package over a Homebrew repackaging that trails it), and record the channel's live release source in `live_source_spec` when the tool does not install through Homebrew.

Application cleanup must preserve ambiguous metadata, moved app identities and partially present multi-app installations. Keep destructive app-data purge separate from finishing an already-removed app's Homebrew uninstall. Ownership observations are local evidence, not permission to migrate or remove installations.

## Releases (maintainers)

Public launchers run only the commit named in `macos/release`, so pushing to `main` does not ship anything by itself. To release:

1. Bump `AIUP_VERSION` in `macos/aiup` and `# aiup-runtime-version:` in `macos/catalog/manifest.tsv` together, update `CHANGELOG.md` and `docs/status.md`, and push.
2. Run `scripts/publish-release`. It reads the pushed `origin/main`, refuses a runtime/catalog version mismatch, and writes `<version> <commit>` to `macos/release`.
3. Commit and push `macos/release`. Launchers pick it up within the raw CDN's five-minute cache.

To roll back, point `macos/release` at an earlier release commit and push.
