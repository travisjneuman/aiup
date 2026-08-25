# Install

aiup is a macOS Bash application with a small live launcher. There is no package installer or tagged release yet.

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
mkdir -p ~/.local/bin
curl -fsSL https://raw.githubusercontent.com/travisjneuman/aiup/main/macos/aiup-launcher -o ~/.local/bin/aiup
chmod +x ~/.local/bin/aiup
touch ~/.zprofile
grep -Fq '# >>> aiup PATH >>>' ~/.zprofile || printf '\n# >>> aiup PATH >>>\nexport PATH="$HOME/.local/bin:$PATH"\n# <<< aiup PATH <<<\n' >> ~/.zprofile
export PATH="$HOME/.local/bin:$PATH"
```

The profile block makes `aiup` available to future sessions using macOS's default zsh login shell; the `export` activates it in the current session. If you deliberately use another login shell, add `$HOME/.local/bin` through that shell's supported profile mechanism instead.

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

For a normal public installation, every invocation downloads both `main/macos/aiup` and `main/macos/catalog/manifest.tsv` from `raw.githubusercontent.com`. The launcher validates the script, manifest structure, and matching version before activating them as `~/.local/share/aiup/aiup-live` and `~/.local/share/aiup/catalog/manifest.tsv`.

If the runtime or manifest is unavailable, empty, invalid, mismatched, or cannot be activated, the command stops. A previous cache is retained for recovery evidence but is not executed as an offline fallback. Normal public use therefore requires GitHub access at the start of every run; later install/update actions may need Homebrew or vendor access too.

Local repository development is an explicit opt-in and is the only supported offline launcher path:

```bash
AIUP_SOURCE_PATH="/path/to/your/aiup/macos/aiup" aiup version
```

`AIUP_SOURCE_PATH` is used only when deliberately set to a non-empty file path. The launcher never guesses or probes a checkout. A missing or invalid explicit source fails instead of silently falling back to the network. Running `./macos/aiup` from a checkout is equivalent and uses that checkout's adjacent catalog manifest.

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
