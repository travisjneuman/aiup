# Install

aiup is a bash script. There is no installer package yet.

## macOS

```bash
mkdir -p ~/.local/bin
curl -fsSL https://raw.githubusercontent.com/travisjneuman/aiup/main/macos/aiup-launcher -o ~/.local/bin/aiup
chmod +x ~/.local/bin/aiup
```

Put `~/.local/bin` on your `PATH` if it is not already:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then:

```bash
aiup version
aiup only fzf
aiup list
```

## What aiup needs

| Need | Why | If missing |
|---|---|---|
| bash | The script | macOS ships it |
| python3 | Path helpers | macOS ships it |
| curl | Vendor installers | macOS ships it |
| fzf | Required full-screen catalog and infrastructure tool | aiup installs/updates the Homebrew formula |
| Homebrew | Required for fzf and brew-managed catalog items | aiup installs it before fzf when missing |
| npm / Node | Only for Node-based agents | aiup can install Homebrew Node when a tool needs it |
| uv | Only for uv-managed tools (shell-gpt, Open Interpreter) | Installed on demand |

aiup does not invoke `sudo` itself. Homebrew's official installer may request macOS administrator authentication. aiup writes its own files to your home directory (`~/.local/bin`, `~/.local/share/aiup`).

## Live public version

The installed `aiup` command is a small launcher. On this machine, every invocation first runs the canonical `~/web-dev/aiup/macos/aiup` checkout directly, so no network access is needed and local changes are immediately testable. Set `AIUP_SOURCE_PATH` to another checkout's `macos/aiup` script when needed.

For users without a local checkout, the launcher falls back to fetching the public `main/macos/aiup` runtime and caches it under `~/.local/share/aiup/aiup-live`. If that fallback fetch fails, aiup stops instead of silently running older cached code. `./macos/aiup` runs the copy in a local checkout.

Update runs are unattended: Homebrew confirmations are accepted automatically, and version checks receive no terminal input. Explicit uninstall and on-disk app-switch confirmations still require your approval.

## First run

`aiup` with no arguments first ensures required infrastructure (currently fzf), then **scans the machine** and updates what it finds. It will not install optional tools you do not have.

```bash
aiup              # update whatever is already installed
aiup list         # browse, install, remove
aiup only grok    # install or update one tool
aiup doctor       # how each catalog item was detected
```

## Uninstall aiup

```bash
rm ~/.local/bin/aiup
rm -rf ~/.local/share/aiup
```

That does not uninstall the coding agents themselves.
