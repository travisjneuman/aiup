# Homebrew in the catalog

Homebrew is infrastructure, not the whole product. The main catalog is a curated list of AI / agent / editor / terminal tools. Under **homebrew** you also see extras that are already on *this* Mac.

## The children are not “all of Homebrew”

If a child says you are missing zero items, Homebrew still has thousands of other formulae. aiup is not a brew browser.

| Child | What it lists | Absent count |
|---|---|---|
| **casks** | GUI apps Homebrew already installed, excluding items in the main catalog | Always empty on purpose |
| **fonts** | `font-*` casks already installed | Always empty on purpose |
| **formulae** | CLI formulae already installed (not treated as libraries) | Always empty on purpose |
| **libraries** | Build/runtime libraries Homebrew already installed | Always empty on purpose |
| **recommended** | A short popular list that is **not** already a Homebrew install | This is the only child that shows absents |

The header `N already on this Mac via Homebrew` means “here is what brew put on this computer,” not “here is everything you could install.”

## Installed vs on disk vs absent

The same product can exist as a Homebrew cask *and* as a drag-installed / App Store / vendor `.app`. Those are **not two different apps**. Detection:

| State | Meaning |
|---|---|
| **installed** | Homebrew owns this formula or cask |
| **on disk** | The app or command is on this Mac some other way (`/Applications/Obsidian.app`, system `curl`, …) |
| **absent** | Not found via Homebrew *or* the app/PATH check (recommended list only) |

Example: Obsidian installed from obsidian.md shows as **on disk** under recommended, not as a missing cask. Enter will **not** `brew install obsidian` on top of it. Uninstall will **not** delete an app aiup did not install through Homebrew.

## Recommended is a shopping list, not inventory

Recommended is a hand-picked set of launchers, note apps, terminals, and CLIs that people in this neighborhood often want. It is not “similar items Homebrew would show you.” Opening Homebrew and searching the same category will still find more.

## What scan uses

- `brew list --cask` / `brew list --formula` for extras already managed by brew
- `/Applications` and `~/Applications` for the recommended casks' `.app` names
- `command -v` for recommended formulae that exist outside brew (including macOS `/usr/bin/curl`)
