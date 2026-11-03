# Linux | aiup

aiup on Linux is new. So far it has run on Arch Linux; other distros are untried. It is a Python program (`runtime/aiup/`) that reads the same catalog as the macOS version, with Linux install targets from `catalog/platforms.tsv`. [docs/cross-platform-design.md](../docs/cross-platform-design.md) has the design. `aiup help` lists the commands.

## What you need

- Python 3.9 or newer. The installer looks for `AIUP_PYTHON`, then `python3`, then `python3.15` down to `python3.9`.
- fzf 0.73.0 or newer for the picker and menus. Without it, or with an older one, `aiup list` prints a plain table instead (`aiup list --plain`), and `aiup only fzf` installs it.
- curl for the installer, and HTTPS access to `raw.githubusercontent.com`.

If Python or fzf is missing, the installer shows the package-manager command it would run (apt-get, dnf, zypper or pacman, with sudo) and asks `[y/N]`. It runs the command, shown on screen, only when you answer yes. With no terminal to ask on, it says the command was not run. A missing fzf doesn't stop the install.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/travisjneuman/aiup/main/linux/install-aiup | sh
```

Options go after `sh -s --`, for example `| sh -s -- --system`.

The installer:

1. Downloads the launcher over HTTPS, with a 1 MiB cap. It checks the first line, the launcher markers, and that Python can compile it.
2. Saves it as `${XDG_DATA_HOME:-~/.local/share}/aiup/launcher/aiup_launcher.py` (mode 600).
3. Writes the `aiup` command to `~/.local/bin/aiup` (mode 700). It's a small sh script that records which Python to use. If `~/.local/bin/aiup` already exists and wasn't made by this installer, it's moved aside to `aiup.aiup-backup-<time>` first.
4. Adds `~/.local/bin` to PATH (see below), then tells you how to use aiup in the terminal you have open.

The installer refuses to run as root. Set `AIUP_ALLOW_ROOT=1` for containers where that's all you have.

Environment variables:

| Variable | What it does |
| --- | --- |
| `AIUP_PYTHON=/path/to/python3` | Use this Python. The `aiup` command honors it at run time too. |
| `AIUP_NO_MODIFY_PATH=1` | Leave shell startup files alone. aiup prints the lines to add instead. |
| `AIUP_ALLOW_ROOT=1` | Allow installing and running as root. |

## PATH

The installer adds one marked block, `# >>> aiup PATH >>>` to `# <<< aiup PATH <<<`, to each of these. Running it again doesn't add a second one.

| File | When |
| --- | --- |
| `~/.profile` | Always (created if missing). |
| `~/.bash_profile`, or else `~/.bash_login` | When one of them exists, since bash then skips `~/.profile` for login shells. |
| `~/.bashrc` | When bash is installed. The block goes at the top, before any early return for non-interactive shells. |
| `~/.zshenv` | When your login shell is zsh or zsh is installed. |
| `~/.config/fish/conf.d/aiup.fish` | When fish is installed or `~/.config/fish` exists. |
| `~/.config/environment.d/60-aiup.conf` | When you're in a systemd user session, so graphical apps see it too. |

New terminals pick it up. In the terminal you installed from, run `export PATH="$HOME/.local/bin:$PATH"` (the installer prints this when it's needed).

## One-off ssh commands: `--system`

Some distros build bash so that a command like `ssh host aiup check` reads no startup file at all, and `~/.local/bin` isn't on PATH there. If that happens, run the installer again with `--system`:

```sh
curl -fsSL https://raw.githubusercontent.com/travisjneuman/aiup/main/linux/install-aiup | sh -s -- --system
```

This adds a shared copy in `/usr/local/bin/aiup`, which is already on PATH everywhere. It shows the three commands first, then runs them with sudo:

```sh
sudo install -d -m 755 /usr/local/lib/aiup
sudo install -m 644 <launcher> /usr/local/lib/aiup/aiup_launcher.py
sudo install -m 755 <generated shim> /usr/local/bin/aiup
```

Without a terminal it uses `sudo -n`, so it works only when sudo needs no password. It warns you if the Python it found is inside your home folder, because other users can't run that one. It won't replace a `/usr/local/bin/aiup` it didn't make. aiup itself still runs as whoever types it, with that person's own state. The shared launcher only changes when you run the installer with `--system` again.

## Uninstall

```sh
curl -fsSL https://raw.githubusercontent.com/travisjneuman/aiup/main/linux/install-aiup | sh -s -- --uninstall
```

This removes the PATH blocks, `~/.local/bin/aiup` (only if this installer made it) and the launcher. If the launcher can't remove the blocks, the installer removes them itself and keeps a `.aiup-backup-<time>` copy of each file it changes. Add `--system` to remove the shared copy in `/usr/local/bin` too (with sudo, shown first).

Your settings, history and downloads stay. The installer prints the `rm -rf` lines for each folder it kept, so you can remove them yourself. It doesn't uninstall any tools aiup installed.

## Privileges

aiup runs as you. It uses sudo only for the system package managers (pacman, an AUR helper's pacman calls, apt, dnf, zypper and snap) and never stores, pipes or caches a password: sudo asks for it in the terminal itself. A user-level manager that asks for sudo is refused.

When you pick an action yourself (`aiup only`, `install`, `remove`, `system`, or the picker), the sudo step runs in front of you. During a plain `aiup` update run, privileged steps follow `aiup settings system`: `report` never runs them, `ask` (the default) needs one yes in a terminal, and `auto` runs them. With no terminal, sudo runs as `sudo -n`, and a step that would need a password is reported as `deferred` with "needs sudo; run aiup in a terminal".

For AUR updates, `aiup settings aur review` (the default) shows the build script and asks first. `aiup settings aur trust` updates AUR packages you already have without asking.

## Where state lives

| What | Where |
| --- | --- |
| Settings (`preferences.json`, `channels.tsv`) | `${XDG_CONFIG_HOME:-~/.config}/aiup` |
| Releases, launcher, npm prefix | `${XDG_DATA_HOME:-~/.local/share}/aiup` |
| Logs and run history | `${XDG_STATE_HOME:-~/.local/state}/aiup` |
| Indexes, downloads, release notes | `${XDG_CACHE_HOME:-~/.cache}/aiup` |
| Picker sessions | `$XDG_RUNTIME_DIR/aiup` when it's yours with mode 700, otherwise `${XDG_CACHE_HOME:-~/.cache}/aiup/run` |

`AIUP_STATE_DIR=/some/dir` puts all of them under that folder instead (`config`, `data`, `state`, `cache`, `run`). XDG values that aren't absolute paths are ignored. aiup makes its folders mode 700 and refuses state paths that are symlinks. [docs/privacy.md](../docs/privacy.md) lists what each file holds.

## How aiup updates itself

`aiup` runs a small launcher, and the launcher runs a published release. Every run it fetches `main/macos/release` (4 KiB at most, about 10 seconds at worst), the same release pointer the macOS version uses. Its first line names a version and a commit.

When that commit is new, the launcher downloads `runtime/FILES` from it, then each file it lists, with size limits. It checks every size and SHA-256, compiles every Python file and checks that the versions agree before it switches over. Each release goes in its own folder under `${XDG_DATA_HOME:-~/.local/share}/aiup/generations/`. The switch happens under a lock, and `current-generation` names the one in use. The current release and anything less than a day old are kept; older ones are removed.

If GitHub can't be reached, or a download doesn't check out, the launcher says why and runs the release you already have. A release on disk that fails its check is downloaded again. Only a first run with nothing installed stops when offline.

For development, `AIUP_SOURCE_PATH=/path/to/aiup/runtime/aiup_main.py aiup version` runs a checkout instead of the published release.
