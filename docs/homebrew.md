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

## Switch to Homebrew without requesting a data zap

On an **on disk** row, press enter.

For apps:

1. Confirm.
2. `brew install --cask --adopt` — Homebrew tracks the existing `.app` when it matches.
3. If versions differ, aiup asks Homebrew to replace the app bundle with `brew install --cask --force` and does not pass `--zap` or directly delete `~/Library`. Homebrew and vendor installer behavior can still be app-specific, so this is not a universal guarantee about every product's settings.

For command-line tools already on PATH:

- Homebrew's copy is installed **alongside**
- The original command (including macOS `/usr/bin`) is not uninstalled

Uninstall from aiup only removes Homebrew-managed installs. A drag-installed app is left for you to remove in Finder.

## Apps that update themselves

Many apps (Homebrew marks them `auto_updates`) update in place, so the app bundle moves ahead of the version Homebrew recorded at install time. For these casks and for catalog app casks, aiup reads the installed bundle's `CFBundleShortVersionString` (or `CFBundleVersion`) and compares it with the cask version:

- **App at or past Homebrew's version:** reported as `current (self-updated)` with the app's own version. aiup skips the Homebrew download and never installs an older build over a newer one.
- **App older than Homebrew's version:** Homebrew upgrades it as the backstop.

Homebrew keeps the Caskroom record at the version it installed and offers no supported way to reconcile that record without reinstalling, so aiup leaves it unchanged; `aiup explain <tool>` shows both the app version and the record.

## Open apps are never replaced

`brew upgrade` quits a running app before replacing it. aiup checks for any process running from inside the app bundle first and, if the app is open, reports the update as `deferred`: quit the app, then run `aiup resume` (or `aiup retry`). `aiup check`, `aiup plan` and `aiup explain` say when an open app is holding an update.

## What a scan reads

- `brew list --cask` / `brew list --formula`
- `/Applications` and `~/Applications`
- `command -v` for recommended formulae
