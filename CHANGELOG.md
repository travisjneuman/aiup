# Changelog

## 2026.08.23-01

- Official app updaters can declare a metadata endpoint template; Screenpipe now checks its official Tauri update manifest before downloading a DMG and refuses unverified fallback downloads.
- `pi-acp` now reports its npm package version even when its CLI emits no `--version` output, and removing Pi explicitly explains that the independently installed ACP adapter remains.
- Default update results distinguish current tools and skipped unmanaged apps from completed updates.

## 2026.08.21-02

- The interactive catalog now supports left/right category collapse/expand and Page Up/Page Down jumps between category rows.

## 2026.08.21-01

- `aiup list` now caches catalog/Homebrew ownership lookups during inventory scanning, so the fzf picker opens promptly even when many Homebrew packages are installed.

## 2026.08.20-25

- Homebrew taps already installed on a Mac are treated as prior user approval and trusted automatically; missing taps required by a selected tool still prompt before they are added and trusted.

## 2026.08.20-24

- Screenpipe now updates from the official architecture-specific stable DMG, verifies the bundle identity, code signature, and Gatekeeper assessment, preserves a rollback copy, and relaunches only when it was running.
- Installed untrusted Homebrew taps are displayed with their remote and automatically trusted as prior user-approved taps; newly required taps still require approval before they are added.
- Catalog validation now fails closed when an entry lacks its installer metadata, updater, remover, label, category, or documentation URL.

## 2026.08.20-23

- Update/install runs are now unattended: Homebrew receives `--yes`, child processes receive no terminal input, and duplicate Homebrew refreshes are skipped.
- Version summaries close stdin so terminal-oriented tools such as `pi-acp` cannot block aiup; unsupported downloaded apps are skipped during the default scan.

## 2026.08.20-22

- Installed `aiup` now uses the canonical local `~/web-dev/aiup/macos/aiup` checkout first, so local testing needs no GitHub access and sees unpublished local changes immediately. GitHub remains a fallback for installations without a local checkout.

## 2026.08.20-21

- Installed `aiup` now uses a live-sync launcher that fetches and validates the current public `main` runtime on every invocation, failing closed when it cannot refresh.

## 2026.08.20-20

- fzf is required infrastructure, managed as a Homebrew formula and refreshed during update runs.

## 2026.08.20-19

- Tab title is `aiup`. Favicon at `/favicon.ico`.

## 2026.08.20-18

- Open Graph and Twitter large image, JSON-LD, sitemap, robots.txt.

## 2026.08.20-17

- Site uses the official lockup and brand colors.

## 2026.08.20-16

- Public site is the product page. Install and how-to live in the repo.

## 2026.08.20-11

- Enter on an **on disk** app lets Homebrew manage it. Settings stay. Never `--zap`.
- Command-line tools already on PATH get a Homebrew copy alongside.

## 2026.08.20-10

- First public release.
