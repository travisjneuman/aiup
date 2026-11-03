# Windows | aiup

aiup on Windows is new in this release, and first real runs are in progress. It is a Python program (`runtime/aiup/`) that reads the same catalog as the macOS version, with Windows install targets from `catalog/platforms.tsv`. [docs/cross-platform-design.md](../docs/cross-platform-design.md) has the design. `aiup help` lists the commands.

## What you need

- Windows PowerShell 5.1 or PowerShell 7 to run the installer.
- Python 3.9 or newer. The installer looks for `AIUP_PYTHON`, then `py -3`, then `python.exe` and `python3.exe` on PATH, then the usual install folders under `%LOCALAPPDATA%\Programs\Python`, `%LOCALAPPDATA%\Python` (the Python install manager) and `%ProgramFiles%`. It skips the Microsoft Store placeholder in `WindowsApps`.
- fzf 0.73.0 or newer for the picker and menus. Without it, or with an older one, `aiup list` prints a plain table instead (`aiup list --plain`), and `aiup only fzf` installs it.

If Python is missing, the installer asks `Install Python from winget now? [y/N]` and, on yes, runs `winget install --id Python.Python.3.14 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements` (`--scope machine` with `-AllUsers`), shown on screen. With no console to ask on, it prints the command instead. Without winget, it also points you to the python.org download page. fzf works the same way with `junegunn.fzf` for your account, and the install carries on without it. `scoop install fzf` works too. If winget can't start, or runs longer than 15 minutes for Python or 5 for fzf, the installer stops it and says so.

## Install

```powershell
irm https://raw.githubusercontent.com/travisjneuman/aiup/main/windows/install-aiup.ps1 | iex
```

This works under the default execution policy, because nothing runs from a script file. To pass an option, run it as a script block:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/travisjneuman/aiup/main/windows/install-aiup.ps1))) -Uninstall
```

Or save the file and run `powershell -NoProfile -ExecutionPolicy Bypass -File install-aiup.ps1 [-Uninstall] [-AllUsers]`.

The installer downloads the launcher over HTTPS, with a 1 MiB cap, and checks the first line, the launcher markers and that Python can compile it. Then it writes these to `%LOCALAPPDATA%\Programs\aiup`:

| File | What it is |
| --- | --- |
| `launcher\aiup_launcher.py` | The launcher. |
| `bin\aiup.cmd` | The command for cmd and PowerShell. It records which Python to use. |
| `bin\aiup.ps1` | Written only when every PowerShell on the computer allows local scripts (RemoteSigned, Unrestricted or Bypass). PowerShell then uses it and you don't get "Terminate batch job (Y/N)?" after Ctrl-C. Otherwise PowerShell uses `aiup.cmd`, and the installer says so. |
| `bin\aiup` | An sh script for Git Bash and MSYS. |

A file already there that this installer didn't make is moved aside first.

Environment variables:

| Variable | What it does |
| --- | --- |
| `AIUP_PYTHON=C:\path\to\python.exe` | Use this Python (3.9 or newer). |
| `AIUP_NO_MODIFY_PATH=1` | Leave PATH alone. The installer prints the folder to add yourself. |

## PATH

The installer adds the `bin` folder to your user PATH (the `Path` value under `HKCU\Environment`) and to the PowerShell window you ran it from. aiup records the user PATH entries it adds in `%LOCALAPPDATA%\aiup\data\path-entries.txt`. Uninstalling takes the `bin` folder back out of PATH and leaves the rest of PATH alone.

The window you installed from can run `aiup` right away. Open a new terminal anywhere else. Programs that were already open keep their old PATH until you restart them.

## Every account: `-AllUsers`

Run the installer from an elevated terminal (Run as administrator) with `-AllUsers`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File install-aiup.ps1 -AllUsers
```

This installs to `%ProgramFiles%\aiup` and adds its `bin` folder to the machine PATH. Without an elevated terminal it stops with "-AllUsers needs an elevated terminal (Run as administrator). The installer never elevates itself." It warns you if the Python it found is inside your user folder, because other accounts can't run that one. An elevated terminal without `-AllUsers` still installs for your account only. Each person who runs aiup keeps their own state.

## Uninstall

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/travisjneuman/aiup/main/windows/install-aiup.ps1))) -Uninstall
```

Add `-AllUsers` (from an elevated terminal) to remove an every-account install. This removes the PATH entry, the commands in `bin` that this installer made, and the launcher. Your settings, history and downloads stay. The installer prints a `Remove-Item -Recurse -Force -LiteralPath` line for each folder it kept, so you can remove them yourself. It doesn't uninstall any tools aiup installed.

## Privileges

aiup runs as you and never elevates itself silently.

- Steps that may show a UAC prompt (winget packages that install for every account, and `winget upgrade --all`) run only from a terminal on the desktop you're using, so you see Windows ask, or when aiup already runs elevated. Over ssh, or with no terminal, they're reported as `deferred` with "needs Windows approval; run aiup in a desktop terminal".
- winget can't run in some sessions, such as ssh on Windows Server. aiup then lists winget as unavailable and carries on with the other managers. If a winget read stops answering, aiup waits for its time limit once, then skips winget for the rest of that run.
- Steps that need an elevated terminal, such as Chocolatey, run only when aiup is already running elevated. Otherwise they're `deferred` with "Run from an elevated terminal:" and the command.
- During a plain `aiup` update run, system-wide steps follow `aiup settings system`: `report` never runs them, `ask` (the default) needs one yes in a terminal, and `auto` runs them. Actions you pick yourself (`aiup only`, `install`, `remove`, `system`, or the picker) run them in front of you.

aiup never stores a password, and it never uses sudo on Windows. When it runs elevated, it says so: user-level tools still install for that account, and a normal terminal is enough for everyday runs.

## Where state lives

| What | Where |
| --- | --- |
| Settings (`preferences.json`, `channels.tsv`) | `%LOCALAPPDATA%\aiup\config` |
| Releases, launcher, npm prefix | `%LOCALAPPDATA%\aiup\data` |
| Logs and run history | `%LOCALAPPDATA%\aiup\state` |
| Indexes, downloads, release notes | `%LOCALAPPDATA%\aiup\cache` |
| Picker sessions | `%LOCALAPPDATA%\aiup\cache\run` |

`AIUP_STATE_DIR=C:\some\dir` puts all of them under that folder instead (`config`, `data`, `state`, `cache`, `run`). [docs/privacy.md](../docs/privacy.md) lists what each file holds.

## How aiup updates itself

`aiup` runs a small launcher, and the launcher runs a published release. Every run it fetches `main/macos/release` (4 KiB at most, 10 seconds), the same release pointer the macOS version uses. Its first line names a version and a commit.

When that commit is new, the launcher downloads `runtime/FILES` from it, then each file it lists, with size limits. It checks every size and SHA-256, compiles every Python file and checks that the versions agree before it switches over. Each release goes in its own folder under `%LOCALAPPDATA%\aiup\data\generations`. The switch happens under a lock, and `current-generation` names the one in use. The current release and anything less than a day old are kept; older ones are removed.

If GitHub can't be reached, or a download doesn't check out, the launcher says why and runs the release you already have. A release on disk that fails its check is downloaded again. Only a first run with nothing installed stops when offline.

For development, set `AIUP_SOURCE_PATH` to a checkout's `runtime\aiup_main.py` to run it instead of the published release.
