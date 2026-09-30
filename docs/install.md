# Install

aiup is a macOS Bash application with a small launcher that runs the latest published release. There is no packaged macOS artifact; the helper below installs the launcher.

## Supported configuration and prerequisites

The current public support baseline is macOS 14 Sonoma or newer on Apple Silicon or 64-bit Intel. This follows the supported Homebrew baseline because fzf is required and managed through Homebrew.

Before installing, verify the three bootstrap commands that aiup cannot install for itself:

```bash
command -v bash
command -v curl
command -v python3
bash --version
python3 --version
```

aiup requires Bash 3 or newer, curl, and a working Python 3. Do not assume those commands exist merely because the machine runs macOS. If any is missing, install or restore it first through Apple or the upstream project; the curl-based command below cannot bootstrap a missing shell, downloader, or Python runtime.

Homebrew and fzf do not need to be present before installation. When a selected action first needs them, aiup uses Homebrew's official installer and then the fzf formula. A supported Homebrew configuration requires current Xcode Command Line Tools; install them first with `xcode-select --install` if `xcode-select -p` fails. Homebrew's installer may request administrator authentication even though aiup does not call `sudo` directly.

## Install and persist PATH

```bash
curl -fsSL https://raw.githubusercontent.com/travisjneuman/aiup/main/macos/install-aiup | bash
export PATH="$HOME/.local/bin:$PATH"
```

The small installer downloads the launcher to a size-bounded temporary file beside the destination, verifies non-empty content, the expected shebang and launcher markers, and Bash syntax, sets mode `700`, then atomically replaces `~/.local/bin/aiup`. A failed, empty, invalid, or partial download leaves an existing launcher unchanged. It adds one marked PATH block to `~/.zprofile`; repeated installs do not duplicate it. The `export` activates the path in the current session. If you deliberately use another login shell, add `$HOME/.local/bin` through that shell's supported profile mechanism instead.

## First run

```bash
aiup version
aiup only fzf
aiup list
```

`aiup only fzf` is the explicit bootstrap action for Homebrew and the required picker. `aiup` with no arguments then scans the machine and updates installed catalog tools; it does not install other optional tools that are absent.

```bash
aiup              # refresh aiup, then update whatever is already installed
aiup list         # refresh aiup, then browse/install/remove
aiup only grok    # refresh aiup, then install or update one selected tool
aiup doctor       # refresh aiup, then show local detection details
```

Normal update/install subprocesses are unattended, including Homebrew's package confirmations. The initial Homebrew bootstrap is the exception: aiup starts Homebrew's official installer in an interactive terminal so it can request confirmation and any administrator authentication. A Homebrew tap already installed on the Mac is treated as prior user approval and trusted automatically. A missing tap required by a selected tool still prompts before it is added. Explicit uninstall and on-disk app-switch confirmations also require approval.

## Online, offline, and local development behavior

For a normal public installation, each invocation first fetches the release pointer, `main/macos/release`, from `raw.githubusercontent.com` (at most 4 KB, 10 seconds). Its first non-comment line is `<version> <commit>`. The launcher then fetches `macos/aiup` and `macos/catalog/manifest.tsv` at exactly that commit. Content addressed by a commit is immutable, so the runtime and catalog always come from the same published release, and changes that land on `main` between releases never reach public installs. When the pointer names the release already installed, the launcher runs it without downloading anything.

A new release is validated (script shape, Bash syntax, manifest structure, and matching versions, including the version named by the pointer) before it is staged under `~/.local/share/aiup/generations/`. Downloads and hidden `.staging-*` directories may overlap, but generation finalization, pointer replacement, and retention cleanup share one Bash 3-compatible activation lock. A live lock is never reclaimed; a lock whose recorded process no longer exists is recovered through an exact aiup-owned reaper path.

One atomically replaced `current-generation` pointer selects a complete validated pair, and `previous-generation` records the former pair. Retention keeps the current and previous generations plus any generation less than a day old, because an open picker may still re-run it. Older generations are removed only when they contain nothing but aiup's own files; unfamiliar contents are left in place. Hidden temporary files and staging directories that an interrupted launch left behind are removed after an hour.

If the pointer cannot be fetched, or a new release fails to download or validate, the launcher prints the reason and runs the last validated release, so aiup keeps working offline. The installed release is revalidated on every run; if it is damaged, the launcher downloads it again. Only a first run with no validated release stops when GitHub is unreachable. Install and update actions may still need Homebrew or vendor access.

Local repository development is an explicit opt-in and is the only supported offline launcher path:

```bash
AIUP_SOURCE_PATH="/path/to/your/aiup/macos/aiup" aiup version
```

`AIUP_SOURCE_PATH` is used only when deliberately set to a non-empty file path. The launcher never guesses or probes a checkout. A missing or invalid explicit source fails instead of silently falling back to the published release. Running `./macos/aiup` from a checkout is equivalent and uses that checkout's adjacent catalog manifest.

## Uninstall aiup

These commands remove the launcher, aiup-owned state, and the marked PATH blocks. They do not uninstall catalog tools or remove unrelated files:

```bash
rm -f ~/.local/bin/aiup
rm -rf ~/.local/share/aiup
for profile in ~/.zprofile ~/.zshrc; do
  [ -f "$profile" ] || continue
  sed -i '' '/# >>> aiup PATH >>>/,/# <<< aiup PATH <<</d' "$profile"
done
```
