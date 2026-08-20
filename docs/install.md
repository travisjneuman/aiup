# Install

aiup is a bash script. There is no installer package yet.

## macOS

```bash
mkdir -p ~/.local/bin
curl -fsSL https://raw.githubusercontent.com/travisjneuman/aiup/main/macos/aiup -o ~/.local/bin/aiup
chmod +x ~/.local/bin/aiup
```

Put `~/.local/bin` on your `PATH` if it is not already:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then:

```bash
aiup version
aiup list
```

## What aiup needs

| Need | Why | If missing |
|---|---|---|
| bash | The script | macOS ships it |
| python3 | Path helpers | macOS ships it |
| curl | Vendor installers | macOS ships it |
| fzf | Full-screen catalog | Numbered prompts work without it. `brew install fzf` is nicer |
| Homebrew | Only for brew-managed catalog items and extras | Optional until you install those items |
| npm / Node | Only for Node-based agents | aiup can install Homebrew Node when a tool needs it |
| uv | Only for uv-managed tools (shell-gpt, Open Interpreter) | Installed on demand |

aiup never uses `sudo`. It writes to your home directory (`~/.local/bin`, `~/.local/share/aiup`).

## First run

`aiup` with no arguments **scans the machine** and updates what it finds. It will not install tools you do not have.

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
