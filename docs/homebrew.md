# Homebrew

Homebrew is how many catalog items land on a Mac. It is not the whole catalog.

## Tap trust

Before its first Homebrew operation, aiup checks installed taps using Homebrew's trust metadata. A tap already installed on the Mac represents prior user approval: if Homebrew marks it untrusted, aiup shows its remote and automatically runs `brew trust --tap` without asking again. This applies to the installed tap itself, not to any tap that aiup would newly add.

When a catalog item needs a tap that is not installed, aiup shows the tap's remote and asks before it adds it (`brew tap`) and trusts it (`brew trust --tap`). It never silently adds or trusts a new tap. Without a terminal to ask in, the install stops with a message.

Some catalog items come from taps run by their own publishers, for example `stacklok/tap/thv`, `docker/tap/sbx`, `mozilla-ai/tap/cq` and `microsoft/foundrylocal/foundrylocal`. Three taps live in repositories that are not named `homebrew-*`, so aiup adds them from their GitHub address: `jundot/omlx`, `vllm-project/vllm-metal` and `ddalcu/mlx-serve`. When a name exists as both a formula and a cask (`mlx-serve`), aiup passes `--formula` or `--cask` so Homebrew installs the right one. When a package is already installed, aiup skips the per-package tap lookup before upgrading it and only reviews the installed taps.

## Downloads and cleanup

Before the first Homebrew upgrade in a run, aiup downloads every outdated formula and cask it is about to upgrade with one `brew fetch`, so `HOMEBREW_DOWNLOAD_CONCURRENCY` can download them in parallel. Casks whose app is open, apps that updated themselves and held or excluded tools are left out. The upgrades still run one tool at a time and reuse the downloads. `AIUP_BREW_PREFETCH=0` turns this off.

While Homebrew upgrades run, plain npm tools and uv tools update in two background lanes. Tools that only touch Homebrew keep running in the foreground beside them; any other tool waits until the lanes finish. Node and uv update first, before the lanes start, so the lane tools install with the new versions. If Homebrew still has to upgrade Node or a formula it needs (such as icu4c), the npm lane is not started. If it still has to upgrade uv, a Python, or a formula they need (such as openssl), the uv lane is not started. Those tools then run one at a time as usual, so no tool is installed with a runtime that is being replaced. `AIUP_PARALLEL=0` runs everything one at a time.

After an update run, aiup runs `brew cleanup --prune=all -s`, then deletes the downloaded bottles and installers Homebrew keeps for the installed versions, and the dangling links they leave. Homebrew's package metadata (`api/`) stays, so the next check does not download it again. The cleanup also removes the older installed versions of upgraded formulae and casks, so only the current one stays on disk. The cleanup is skipped while another `brew` is running. `AIUP_CLEANUP_CACHES=0` keeps the downloads.

## Bottle attestations

Homebrew can check that each bottle was built by Homebrew's own build service, using a signed attestation stored on GitHub. That check needs the GitHub CLI (`gh`) signed in. When `gh` is installed and `gh auth status` succeeds, aiup turns the check on for the run (`HOMEBREW_VERIFY_ATTESTATIONS=1`). Without `gh` or a sign-in it stays off, because Homebrew would otherwise try to install `gh` by itself. Set `AIUP_BREW_ATTESTATIONS=0` to keep it off, or set `HOMEBREW_VERIFY_ATTESTATIONS` yourself and aiup leaves your setting alone.

## How current Homebrew's answer is

Homebrew answers "is there a newer version?" from a local copy of its package metadata. aiup's read-only paths run Homebrew with auto-update off, so that copy could otherwise be days old. Before `aiup check` or the picker's update preview asks Homebrew, aiup refreshes the copy with Homebrew's own fast `brew update --auto-update` when it is older than 15 minutes. If you set `HOMEBREW_NO_AUTO_UPDATE`, aiup leaves it alone.

aiup reports the version Homebrew can install, which can trail the vendor's own release by a few hours or days while Homebrew packages it. Tools that aiup installs outside Homebrew are compared with their vendor's release channel instead.

That lag is why many tools default to npm, PyPI or their own installer, with Homebrew as an alternate. `aiup channel TOOL brew` moves a tool to Homebrew if you prefer it there, and `aiup channel TOOL default` moves it back. The next `aiup only TOOL` makes the switch and removes the old copy. To put every tool that Homebrew has on Homebrew, run `aiup channel --policy brew`; `aiup channel --policy keep` leaves each tool where it is installed now, and `aiup channel --policy newest` goes back to the default. A per-tool pick always wins over the policy.

Update candidates include auto-updating casks (aiup then compares the installed app, so a self-updated app is not downgraded) but not unversioned `:latest` casks, which would otherwise reinstall on every run. If Homebrew's metadata for an app cask cannot be read during an update run, the upgrade is deferred so it never runs unchecked; `aiup resume` picks it up.

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

## installed · on disk · not installed

The same product can exist as a Homebrew cask *and* as a drag-installed / App Store / vendor `.app`. Those are one app.

| State | Meaning |
|---|---|
| **installed** | Homebrew owns this formula or cask |
| **on disk** | The app or command is on your Mac some other way |
| **not installed** | Not found via Homebrew *or* the app/PATH check (recommended and available only) |

## Switch to Homebrew without requesting a data zap

On an **on disk** row, press enter.

For apps:

1. Confirm.
2. `brew install --cask --adopt`: Homebrew tracks the existing `.app` when it matches.
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
