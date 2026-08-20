# Homebrew

Homebrew is how many catalog items land on a Mac. It is not the whole catalog.

## Tap trust

Before its first Homebrew operation, aiup checks installed taps using Homebrew's trust metadata. A tap already installed on the Mac represents prior user approval: if Homebrew marks it untrusted, aiup shows its remote and automatically runs `brew trust --tap` without asking again. This applies to the installed tap itself, not to any tap that aiup would newly add.

If a future catalog item requires a tap that is not installed, its installer must identify that tap and ask before adding and trusting it. aiup never silently adds or trusts a newly introduced tap.

## Child lists

| Child | What you see |
|---|---|
| **casks** | GUI apps Homebrew already installed on your Mac (minus main-catalog items) |
| **fonts** | `font-*` casks already installed |
| **formulae** | CLI formulae already installed (not classified as libraries) |
| **libraries** | Libraries Homebrew already installed |
| **recommended** | A short popular list that is not already a Homebrew install |

casks / fonts / formulae / libraries are **inventory of your Mac**. They are not a search of everything Homebrew ships. Opening Homebrew will still show thousands of other packages.

**recommended** is the list that can show things you don't have yet.

## installed · on disk · absent

The same product can exist as a Homebrew cask *and* as a drag-installed / App Store / vendor `.app`. Those are one app.

| State | Meaning |
|---|---|
| **installed** | Homebrew owns this formula or cask |
| **on disk** | The app or command is on your Mac some other way |
| **absent** | Not found via Homebrew *or* the app/PATH check (recommended only) |

## Switch to Homebrew without losing settings

On an **on disk** row, press enter.

For apps:

1. Confirm.
2. `brew install --cask --adopt` — Homebrew tracks the existing `.app` when it matches.
3. If versions differ, only the app bundle is replaced (`brew install --cask --force`). Notes, vaults, preferences, and everything under `~/Library` stay. aiup never passes `--zap`.

For command-line tools already on PATH:

- Homebrew's copy is installed **alongside**
- The original command (including macOS `/usr/bin`) is not uninstalled

Uninstall from aiup only removes Homebrew-managed installs. A drag-installed app is left for you to remove in Finder.

## What a scan reads

- `brew list --cask` / `brew list --formula`
- `/Applications` and `~/Applications`
- `command -v` for recommended formulae
