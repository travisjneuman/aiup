# Changelog

## 2026.08.20-14

- Site rebuilt from the Grok `frontend-design` skill: the page is the catalog (expandable rows from `catalog.json`), not a dark-mode marketing template.

## 2026.08.20-13

- Site redesign: product layout, no CRT overlay, no emoji section headers. Catalog still loaded from `catalog.json`.

## 2026.08.20-12

- Site is Cloudflare Pages from `site/`. No GitHub Actions. No GitHub Pages.

## 2026.08.20-11

- Enter on an **on disk** app lets Homebrew manage it. Settings, notes, and `~/Library` stay (`--adopt`, then replace the `.app` only if versions differ). Never `--zap`.
- Command-line tools already on PATH get a Homebrew copy alongside; the original is not deleted.
- `aiup catalog` / `aiup catalog --markdown` export the catalog definition (no machine scan). `scripts/sync-public-docs` refreshes README, docs, and the site from that export.

## 2026.08.20-10

- First public repository: macOS script, README, site, local-only scan.
- Homebrew extras can show **on disk** when the same app exists outside Homebrew.
- Child Homebrew lists are this Mac's inventory; recommended is the short add-list.

Earlier macOS history lived in a private working copy before this public repository.
