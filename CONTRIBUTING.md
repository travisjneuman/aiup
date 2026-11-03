# Contributing to aiup

aiup accepts focused fixes, documentation improvements, and evidence-backed catalog/tool requests for the current macOS implementation and for the new Linux and Windows runtime in `runtime/` (first real runs in progress). Tagged releases, packaged installers, CI architecture, and broad redesigns need separate project decisions before implementation.

## Before opening a pull request

1. Open or reference an issue when the change alters catalog lifecycle behavior, adds a tool, or changes an installer/remover contract.
2. Keep `macos/catalog/manifest.tsv` as the source of truth for catalog presentation, lifecycle, and macOS package targets. Keep tool-specific macOS execution adapters in `macos/aiup`. Linux and Windows install targets go in `catalog/platforms.tsv`, and aliases, command names and data paths in `catalog/tool-meta.tsv`. [docs/cross-platform-design.md](docs/cross-platform-design.md) is the build contract for `runtime/`.
3. Treat unknown local detections as detected-only until an update/removal contract is reviewed.
4. Never add telemetry, upload local inventory, pass Homebrew `--zap`, or promise universal settings preservation. On macOS, never invoke `sudo` directly. On Linux, use sudo only for the system package managers and let sudo ask for the password itself. On Windows, never elevate silently.
5. Preserve exact-path, preview-first, confirmation-gated, Trash-recoverable behavior for app-bundle cleanup.
6. Do not silently add or trust a new Homebrew tap. An already installed tap represents prior user approval; a missing required tap must prompt before addition.

## Refresh facts and review the change

For a catalog source change, perform the real text refresh and review its diff:

```bash
scripts/sync-public-docs --skip-media
git diff
```

This writes public outputs. It is not a check, test, or dry run. Report what
actually ran and keep evidence separate from source-review conclusions.

When catalog producer inputs change, run `scripts/sync-public-docs --skip-media` once after edits finish and include its generated outputs, especially `showcase.json`, in the same commit. Review the diff instead of running another export just to check it. The default invocation also copies accepted canonical media; neither invocation generates media. Count-bearing social images need a separately authorized media task. See [public catalog facts](docs/public-catalog-facts.md). The project validates changes by review. Please describe what you reviewed in your pull request.

## Pull requests

Keep the diff scoped and explain behavior, safety boundaries, validation, and any known limitations. Do not include personal paths, machine names, credentials, private logs, local inventory, or unrelated formatting changes.

For a bug, use the [bug report form](https://github.com/travisjneuman/aiup/issues/new?template=bug.yml). For a catalog candidate, use the [catalog/tool request form](https://github.com/travisjneuman/aiup/issues/new?template=catalog-tool.yml). Security vulnerabilities follow [`SECURITY.md`](SECURITY.md), not public issues.

## Catalog admission and coverage quality

Before adding a managed tool, supply its official source, plain-language purpose, most appropriate category, supported OS/architecture, and installation owner. Review detection, version evidence, update, removal, app-close behavior and dependencies together. Detection alone is not an updater contract. Mark unsupported operations as manual or unavailable; never imply full lifecycle support from a name match. Avoid duplicate aliases for the same installation and distinguish project packages from global tools. Keep runtime/manifest versions paired and regenerate public catalog files with `scripts/sync-public-docs`. Add a focused check only when a concrete adapter issue warrants one.

The catalog carries only maintained software. Remove an entry when its project is archived, declared unmaintained or end of life, or has shipped no release and no code change for more than a year; name a maintained successor when one exists. Prefer the channel that publishes new releases first when it is also official (for example a vendor's npm package over a Homebrew repackaging that trails it), and record the channel's live release source in `live_source_spec` when the tool does not install through Homebrew.

Application cleanup must preserve ambiguous metadata, moved app identities and partially present multi-app installations. Keep destructive app-data purge separate from finishing an already-removed app's Homebrew uninstall. Ownership observations are local evidence, not permission to migrate or remove installations.

## Releases (maintainers)

Public launchers run only the commit named in `macos/release`, so pushing to `main` does not ship anything by itself. To release:

1. Run `scripts/bump-version YYYY.MM.DD-NN`. It sets the four versions that must agree: `AIUP_VERSION` in `macos/aiup`, the `# aiup-runtime-version:` lines in `macos/catalog/manifest.tsv` and `catalog/platforms.tsv`, and `runtime/aiup/version.py`. Never edit them by hand.
2. Move CHANGELOG Unreleased under the new version, and update `docs/status.md`.
3. Run `scripts/stamp-runtime` to rewrite `runtime/FILES`, the file list the Linux and Windows launchers check. Never edit it by hand.
4. Commit and push.
5. Run `scripts/publish-release`. It reads the pushed `origin/main`, not the working tree. It stops if the versions disagree, if `runtime/FILES` names another version, if a listed file is missing or has the wrong size or SHA-256, or if a `.py` file under `runtime/aiup/` is not listed. Otherwise it writes `<version> <commit>` to `macos/release`.
6. Commit and push `macos/release`. Launchers on all three systems pick it up within the raw CDN's five-minute cache.

To roll back, point `macos/release` at an earlier release commit and push.
