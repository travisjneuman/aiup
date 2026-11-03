# Cross-platform runtime design (Linux and Windows) | aiup

Status, 2026-11-03: the Linux and Windows runtime described here is implemented in this repository and ships in the next release. First runs on real Linux and Windows machines are in progress.

This is the build spec for one new aiup runtime for Linux and Windows. It is written in Python 3 (standard library only, Python 3.9 or newer), drives fzf for the TUI the way `macos/aiup` does, and reads one shared catalog with per-platform install targets. macOS keeps its Bash runtime. The new runtime has a `darwin` platform module so it could run on macOS later, but no macOS switch is planned.

Every macOS behavior below is cited by the function in `macos/aiup` (or `macos/aiup-launcher`) that implements it, so workers can read the original before building the equivalent.

Contents:

1. [Goals and fixed decisions](#1-goals-and-fixed-decisions)
2. [Command parity matrix](#2-command-parity-matrix)
3. [Repository layout and how `aiup` reaches PATH](#3-repository-layout-and-how-aiup-reaches-path)
4. [Release contract](#4-release-contract)
5. [Catalog schema](#5-catalog-schema)
6. [Provider model](#6-provider-model)
7. [Privilege policy](#7-privilege-policy)
8. [Detection model](#8-detection-model)
9. [Runtime services: concurrency, state, output, terminal, notifications, Trash](#9-runtime-services)
10. [Work packages](#10-work-packages)
11. [Open questions](#11-open-questions)

---

## 1. Goals and fixed decisions

- One runtime for Linux and Windows: `runtime/aiup/`, Python 3.9+, stdlib only. No pip installs, no vendored third-party code, no compiled helpers.
- fzf is the only required external tool for the TUI, same as macOS (`AIUP_REQUIRED_TOOLS=(fzf)`, `ensure_fzf_for_interactive`).
- One catalog. `macos/catalog/manifest.tsv` stays the base list of ids, categories, lifecycles, labels and docs URLs. A new `catalog/platforms.tsv` adds Linux and Windows install targets. The macOS runtime and launcher never read the new files.
- One release pointer, one release commit, for every platform (section 4). The macOS launcher contract does not change.
- The same commands, flags, exit codes and JSON schemas as macOS wherever the idea carries over. Where it does not, the command says so in one line and names the substitute.
- aiup never stores, pipes or caches a password and never elevates itself silently (section 7).
- No telemetry, no account, no upload of local inventory (same as `docs/privacy.md`).
- Python 3.9 compatibility rules for every worker: put `from __future__ import annotations` at the top of every module; no `match`, no runtime `X | Y` unions, no `tomllib`, no `zip(strict=)`, no `typing.get_type_hints`. Every `open()` passes `encoding="utf-8"` (Windows defaults to the ANSI code page). Every `subprocess` call passes an argv list, never `shell=True`.

---

## 2. Command parity matrix

Legend: **Same** means the behavior and output contract match macOS. **Adapted** means the same command with a platform-specific meaning, described in the row. **macOS only** means the new runtime prints one line, `aiup: <command> is macOS only. <substitute>`, and exits 1 (it is a known command, so 2 is wrong; 2 stays reserved for mistyped input, as `usage_error` does today).

### 2.1 Commands

| Command (macOS source) | Linux | Windows |
| --- | --- | --- |
| `aiup`, `aiup full`, `aiup core` (`cmd_update_installed`) | Adapted. Updates installed catalog tools on user-level channels without prompts. Catalog tools on system channels follow `settings system` (section 7.3). Linuxbrew extras update like Homebrew extras do on macOS (`update_installed_brew_extra`). Never installs missing tools (`NO_INSTALL=1`). | Adapted. Same, with scoop as the user-level extras manager. winget and choco catalog tools follow `settings system`. |
| `aiup list` (`cmd_catalog_browse`, `pick_catalog_tools`) | Same picker, keys and row marks (`row_state_mark`). The `homebrew` pseudo-category becomes `packages` ("Other packages"), filled from every available package manager's inventory. `detected` stays. | Same. `packages` is filled from winget, scoop, choco and Appx inventory. |
| `aiup list --plain`, `--detected`, `--category`, `--view`, `--sort` (`print_list`, `print_inventory_definition`) | Same. `--category` accepts the catalog categories plus `packages`, `packages/<manager>` and `detected` (macOS: `homebrew/casks` and friends). | Same. |
| `aiup check [tools...]` (`cmd_check`) | Same, including release notes (`print_release_notes`) and "Newer on another channel" hints (`print_channel_hints`). Latest versions come from each tool's active channel (section 6). | Same. |
| `aiup plan` (`cmd_plan`) | Same. Steps that need sudo are marked `needs sudo`. | Same. Steps that may raise a UAC prompt are marked `may ask Windows for approval`; choco steps outside an elevated terminal are marked `needs an elevated terminal`. |
| `aiup only <tools...>` (`main_update` with `NO_INSTALL=0`) | Same. Installing a tool on a system channel is an explicit user action, so a visible sudo prompt is allowed. | Same. |
| `aiup install` (`cmd_install_interactive`) | Same. | Same. |
| `aiup remove [tools...]`, `uninstall` (`cmd_remove_named`, `cmd_remove_interactive`, `run_tool_remove`) | Same confirmation flow. User data paths come from `catalog/tool-meta.tsv` (macOS: `tool_user_data_paths`) and go to the freedesktop Trash (section 9.7). | Same. User data goes to the Recycle Bin. |
| `aiup attention`, `owners`, `duplicates` (`cmd_overview`) | Same. `duplicates` walks every PATH entry (`which_all_unique_list`). | Same. PATH lookup honors `PATHEXT`. |
| `aiup resume`, `aiup retry` (`run_history resume|retry`) | Same, reading each tool's newest saved result across retained runs. | Same. |
| `aiup history [tool]`, `aiup logs [tool]` (`run_history`) | Same. `logs` pages through `$PAGER` or `less -FRX` in a terminal; `AIUP_NO_PAGER=1` prints. | Same. Uses `$PAGER` or `less` when one is on PATH (Git for Windows ships `less`); otherwise prints without a pager. |
| `aiup explain <tool>` (`cmd_explain`) | Same: detection, channel, owner, path, version, next action. Adds the distro and whether sudo would be needed. | Same. Adds install scope (user or machine) and whether elevation would be needed. |
| `aiup preview <tool>` (`print_catalog_preview`) | Same. | Same. |
| `aiup docs|home|open <tool>`, `--print` (`cmd_docs`, `open_url`) | Same. Opens with `xdg-open`, then `gio open`. | Same. Opens with `os.startfile`. |
| `aiup doctor [--details]` (`cmd_diagnostics`, `print_doctor`) | Adapted. Adds Python version and path, fzf version check, PATH setup state for each shell, available package managers, AUR helper, sudo availability, root warning. | Adapted. Adds Python path, fzf version, user PATH entry, available managers, elevation state, execution policy, console code page and VT support. |
| `aiup coverage` (`cmd_coverage`) | Same. | Same. |
| `aiup welcome` (`cmd_welcome`) | Same guide. Its cleanup choices (Homebrew removed-app records) are left out. | Same as Linux. |
| `aiup preferences` (`preferences show`) | Same file format (`preferences.json`). | Same. |
| `aiup exclude|include TOOL`, `hold TOOL DATE`, `unhold TOOL` (`preferences`) | Same. Valid ids are catalog ids plus `pkg:<manager>:<name>` package ids (macOS: `bf:`/`bc:` Homebrew ids). | Same. |
| `aiup group set|check|run|remove` (`preferences group-*`) | Same. | Same. |
| `aiup settings cleanup auto|review` (`preferences cleanup`) | Accepted and stored so exports stay portable; it has no effect here and says so. | Same as Linux. |
| `aiup settings system report|ask|auto` | New (section 7.3). | New. |
| `aiup settings aur review|trust` | New (section 7.2). | Not offered; exits 1 with "AUR is Linux only". |
| `aiup channel [TOOL [CHANNEL]]`, `--policy` (`cmd_channel`, `cmd_channel_policy`, `channels_load`, `channels_apply_policy`) | Adapted. Channel names are the provider names in section 6.3. `--policy newest|keep|system|<manager>`. `system` means the distro manager; `brew` is accepted and means Linuxbrew. | Adapted. `--policy newest|keep|winget|scoop|choco`. `system` is accepted and means winget. |
| `aiup export [FILE]`, `aiup import FILE` (`cmd_export`, `cmd_import`) | Same schema `aiup-export-v1` with additive keys (section 9.4). | Same. |
| `aiup notify [--always]` (`cmd_notify`, `notify_path_setup`) | Adapted. Desktop notification through `notify-send`, then `gdbus` (section 9.6). Schedules nothing; docs show a systemd user timer and a crontab line. | Adapted. Toast through Windows PowerShell (section 9.6). Docs show a Task Scheduler entry. |
| `aiup system` | New. Runs the full system upgrade for the distro manager (section 7.3), always with a visible sudo prompt and a `[y/N]` question first. | New. Runs `winget upgrade --all` (UAC prompts are Windows' own) and, only in an elevated terminal, `choco upgrade all`. Asks `[y/N]` first. |
| `aiup cleanup homebrew`, `cleanup bc:<name>`, `cleanup <detected-app-id> [--apply]`, `cleanup history` (`cmd_cleanup`, `cmd_cleanup_homebrew`, `detected_cleanup_paths`) | macOS only. Substitute: `aiup remove TOOL` moves known user data to the Trash. `cleanup history` works (it only reads run history). | Same as Linux. |
| `aiup inventory [--plain|--refresh]` (`print_inventory_definition`) | Same JSON shape, with records from the Linux detection sources (section 8). | Same, Windows sources. |
| `aiup catalog [--json|--markdown]` (`print_catalog_definition`) | Adapted. Adds `--platform linux|windows|all` (default: the current one); each tool carries its targets for that platform. Definition export only: no scan, no state. | Same. |
| `aiup catalog --contracts` (`print_catalog_contracts`) | macOS only. | macOS only. |
| `aiup project DIRECTORY` (`cmd_project`) | Same (reads declared npm dependencies, runs nothing). | Same. |
| `npm-update` | Same shortcut for `aiup only npm`. | Same. |
| `aiup version`, `help`, `-h`, `--help` (`usage`) | Same. Help text names the platform ("keeps the AI and developer tools on this computer current"). | Same. |
| Internal `__fzf-rows`, `__cat-*`, `__enter-action`, `__search-query`, `__fzf-header` (`parse_args`) | Same role, served by `runtime/aiup/tui/fast.py` (section 9.5). | Same. |
| Internal `__tui-test-*` | Not carried over. The new runtime has no test-only commands or test-only environment variables. | Same. |

### 2.2 Flags

All parsed the way `parse_args` does today: global flags may appear anywhere, values are validated before anything runs, and a bad value exits 2 with one line.

| Flag | Linux and Windows meaning |
| --- | --- |
| `--dry-run` | Same. Every provider step is printed, nothing runs, results are `planned`. |
| `--json` | Same scope: update runs, `check`, `group run`, `group check`. Other commands refuse it with exit 2. JSON goes to stdout; everything a person reads goes to stderr (macOS does `exec 6>&1 1>&2`). |
| `--verbose` | Same: stream provider output too. Turns off parallel lanes, as `lanes_enabled` does. |
| `--show-unchanged` | Same. |
| `--force` | Same: run npm, uv and package-manager updates even when versions read as current. Never forces a reinstall through a system manager. |
| `--no-install` | Same. |
| `--plain` | Same: sets `NO_COLOR=1` and keeps status words. |
| `--refresh` | Same: rebuild the inventory; with `check`, ask every release source again. |
| `--heartbeat-seconds N` | Same (`AIUP_HEARTBEAT_SECONDS`). |
| `--category`, `--view`, `--sort` | Same values; see the `list` row for category names. |
| `--timings` | Same: discovery and provider timings on stderr (`profile_mark`). |
| `--print` (docs), `--details` (doctor), `--always` (notify), `--policy` (channel), `--apply` (cleanup, macOS only) | Same. |

### 2.3 Exit status

| Status | Meaning, all platforms |
| --- | --- |
| 0 | Done. For `check`, the check ran. |
| 1 | Something failed, a refused action, or a macOS-only command on another platform. |
| 2 | Mistyped command, option or missing argument. One line: `aiup: unknown command 'chek'. Run aiup help.` |
| 130 | Stopped with Ctrl-C. Finished tools are recorded; the rest are pending for `aiup resume`. On Windows, a console Ctrl-C (`KeyboardInterrupt`) and Ctrl-Break both map to 130. |

### 2.4 Environment variables

| Variable | macOS | Linux and Windows |
| --- | --- | --- |
| `NO_COLOR` | Same. | Same. |
| `FZF_DEFAULT_OPTS` | User colors win over `catalog_fzf_style`. | Same. |
| `PAGER`, `LESS` | `aiup logs`. | Same. |
| `AIUP_NO_PAGER=1` | Print logs without a pager. | Same. |
| `AIUP_CLEANUP_CACHES=0` | Keep download caches (`post_update_cleanup`). | Same for user-level caches (npm, uv, pip, pnpm store). aiup never cleans system caches (no `paccache`, no `apt-get clean`). |
| `AIUP_PARALLEL=0` | No npm/uv lanes. | Same: run every lane in sequence. |
| `AIUP_RELEASE_NOTES=0` | Skip release-note lookups. | Same. |
| `AIUP_NPM_PROVENANCE_CHECK=0` | Skip the npm provenance question (`npm_provenance_gate`). | Same. |
| `AIUP_BREW_ATTESTATIONS=0` | Homebrew bottle attestations (`brew_attestations_setup`). | Linuxbrew only. Ignored on Windows. |
| `AIUP_LOG_LIMIT` | Runs to keep (1 to 100, default 20). | Same. |
| `AIUP_HEARTBEAT_SECONDS` | Progress interval. | Same. |
| `AIUP_CHECK_WORKERS` | Read workers, 2 to 6 (`check_worker_count`). | Same. CPU count from `os.cpu_count()`. |
| `AIUP_INVENTORY_CACHE_TTL`, `AIUP_TUI_CACHE_TTL`, `AIUP_TUI_SESSION_TTL`, `AIUP_AVAILABLE_VERSION_CACHE_TTL`, `AIUP_AVAILABLE_VERSION_FAILURE_TTL`, `AIUP_AVAILABLE_VERSION_PROVIDER_TIMEOUT`, `AIUP_AVAILABLE_VERSION_CACHE_LIMIT`, `AIUP_RUN_PROVIDER_TIMEOUT`, `AIUP_TUI_PREFETCH_WORKERS` | Cache and timeout tuning. | Same names, same defaults and clamps (section 9.1). |
| `AIUP_STATE_DIR` | Root of all state. | If set, every aiup directory goes under it (section 9.2), as on macOS. |
| `AIUP_LOCAL_BIN` | Where vendor installers put commands (`~/.local/bin`). | Same default on Linux. Windows default `%USERPROFILE%\.local\bin` (where several vendor installers, Claude Code's among them, put their commands). |
| `AIUP_NPM_PREFIX` | aiup's own npm prefix. | Same idea (section 6.4). |
| `AIUP_SOURCE_PATH` | Run a checkout's `macos/aiup`. | Run a checkout's `runtime/aiup_main.py` (section 4.6). |
| `AIUP_REPO_RAW`, `AIUP_RELEASE_URL` | Launcher sources. | Same names and defaults. |
| `AIUP_UPSTREAM_URL`, `AIUP_MANIFEST_URL` | Direct two-file mode. | Not supported: the runtime is many files. `AIUP_SOURCE_PATH` covers development. |
| `AIUP_PROFILE` | Same as `--timings`. | Same. |
| `AIUP_PYTHON` | n/a | New. Absolute interpreter path the shims use; set by the installers (section 3.3). |
| `AIUP_ALLOW_ROOT=1` | n/a | New, Linux only. Lets aiup run as root (containers). Default: refuse (section 7.1). |
| `AIUP_ASCII=1` | n/a | New. ASCII row marks and frames for terminals without the glyphs (section 9.5). |
| `AIUP_NO_MODIFY_PATH=1` | n/a | New. Installers and the runtime never edit shell profiles or the user PATH. |

---

## 3. Repository layout and how `aiup` reaches PATH

### 3.1 New and changed files

```
runtime/
  aiup_main.py                 entry script: puts its own folder on sys.path, calls aiup.cli.main
  FILES                        release file list: sha256, size, path (generated, section 4.3)
  README.md                    developer notes for the runtime (no public claims)
  launcher/
    aiup_launcher.py           Linux and Windows launcher, self-contained, also does PATH setup
  aiup/
    __init__.py
    __main__.py                python -m aiup support
    version.py                 AIUP_VERSION = "..." (one line the release scripts edit)
    errors.py                  exit codes, UsageError, PlatformUnsupported
    model.py                   dataclasses in section 6.1
    versions.py                version parsing and comparison (macOS: version_is_greater)
    config.py                  environment variables and their clamps
    paths.py                   Dirs for each platform (section 9.2)
    cli.py                     argument parsing and dispatch (macOS: parse_args)
    catalog/
      __init__.py
      loader.py                reads manifest.tsv, platforms.tsv, categories.tsv, tool-meta.tsv
      targets.py               cell grammar parser (section 5.3)
      export.py                catalog --json / --markdown
    platform/
      __init__.py              current() -> Platform
      base.py                  Platform protocol and shared dataclasses
      linux.py
      windows.py
      darwin.py                minimal, enough for catalog export; not a supported runtime
      proc.py                  run_read, run_step, process tree, kill_tree, output decoding
      term.py                  tty detection, VT mode, UTF-8, colors, glyph set
    providers/
      __init__.py              registry: all_providers(), get(name)
      base.py                  Provider base class and Step/Action types
      _linux.py                shared Linux helpers: LC_ALL=C reads, system and user steps, lock checks, Memo
      _win.py                  shared Windows helpers: unsigned exit codes, PowerShell JSON calls, folders, Memo
      linux_pacman.py  linux_aur.py  linux_apt.py  linux_dnf.py  linux_zypper.py
      linux_flatpak.py  linux_snap.py  linux_nix.py
      brew.py                  Linuxbrew (and a darwin path later)
      win_winget.py  win_scoop.py  win_choco.py  win_appx.py
      npm.py  pnpm.py  bun.py  uv.py  pipx.py  cargo.py  go.py
      vendor.py                self-updaters (claude update and similar)
      script.py                downloaded install scripts (sh/bash, PowerShell)
    engine/
      __init__.py
      context.py               Context passed to providers
      channels.py              channel resolution and policy (section 6.5)
      plan.py                  build a Plan from tools, prefs, holds, channels
      run.py                   execute a Plan: steps, heartbeat, Ctrl-C, results
      lanes.py                 parallel lanes (section 9.1)
      privilege.py             sudo / UAC rules (section 7)
      check.py                 aiup check and aiup plan data
      report.py                human report and JSON (aiup-run-v1, aiup-check-v1)
      history.py               logs, history, retry, resume, attention data
      prefs.py                 preferences.json, channels.tsv, groups, holds, settings
      net.py                   bounded HTTPS fetch, JSON helpers, registry lookups
      cache.py                 TTL caches and atomic writes
      releasenotes.py          release-note lookup and cache
    detect/
      __init__.py
      inventory.py             unified inventory (section 8)
      sources.py               DetectionSource registry; hooks for the research doc
    tui/
      __init__.py
      picker.py                builds and runs fzf (macOS: pick_catalog_tools)
      rows.py                  row and header formatting (format_catalog_display, format_category_header)
      session.py               session snapshot directory and token
      fast.py                  fast helper entry for fzf bindings
      preview.py               preview text (print_catalog_preview)
    commands/
      __init__.py
      update.py  check.py  plan.py  listing.py  remove.py  explain.py  doctor.py
      overview.py  coverage.py  welcome.py  prefs_cmds.py  channel.py  system.py
      exportimport.py  notify.py  docs.py  history_cmds.py  inventory_cmd.py
      catalog_cmd.py  project.py
catalog/
  platforms.tsv                Linux and Windows targets (section 5.2)
  categories.tsv               category id, order, name, emoji, blurb
  tool-meta.tsv                aliases, commands, processes, user data paths
linux/
  install-aiup                 POSIX sh installer
  README.md
windows/
  install-aiup.ps1             Windows PowerShell 5.1 compatible installer, ASCII only
  README.md
scripts/
  bump-version                 new: sets one version in all four places
  stamp-runtime                new: writes runtime/FILES
  publish-release              extended (section 4.4)
  sync-public-docs             extended (section 5.6)
.gitattributes                 new: LF for runtime/**, catalog/**, linux/**, *.py, *.tsv
```

Unchanged: `macos/aiup`, `macos/aiup-launcher`, `macos/install-aiup`, `macos/catalog/manifest.tsv` (apart from the normal version header bump), and the `macos/release` format.

### 3.2 Linux: how the user ends up typing `aiup`

Install command (public, documented in `linux/README.md` and `docs/install.md` once it ships):

```sh
curl -fsSL https://raw.githubusercontent.com/travisjneuman/aiup/main/linux/install-aiup | sh
```

`linux/install-aiup` (POSIX sh, no bashisms, mirrors `macos/install-aiup`):

1. Requires `curl`, `mktemp`, and a Python 3.9+ interpreter. It looks for `$AIUP_PYTHON`, then `python3`, then `python3.13` down to `python3.9` on PATH, and runs each candidate with `-I -c 'import sys; print(sys.version_info[:2] >= (3, 9))'`. If none qualifies it prints the distro command to install Python (from `/etc/os-release` `ID`/`ID_LIKE`: `sudo pacman -S python`, `sudo apt install python3`, `sudo dnf install python3`, `sudo zypper install python3`) and exits 1. It never runs sudo for Python. For a missing fzf on pacman or dnf it asks `Install fzf with sudo? [y/N]` on the terminal and runs the visible `sudo` package install only on yes; elsewhere it points to `aiup only fzf`, because apt and zypper ship fzf older than 0.73.
2. Refuses to run as root unless `AIUP_ALLOW_ROOT=1`.
3. Downloads `main/runtime/launcher/aiup_launcher.py` with the same curl limits as `macos/install-aiup` (HTTPS only, 1 MiB cap) into a temp file beside the destination, then validates: non-empty, first line `#!/usr/bin/env python3`, the markers `AIUP_LAUNCHER_REVISION =`, `AIUP_RELEASE_URL`, `def validate_generation(`, and that the chosen Python can `compile()` it without running it.
4. Installs it to `${XDG_DATA_HOME:-~/.local/share}/aiup/launcher/aiup_launcher.py` (mode 600) by atomic rename.
5. Writes the shim `~/.local/bin/aiup` (mode 700, atomic rename):

   ```sh
   #!/bin/sh
   # aiup shim (generated by install-aiup)
   AIUP_PYTHON="${AIUP_PYTHON:-/usr/bin/python3}"
   [ -x "$AIUP_PYTHON" ] || AIUP_PYTHON="$(command -v python3)"
   exec "$AIUP_PYTHON" -I -B "$HOME/.local/share/aiup/launcher/aiup_launcher.py" "$@"
   ```

   The recorded interpreter is the absolute path found in step 1, so an activated virtualenv or a project `.python-version` never changes which Python runs aiup. The launcher re-checks the version on every start.
6. Runs `"$AIUP_PYTHON" -I -B aiup_launcher.py setup-path ~/.local/bin` unless `AIUP_NO_MODIFY_PATH=1`. PATH setup lives in the launcher so the shell installer, the PowerShell installer and the runtime share one implementation.

`setup-path` on Linux writes one marked block, `# >>> aiup PATH >>>` / `# <<< aiup PATH <<<` (the same markers `ensure_zsh_path_block` and `persist_path` use), only when the directory is not already handled, into:

| File | Why |
| --- | --- |
| `~/.profile` (created if missing) | Login shells and display managers that read it. |
| `~/.bashrc`, block inserted at the top | Interactive bash, and non-interactive bash over SSH on distros that read `.bashrc` there. Many distro `.bashrc` files return early when non-interactive, so an appended block would never run. |
| `~/.zshenv` (only when zsh is installed or `$SHELL` is zsh) | Every zsh, interactive or not, so agent shells see it. |
| `~/.config/fish/conf.d/aiup.fish` (only when fish is installed) | Fish, using `contains -- DIR $PATH; or set -gx PATH DIR $PATH`. |
| `~/.config/environment.d/60-aiup.conf` (only on systemd user sessions: `XDG_RUNTIME_DIR/systemd` exists) | Graphical sessions and apps started from them, which is where most agent tools and editors get their PATH. Content: `PATH=${HOME}/.local/bin:${PATH}`. Takes effect at the next login. |

Each POSIX block guards against duplicates at run time: `case ":$PATH:" in *":DIR:"*) ;; *) PATH="DIR:$PATH"; export PATH ;; esac`. Directories with newlines are refused (as `persist_path` does). Paths under `$HOME` are written as `$HOME/...`. The installer then prints the `export PATH=...` line for the current shell, like the macOS installer.

`install-aiup --uninstall` removes the shim, the launcher and every marked block. It leaves `~/.local/share/aiup`, `~/.local/state/aiup`, `~/.cache/aiup` and `~/.config/aiup` and prints the exact `rm -rf` lines, matching the manual steps in `docs/install.md`.

### 3.3 Windows: how the user ends up typing `aiup`

Install command (works under the default `Restricted` execution policy because nothing is run as a script file):

```powershell
irm https://raw.githubusercontent.com/travisjneuman/aiup/main/windows/install-aiup.ps1 | iex
```

`windows/install-aiup.ps1` must run in Windows PowerShell 5.1 and pwsh 7 and must be pure ASCII (5.1 reads a BOM-less UTF-8 file as the ANSI code page). Steps:

1. Find Python 3.9+: `$env:AIUP_PYTHON`, then `py -3` (resolved to an absolute path with `py -3 -c "import sys; print(sys.executable)"`), then `python.exe` and `python3.exe` on PATH. Each candidate must run `-I -c` and report 3.9+ within 10 seconds. The Microsoft Store alias stubs in `%LOCALAPPDATA%\Microsoft\WindowsApps` fail this check when no Store Python is installed, so they are skipped by behavior, not by path. If nothing qualifies, the installer asks `Python 3.9 or newer was not found. Install Python from winget now? [y/N]`; on yes it runs winget for the official Python package in user scope (WP8 picks the id from winget's official source and records it in the script); on no, or without a console, it prints the winget command and exits 1.
2. Create `%LOCALAPPDATA%\Programs\aiup\bin` and `%LOCALAPPDATA%\Programs\aiup\launcher`.
3. Download `main/runtime/launcher/aiup_launcher.py` with `Invoke-WebRequest -UseBasicParsing` (TLS 1.2 forced on 5.1 via `[Net.ServicePointManager]::SecurityProtocol`), 1 MiB cap, into a temp file in the same folder; validate the same markers as Linux plus a `compile()` by the chosen Python; then `Move-Item -Force`.
4. Write three shims into `bin` (atomic: write temp, then move):
   - `aiup.cmd` (works in cmd, Windows PowerShell 5.1, pwsh 7, and anything that runs `.cmd` from PATH):

     ```bat
     @echo off
     setlocal
     set "AIUP_PYTHON=C:\path\to\python.exe"
     "%AIUP_PYTHON%" -I -B -X utf8 "%LOCALAPPDATA%\Programs\aiup\launcher\aiup_launcher.py" %*
     exit /b %ERRORLEVEL%
     ```

   - `aiup.ps1`, written only when the effective execution policy allows local scripts (`Get-ExecutionPolicy` is not `Restricted` or `AllSigned`). It runs the same command with `& $py ... @args; exit $LASTEXITCODE`. It avoids cmd's "Terminate batch job (Y/N)?" prompt after Ctrl-C in PowerShell when PowerShell picks it over `aiup.cmd` (see open question 1).
   - `aiup` with no extension, a POSIX sh shim for Git Bash and other MSYS shells, which do not run `.cmd` files by bare name. It converts the launcher path with `cygpath -w` when available.
5. Unless `AIUP_NO_MODIFY_PATH=1`, run `python aiup_launcher.py setup-path "%LOCALAPPDATA%\Programs\aiup\bin"`. On Windows `setup-path` uses `winreg` to read `HKCU\Environment\Path` without expanding it, prepends the folder only if missing (case-insensitive, trailing backslash ignored), writes it back with its existing value type (`REG_SZ` or `REG_EXPAND_SZ`; a new value is `REG_EXPAND_SZ`), and broadcasts `WM_SETTINGCHANGE` with `SendMessageTimeoutW` through `ctypes`. It also adds the folder to the current PowerShell session (`$env:Path`). Already-running programs keep their old PATH until restarted; the installer says so.
6. `install-aiup.ps1 -Uninstall` removes the shims, the launcher and the PATH entry, and prints the folders under `%LOCALAPPDATA%\aiup` it left in place.

The launcher and runtime always run with `-X utf8` on Windows (also set through `PYTHONUTF8=1` for child Python processes aiup itself starts), and `-B` so no `__pycache__` lands inside a generation. Bytecode goes to `PYTHONPYCACHEPREFIX=<cache>/pycache` (section 9.2) so startup stays fast.

---

## 4. Release contract

### 4.1 One pointer for every platform

`macos/release` stays the only release pointer. Its format does not change:

```
# aiup release: public launchers run the runtime and catalog at this commit.
<version> <40-hex commit>
```

The Python launcher reads the same URL default (`AIUP_RELEASE_URL=$AIUP_REPO_RAW/main/macos/release`). One release means one commit for macOS, Linux and Windows, so the catalog and both runtimes always come from the same reviewed state, and there is no second pointer to drift. The path keeps its `macos/` prefix because installed macOS launchers have it built in; renaming it would break them.

### 4.2 Versions that must agree

At a release commit these four values are equal, and `scripts/publish-release` refuses to write the pointer otherwise:

| Where | Form |
| --- | --- |
| `macos/aiup` | `AIUP_VERSION="2026.11.03-01"` |
| `macos/catalog/manifest.tsv` | `# aiup-runtime-version: 2026.11.03-01` |
| `catalog/platforms.tsv` | `# aiup-runtime-version: 2026.11.03-01` |
| `runtime/aiup/version.py` | `AIUP_VERSION = "2026.11.03-01"` |

`scripts/bump-version VERSION` sets all four. It accepts only `YYYY.MM.DD-NN`.

### 4.3 `runtime/FILES`

The Python runtime is many files, so the launcher needs a list. `scripts/stamp-runtime` writes it from the working tree after source edits and before the release commit:

```
# aiup runtime files: sha256 size path
# aiup-runtime-version: 2026.11.03-01
3f2a...  1834  runtime/aiup_main.py
9b1c...  20511  runtime/aiup/cli.py
...
77de...  48120  macos/catalog/manifest.tsv
a0c4...  61002  catalog/platforms.tsv
5e19...  2210  catalog/categories.tsv
c8d2...  30410  catalog/tool-meta.tsv
```

Rules: two spaces between fields; paths sorted; every `.py` file under `runtime/aiup/` plus `runtime/aiup_main.py` plus the four catalog files, nothing else (the launcher itself is not listed). Allowed path pattern: `^(runtime/aiup_main\.py|runtime/aiup/[a-z0-9_/]+\.py|macos/catalog/manifest\.tsv|catalog/[a-z0-9-]+\.tsv)$`. `stamp-runtime` refuses a file that contains a CR byte or is not UTF-8, so the hash is the same bytes GitHub serves. It is a release manifest (like a lockfile), so it is committed.

### 4.4 Publishing

The release rule in `AGENTS.md` becomes (WP11 edits the text):

1. `scripts/bump-version NEW_VERSION`
2. Move CHANGELOG `Unreleased` under the new version.
3. `scripts/stamp-runtime`
4. Commit and push.
5. `scripts/publish-release`
6. Commit and push `macos/release`.

`scripts/publish-release` keeps its current macOS check (runtime and manifest versions at `origin/main`) and adds, all read with `git show "$sha:<path>"` so the working tree does not matter:

- `catalog/platforms.tsv` header and `runtime/aiup/version.py` equal the macOS version;
- `runtime/FILES` names that version, and every listed path exists at `$sha` with the listed size and SHA-256, and every `.py` under `runtime/aiup/` at `$sha` is listed.

Any mismatch stops before `macos/release` is written, with a message naming the file.

### 4.5 Launcher behavior (`runtime/launcher/aiup_launcher.py`)

Same contract as `macos/aiup-launcher`, in Python:

- `AIUP_LAUNCHER_REVISION = 1` (its own counter; exported with `AIUP_LAUNCHER_KIND=python`). The runtime can ask for a newer launcher the way `launcher_revision_notice` does.
- Fetch the pointer: HTTPS only, 4 KiB cap, 10 second timeout (`urllib.request` with a default SSL context; redirects allowed only to `https:`). Parse the first non-comment line as `<version> <40 lowercase hex>`.
- If the current generation's `release` file names that commit and the generation validates, run it with no download.
- Otherwise download `runtime/FILES` at the commit (`$AIUP_REPO_RAW/<sha>/runtime/FILES`, 64 KiB cap), check its version against the pointer, then download every listed file (at most 6 at once, each capped at 1 MiB, 8 MiB total, 30 second timeout per file, 2 retries) into `generations/.staging-<id>/` keeping their repo paths.
- `validate_generation(dir, expected_version)`: every listed file present with the right size and SHA-256; every `.py` passes `compile(source, path, "exec")` (syntax only, nothing runs); the four version strings agree; `catalog/platforms.tsv` parses and has an `fzf` row; no unlisted files except `release` and `__pycache__` (which `-B` should prevent anyway).
- Activation: hold `activation.lock` (created with `os.open(O_CREAT | O_EXCL)`, holding `pid start_time random`), rename staging to `generations/<version>-<epoch>-<pid>`, write `previous-generation`, then replace `current-generation` with `os.replace`. A lock whose owner is gone is recovered as `acquire_activation_lock` does. Owner liveness uses `Platform.pid_alive`, never `os.kill(pid, 0)` on Windows (there it terminates the process).
- Retention: keep the current generation and any generation younger than a day, remove older ones only when they contain nothing but aiup's files (`prune_unreferenced_generations`). Sweep staging folders and temp files older than an hour (`sweep_stale_temporaries`).
- Offline or invalid download: print the reason and run the last validated generation (`fall_back`); with none, exit 1.
- Run: in-process. Set `AIUP_ACTIVE_RUNTIME`, `AIUP_ACTIVE_GENERATION`, `AIUP_CATALOG_DIR`, `AIUP_LAUNCHER_PATH`, `AIUP_PYTHON` (= `sys.executable`), release the lock, put `<generation>/runtime` first on `sys.path`, import `aiup.cli`, and `sys.exit(aiup.cli.main(argv))`. In-process keeps one interpreter start and keeps Ctrl-C and exit codes intact on Windows, where `os.execv` starts a new process instead of replacing this one.
- `setup-path DIR...` subcommand (section 3.2 and 3.3). It is the only thing the launcher does besides launching.

### 4.6 Development and offline use

`AIUP_SOURCE_PATH=/path/to/checkout/runtime/aiup_main.py aiup version` runs a checkout with its adjacent catalog files, skips the pointer, and is used only when set non-empty (same rule as the macOS launcher). Running `python3 runtime/aiup_main.py` from a checkout is equivalent. A missing or invalid explicit source fails; it never falls back to the release.

---

## 5. Catalog schema

### 5.1 Why a separate file

`catalog_manifest_load` reads each row with `read -r id category kind lifecycle label docs target endpoint`, so an extra column would be folded into `endpoint`, and `manifest_ok` in installed macOS launchers checks the same file. New columns in `manifest.tsv` would break both. So the base file stays as it is and Linux and Windows data live beside it in `catalog/`.

The new runtime reads from `manifest.tsv`: `id`, `category`, `lifecycle`, `label`, `docs`, and `endpoint` (column 8). It ignores `kind` and `target` (macOS install data) except to carry them into `catalog --json --platform all` as `macos`.

### 5.2 `catalog/platforms.tsv`

Header lines, then one row per id that has at least one Linux or Windows target. Column order matches what the research workers produce, with two default columns added before `notes`:

```
# aiup cross-platform install targets
# aiup-runtime-version: 2026.11.03-01
# id	linux_arch	linux_apt	linux_dnf	linux_flatpak	linux_snap	linux_brew	linux_other	windows_winget	windows_scoop	windows_choco	windows_other	linux_default	windows_default	notes
```

| # | Column | Meaning |
| --- | --- | --- |
| 1 | `id` | Must exist in `manifest.tsv`. |
| 2 | `linux_arch` | pacman package (`pkg` or `repo/pkg`) or AUR package (`aur:pkg`). |
| 3 | `linux_apt` | Debian/Ubuntu package name. |
| 4 | `linux_dnf` | Fedora/RHEL package name. zypper does not read this column (open question 4, settled). |
| 5 | `linux_flatpak` | Flatpak app id; `remote:app.id` for a remote other than Flathub. |
| 6 | `linux_snap` | Snap name, optionally followed by ` --classic`. |
| 7 | `linux_brew` | Linuxbrew formula (`name` or `tap/name`). |
| 8 | `linux_other` | Prefixed targets (5.3): `npm:`, `uv:`, `pipx:`, `cargo:`, `go:`, `script:`, `vendor:`, `nix:`. |
| 9 | `windows_winget` | winget package id (`Publisher.Package`); `msstore:<id>` for the Store source. |
| 10 | `windows_scoop` | `bucket/app`. |
| 11 | `windows_choco` | Chocolatey package id. |
| 12 | `windows_other` | Same prefixes as `linux_other`; scripts must be `.ps1`. |
| 13 | `linux_default` | Channel name that ships releases first on Linux (section 6.3 names). Empty: use the precedence rule in 5.4. |
| 14 | `windows_default` | Same for Windows. |
| 15 | `notes` | Free text, never parsed. Repository setup a package needs, known lag, why something is missing. |

Empty cell: no target on that channel. An id with every Linux cell empty is not available on Linux, and the same for Windows. Ids in `manifest.tsv` with no row here are macOS only.

### 5.3 Cell grammar

A cell holds one target or several separated by `;` (no spaces around `;`). Values never contain a tab, `;`, or a control character. The loader (`catalog/targets.py`) rejects anything else with the file, line and column.

```
cell        = "" | target *( ";" target )
target      = plain | prefixed
plain       = package [ " " flag ]        ; only in manager columns
prefixed    = prefix ":" value            ; only in *_other columns, and aur: / msstore: / remote: in their own columns
prefix      = "npm" | "uv" | "pipx" | "cargo" | "go" | "nix" | "script" | "vendor"
```

| Form | Meaning |
| --- | --- |
| `npm:@scope/pkg` | Install into aiup's npm prefix (section 6.4). |
| `uv:pkg` | `uv tool install pkg`. |
| `pipx:pkg` | `pipx install pkg`. |
| `cargo:crate` | `cargo install --locked crate`. |
| `go:module/path/cmd` | `go install module/path/cmd@latest`. |
| `nix:attr` | `nix profile install nixpkgs#attr` (Linux only). |
| `script:https://...` | Official install script, downloaded to a private file, then run (section 6.7). |
| `vendor:command args` | The tool's own updater, for example `vendor:claude update`. |
| `script:URL;vendor:CMD` | One `vendor` channel: install with the script, update with the command, and fall back to the script when the command fails. This is how `update_claude` works today (`claude update`, then `run_vendor_installer`). |
| `pkg --classic` (snap) | The only allowed snap flag. |
| `aur:pkg` | AUR package, needs yay or paru (section 7.2). |

Flags allowed in plain cells: snap `--classic`. Anything else is a load error, so data cannot smuggle arbitrary arguments into a command line.

### 5.4 Default channel order

`--policy newest` (the default, as on macOS: "installs each tool from the channel that ships its releases first") picks the first target whose provider is available on this computer, in this order:

1. The channel named in `linux_default` / `windows_default`, if available here.
2. Linux: `vendor` (script and self-updater), `npm`, `uv`, `pipx`, `cargo`, `go`, then the distro manager that matches this computer (`pacman`, then `aur` when a helper exists; or `apt`, `dnf`, `zypper`), then `brew`, `flatpak`, `snap`, `nix`.
3. Windows: `vendor`, `npm`, `uv`, `pipx`, `cargo`, `go`, `winget`, `scoop`, `choco`.

Upstream channels come first because, as on macOS, package managers usually trail the publisher by hours to days. A distro manager whose package needs a repository that is not configured here (apt or dnf cannot resolve the name now) is treated as unavailable; aiup never adds third-party repositories.

### 5.5 `catalog/categories.tsv` and `catalog/tool-meta.tsv`

These hold data that lives in Bash functions today. The macOS runtime keeps its own copies; the new runtime reads only these files.

`categories.tsv`: `id`, `order`, `name`, `emoji`, `blurb`. Seeded from `CATEGORY_ORDER`, `category_display_name`, `catalog_category_emoji` and `catalog_category_blurb`, with blurbs that mention a Mac rewritten in platform-neutral words (for example `local-ai`: "Model runtimes and servers that run on your computer"). Pseudo-categories: `updates`, `packages` ("Other packages", replacing `homebrew`), `detected` ("Other software").

`tool-meta.tsv`: `id`, `aliases`, `commands`, `processes`, `linux_data`, `windows_data`.

| Column | Format | macOS source |
| --- | --- | --- |
| `aliases` | comma list | `resolve_tools` |
| `commands` | comma list of command base names; Windows adds `PATHEXT` | `binary_of_tool` (default: the id) |
| `processes` | comma list of process names that mean "the app is open, defer" | the running-app checks behind `cask_update_gate` and `app_bundle_running` |
| `linux_data` | `;` list of paths using `~`, `$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`, `$XDG_STATE_HOME`, `$XDG_CACHE_HOME` | `tool_user_data_paths` |
| `windows_data` | `;` list using `%APPDATA%`, `%LOCALAPPDATA%`, `%USERPROFILE%` | `tool_user_data_paths` |

The loader expands only those variables; any other `$` or `%` is a load error. Expanded paths must stay inside the user's home or the named base folders, or the row is rejected.

### 5.6 Public reporting (`scripts/sync-public-docs`, `site/catalog.json`)

- The runtime gains `aiup catalog --json --platform all`: the same top-level `categories`, `tools`, `recommended` arrays as `print_catalog_definition`, with an additive `platforms` object per tool: `{"macos": {"kind": "...", "target": "..."}, "linux": [{"channel": "pacman", "package": "..."}, ...], "windows": [...]}`. Missing platform keys mean not available there.
- `scripts/sync-public-docs` keeps its macOS export as the source for counts and adds one Python export of the same data: an inline `python3 -I -B -c` call to `aiup.catalog.export.render(load(), "json", "all")`, with `AIUP_CATALOG_DIR` set to the checkout's `catalog/` (no scan, no state, no network). It stops before writing anything if the two exports disagree on ids or categories.
- `site/catalog.json`: each tool gets the additive `platforms` object. `docs/catalog.md` and the README `CATALOG` block get Linux and Windows columns showing the default channel name, or blank.
- `showcase.json`: no change to the `platform` metric, status, summary or stack until Linux and Windows support ships in a release and has been reviewed. The Catalog tools metric keeps counting the top-level `tools` array (the curated base list), so it does not change meaning.

### 5.7 Validation at load

`catalog/loader.py` stops with a clear message (exit 1) when: a version header does not match `AIUP_VERSION`; an id repeats; an id in `platforms.tsv` or `tool-meta.tsv` is not in `manifest.tsv`; a category is not in `categories.tsv`; a lifecycle is not `active|maintenance|sunset|archived` (`catalog_validate`); a cell breaks the grammar; a default names a channel with no target in that row; a `script:` URL is not HTTPS, or a Windows script URL does not end in `.ps1`; there is no `fzf` row. This is the runtime refusing bad input, the same role `catalog_validate` plays today.

---

## 6. Provider model

### 6.1 Data classes (`runtime/aiup/model.py`, owned by WP1)

```python
@dataclass(frozen=True)
class Target:
    channel: str                 # provider name, section 6.3
    package: str                 # package id, crate, module, URL, or command line
    flags: Tuple[str, ...] = ()  # only "--classic" today
    update_command: str = ""     # vendor channel: self-update command
    install_script: str = ""     # vendor channel: script URL

@dataclass(frozen=True)
class CatalogEntry:
    id: str
    category: str
    lifecycle: str
    label: str
    docs: str
    endpoint: str
    macos_kind: str
    macos_target: str
    targets: Mapping[str, Tuple[Target, ...]]   # "linux" / "windows" -> targets in default order
    defaults: Mapping[str, str]                 # "linux" / "windows" -> channel name or ""
    aliases: Tuple[str, ...]
    commands: Tuple[str, ...]
    processes: Tuple[str, ...]
    user_data: Mapping[str, Tuple[str, ...]]    # unexpanded paths per OS
    notes: str

@dataclass(frozen=True)
class Installed:
    version: str                 # "" when present but unreadable
    path: Optional[str]
    scope: str                   # "user" | "system" | "machine"
    channel: str

@dataclass(frozen=True)
class Latest:
    version: str                 # "" when unverified
    source: str                  # "registry", "pypi", "pacman", "winget", "vendor-endpoint", ...
    unverified_reason: str = ""
    pending: bool = False        # the manager says an update waits but names no version (flatpak)
    managed: str = ""            # another updater owns this copy (Microsoft Store): the note to show

@dataclass(frozen=True)
class Step:
    argv: Tuple[str, ...]
    label: str                   # shown in progress and logs
    privilege: str = "none"      # "none" | "sudo" | "helper-sudo" | "uac-possible" | "elevated-required" | "polkit"
    interactive: bool = False    # needs the terminal (sudo prompt, AUR review)
    env: Mapping[str, str] = field(default_factory=dict)
    timeout: Optional[float] = None
    ok_codes: Tuple[int, ...] = (0,)
    download: str = ""           # script steps: URL the engine downloads first; argv gets the file path as {file}
    on_fail: str = "stop"        # "stop" | "next" (try the following step, e.g. vendor -> script)
    confirm: str = ""            # a y/N question the engine asks first ("Add and trust tap X?"); default no

@dataclass(frozen=True)
class Action:
    tool: str
    op: str                      # "install" | "update" | "remove"
    channel: str
    steps: Tuple[Step, ...]
    note: str = ""
    result: str = ""             # empty steps only: "skipped" | "deferred" | "self-updated" | "failed"

@dataclass(frozen=True)
class PackageRecord:            # package-manager inventory row
    manager: str
    name: str
    version: str
    scope: str
    explicit: bool               # installed on request, not as a dependency
    paths: Tuple[str, ...] = ()

@dataclass(frozen=True)
class Ownership:
    manager: str
    package: str
    confidence: str              # "exact" (manager said so) | "prefix" (path is under its root)

@dataclass
class ToolResult:               # one row of aiup-run-v1 / aiup-check-v1
    tool: str
    result: str                  # same vocabulary as docs/scripting.md
    before: str = ""
    after: str = ""
    installed: str = ""
    latest: str = ""
    channel: str = ""
    note: str = ""
    warning: bool = False
    duration: int = 0
```

Use `typing.Tuple`, `Mapping`, `Optional` for 3.9.

- `Latest.pending`: `engine/latest.py` `classify` gives `update` with no version. `aiup check` shows `unknown` with the note "An update is waiting; its version is not published.", and the picker shows `unknown` too.
- `Latest.managed`: `classify` gives `skipped` with that note, never an update. Neither field is stored in the available-version cache.
- `Step.confirm`: the engine asks once per run (`privilege.confirm_step`). No, the default, skips the action; no terminal defers it; a dry run plans it as yes. Lanes never ask, so such a step runs in the main lane.
- `Action.result`: an action without steps never counts as done. `engine/plan.py` `empty_result` is the one rule: `result` when set, else `failed` for an install and `skipped` for an update or removal, with `note` saying why.
- Version order: `versions.version_cmp(a, b, scheme)` takes `generic` (the macOS order), `pacman` (libalpm `vercmp`, also AUR), `dpkg` (apt) or `rpm` (dnf, zypper). `scheme_for(channel)` picks it; every other channel is `generic`.

### 6.2 Provider interface (`runtime/aiup/providers/base.py`, owned by WP1)

Providers describe; the engine acts. A provider never runs a mutating command itself. It returns `Action`s and the engine runs the steps, which gives dry-run, logging, progress, sudo handling and Ctrl-C in one place (macOS does all of this in `run_with_heartbeat`).

```python
class Provider:
    name: str = ""                      # channel name
    oses: FrozenSet[str] = frozenset()  # {"linux"}, {"windows"}, {"linux", "windows", "darwin"}
    scope: str = "user"                 # "user" | "system" | "mixed"
    lane: str = "main"                  # lane key for parallel runs (section 9.1)
    exclusive: bool = False             # True: runs alone, never beside another lane
    targeted_update: bool = True        # False: a single package cannot be updated safely (pacman)

    def available(self, ctx: Context) -> bool: ...
    def installed(self, ctx: Context, target: Target) -> Optional[Installed]: ...
    def latest(self, ctx: Context, target: Target, timeout: float) -> Latest: ...
    def outdated(self, ctx: Context) -> Mapping[str, Latest]:
        return {}                       # optional bulk read, keyed by package
    def inventory(self, ctx: Context) -> Iterable[PackageRecord]:
        return ()
    def install(self, ctx: Context, target: Target) -> Action: ...
    def update(self, ctx: Context, target: Target) -> Action: ...
    def remove(self, ctx: Context, target: Target) -> Action: ...
    def owns(self, ctx: Context, path: str) -> Optional[Ownership]:
        return None
    def system_upgrade(self, ctx: Context) -> Optional[Action]:
        return None                     # aiup system; only system-scope providers
    def metadata_refresh(self, ctx: Context) -> Optional[Action]:
        return None                     # e.g. apt-get update; engine runs at most once per run

    # optional hooks; the engine calls them on every provider, so each has a safe default
    def can_provide(self, ctx: Context, target: Target) -> bool:
        return True                     # asked before an install: does the repository have it here
    def lock_held(self, ctx: Context) -> str:
        return ""                       # checked before any step: a note while another process holds the lock
    def notices(self, ctx: Context) -> Tuple[str, ...]:
        return ()                       # shown after aiup system (pacman: new .pacnew files)
    def owns_many(self, ctx: Context, paths: Sequence[str]) -> Dict[str, Ownership]:
        ...                             # default: owns() for each path
    def unavailable_reason(self, ctx: Context) -> str:
        return ""                       # for doctor: why this channel cannot be used here
    def forget(self) -> None:
        return None                     # drop cached reads; called after every step that ran
    def explain_exit(self, op: str, code: Optional[int]) -> Optional[Tuple[str, str]]:
        return None                     # (result, note) for a non-zero exit status
```

Shared helpers live beside the providers: `providers/_linux.py` (`run_c` reads with `LC_ALL=C`, `system_step` and `user_step`, `/proc/locks` and pid-file lock checks, `Memo` for bulk reads) and `providers/_win.py` (`run_w` with unsigned exit codes, `code_forms` for `ok_codes`, PowerShell `-EncodedCommand` JSON calls, Windows folders, `Memo`).

Reads go through `ctx.run_read(argv, timeout, max_bytes, cwd=None, env=None)` (WP5, `platform/proc.py`): no terminal, stdin closed, never sudo, output capped (macOS `AIUP_PROVIDER_MAX_BYTES`, `bounded_provider_capture`), decoded with `proc.decode_output` (UTF-8, then the console or locale code page on Windows, with replacement). HTTP reads go through `ctx.net` (WP6, `engine/net.py`): HTTPS only, size caps, timeouts, the available-version cache.

`run_read` takes an optional `cwd` (some tools read a project file there) and `env` (variables added on top of the user's environment).

`Context` (`engine/context.py`, WP6) carries: `platform`, `dirs`, `settings`, `net`, `cache`, `dry_run`, `interactive` (stdin and stderr are terminals), `verbose`, `log`, `distro` (Linux `os-release` id and id_like). Commands get it from `engine.context.create_context(args, catalog)`, which reads `dry_run`, `verbose`, `refresh`, `force`, `json` and the loaded config from the parsed command line.

### 6.3 Providers and channel names

| Channel | Module | OS | Scope | Lane | Exclusive | Targeted update | Installed / latest read | Update and remove |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pacman` | `linux_pacman.py` | linux | system | system | yes | **no** | `pacman -Q pkg`; latest from `checkupdates` (pacman-contrib, uses a temporary database, no root) or `pacman -Si` against the current sync db | Update only through a full `pacman -Syu` (never `-Sy` alone: partial upgrades are unsupported on Arch). Remove: `pacman -Rs pkg`. |
| `aur` | `linux_aur.py` | linux | system | system | yes | yes | `pacman -Qm`; latest from the helper (`paru -Qua` / `yay -Qua`) | `paru -S pkg` or `yay -S pkg`, run as the user (never root), interactive. Remove with pacman. |
| `apt` | `linux_apt.py` | linux | system | system | yes | yes | `dpkg-query -W`; latest from `apt-cache policy` (local lists) | `sudo apt-get install --only-upgrade -y pkg` after one `sudo apt-get update` per run (`metadata_refresh`). Remove: `apt-get remove`, never purge. |
| `dnf` | `linux_dnf.py` | linux | system | system | yes | yes | `rpm -q`; latest from `dnf -q list --upgrades pkg` | `sudo dnf upgrade -y pkg`. Remove: `dnf remove -y`. |
| `zypper` | `linux_zypper.py` | linux | system | system | yes | yes | `rpm -q`; latest from `zypper -q list-updates` | `sudo zypper --non-interactive update pkg`. System upgrade: `zypper dup` on Tumbleweed (`os-release` id `opensuse-tumbleweed`), `zypper update` otherwise. |
| `flatpak` | `linux_flatpak.py` | linux | mixed | flatpak | no | yes | `flatpak list --app --columns=application,version,installation`; latest from `flatpak remote-info` | `flatpak update -y --noninteractive --user|--system APP`. New installs use `--user`. System installation auth is polkit's own prompt. |
| `snap` | `linux_snap.py` | linux | system | system | yes | yes | `snap list`; latest from `snap info` | `sudo snap refresh name`. Remove: `snap remove`. |
| `brew` | `brew.py` | linux (darwin later) | user | brew | no | yes | `brew list --versions`, `brew outdated --json=v2` | `brew upgrade --formula`. Same tap rules as macOS (`brew_ensure_target_tap`: ask before adding a tap). |
| `nix` | `linux_nix.py` | linux | user | nix | no | yes | `nix profile list --json` | `nix profile upgrade NAME`. Remove: `nix profile remove NAME`. |
| `winget` | `win_winget.py` | windows | mixed | system | yes | yes | `winget list --id ID --exact`, `winget upgrade` (bulk); always `--disable-interactivity --accept-source-agreements` | `winget upgrade --id ID --exact --silent --accept-package-agreements --accept-source-agreements --disable-interactivity`. New installs pass `--scope user` when the manifest offers it. Remove: `winget uninstall --id ID --exact`. |
| `scoop` | `win_scoop.py` | windows | user | scoop | no | yes | `scoop list`, `scoop status` | `scoop update app`. Ask before `scoop bucket add` (same rule as Homebrew taps). Remove: `scoop uninstall app` (never `-p`). |
| `choco` | `win_choco.py` | windows | system | system | yes | yes | `choco list --limit-output`, `choco outdated --limit-output` | `choco upgrade -y pkg`, only when aiup runs elevated (section 7.4). |
| `appx` | `win_appx.py` | windows | user | appx | no | no | `Get-AppxPackage` through `powershell -NoProfile` (cached, it is slow) | Detection and removal only (`Remove-AppxPackage` for the current user). Updates come from the Store; `latest` answers `managed` ("managed by Microsoft Store"), so aiup reports them as skipped with that note. |
| `npm` | `npm.py` | all | user | npm | no | yes | aiup prefix `lib/node_modules/<pkg>/package.json`; latest from the npm registry | `npm install -g --prefix <aiup prefix> pkg@latest` with the macOS provenance gate and allowed install scripts (`npm_install_aiup_latest`, `npm_provenance_gate`, `npm_allowed_install_scripts`). |
| `pnpm` | `pnpm.py` | all | user | npm | no | yes | `pnpm ls -g --json` | Updates copies the user installed with pnpm (`keep` policy). Never chosen for new installs. |
| `bun` | `bun.py` | all | user | npm | no | yes | `bun pm ls -g` | Same as pnpm. |
| `uv` | `uv.py` | all | user | python | no | yes | `uv tool list`; latest from PyPI | `uv tool upgrade pkg` / `uv tool install` (`uv_tool_install_args`). |
| `pipx` | `pipx.py` | all | user | python | no | yes | `pipx list --json`; latest from PyPI | `pipx upgrade pkg`. |
| `cargo` | `cargo.py` | all | user | rust | no | yes | `~/.cargo/.crates2.json`; latest from the crates.io API | `cargo install --locked crate`. |
| `go` | `go.py` | all | user | go | no | yes | `go version -m BINARY` (module path and version); latest from `proxy.golang.org/<module>/@latest` | `go install module@latest`. |
| `vendor` | `vendor.py` | all | user | vendor | no | yes | the tool's `--version`; latest from manifest `endpoint` (column 8) when present, else unverified | Self-update command, falling back to the install script (`on_fail="next"`). |
| `script` | `script.py` | all | user | vendor | no | yes | the tool's `--version` | Download then run (section 6.7). Used for installs when a tool has no `vendor:` updater. |

`exclusive=True` providers share lane `system` and never run beside each other or beside an interactive step.

### 6.4 Node, npm and aiup's own prefixes

As on macOS (`AIUP_NPM_PREFIX`, `ensure_managed_paths`), npm tools go into aiup's own prefix so they never need root and never collide with a system npm:

- Linux: `$XDG_DATA_HOME/aiup/npm`, commands in `.../npm/bin`.
- Windows: `%LOCALAPPDATA%\aiup\data\npm`; npm puts command shims in the prefix folder itself, not `bin`.

The runtime calls `aiup_launcher.py setup-path <npm bin>` (through `AIUP_LAUNCHER_PATH`) the first time it installs into the prefix. The `npm` infra entry means "Node and npm": aiup keeps whatever provides them now if it is a version manager (nvm, fnm, volta, mise, asdf: detected from the resolved path) and never replaces it. A tool found in a root-owned npm prefix is reported with `aiup channel TOOL npm` as the fix (that moves it into aiup's prefix and then removes the old copy, like `channel_retire_others`); aiup never runs `sudo npm`. The same rule holds for Python: never `sudo pip`, never `--break-system-packages`.

### 6.5 Channel resolution and policy (`engine/channels.py`, WP6)

```python
@dataclass(frozen=True)
class Resolution:
    active: Optional[Target]          # channel this run uses
    installed: Tuple[Tuple[Target, Installed], ...]   # every copy found, any channel
    reason: str                       # shown by aiup channel TOOL (macOS: channel_reason)
    picked: bool                      # True when the user picked it
    retire: Tuple[Tuple[Target, Installed], ...] = ()   # copies to remove once the active one works
    kept_note: str = ""               # copies left in place, and why

def resolve(entry: CatalogEntry, os_name: str, policy: str,
            picks: Mapping[str, str], ctx: Context) -> Resolution: ...
```

- A pick in `channels.tsv` (`tool<TAB>channel`) always wins, as in `channels_load`. `aiup channel TOOL default` removes the pick.
- `newest`: section 5.4 order.
- `keep`: update each tool from wherever it is installed now; never move or remove a copy; new installs use `newest` (`channels_apply_policy` with `keep`).
- `system` (Linux: the distro manager; Windows: winget) or a manager name (`brew`, `flatpak`, `snap`, `nix`, `winget`, `scoop`, `choco`): use that manager wherever it has the tool; the next run moves those tools and removes each old copy once the new one is in place (macOS `brew` policy).
- `channels.tsv` stores the policy as `*<TAB>policy`, same as macOS.

### 6.6 Special tools

The 18 macOS `special` entries have Bash updaters (`update_claude`, `update_codex`, and so on). On Linux and Windows they are data, not code: `platforms.tsv` gives each a `vendor` channel (`script:URL;vendor:CMD`) or a package channel. Migration rules that macOS hard-codes (for example `update_claude` removing npm and Homebrew copies before using the native installer) become the general channel rule: a tool installed on a channel other than the active one is moved, and the old copy is removed after the new one works. Anything that cannot be expressed this way goes in a short per-tool hook table in `engine/channels.py`, with a comment naming the macOS function it follows. WP6 owns that table; keep it small.

### 6.7 Install scripts

Same safety as `run_vendor_installer`:

- HTTPS only, redirects only to HTTPS, 2 retries, 300 second limit, downloaded into a fresh private folder under `<cache>/downloads/installer.<random>`, refused when empty, removed afterwards.
- Linux: run with `bash` when the first line names bash, `sh` when it names sh; refuse anything else.
- Windows: `.ps1` only, run as `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <file>`. `-ExecutionPolicy Bypass` applies to that one process and that one file aiup just downloaded; it is the same trust decision as running a downloaded `install.sh`. aiup never uses `irm | iex` for catalog tools.
- Scripts run with stdin closed unless the step is marked interactive.
- Some installers get fixed arguments after the file path, from `_SCRIPT_ARGS` in `runtime/aiup/providers/script.py`, keyed by the exact catalog URL. Hermes gets `--skip-browser` (or `-SkipBrowser` on Windows) so its installer never downloads Chromium. macOS passes the same flag through `run_vendor_installer ... -- ARG`.

---

## 7. Privilege policy

macOS today: aiup never calls sudo itself; Homebrew may, and while any sudo runs under aiup the progress line reads "sudo password:" and stays put (`process_tree_has_sudo`, `run_with_heartbeat`). The same rules carry over, plus what Linux and Windows need.

### 7.1 Linux

- aiup refuses to run as root (euid 0) unless `AIUP_ALLOW_ROOT=1`. User-level installs would land in root's home, and AUR helpers refuse root.
- sudo is used only by system-scope providers (`pacman`, `aur` through its helper, `apt`, `dnf`, `zypper`, `snap`), only for an explicit action (`aiup only`, `aiup install`, `aiup remove`, `aiup system`, a picker action) or an update the `settings system` rule allows (7.3).
- User-level managers (`npm`, `pnpm`, `bun`, `uv`, `pipx`, `cargo`, `go`, `brew`, `nix`, `flatpak --user`, `vendor`, `script`) never run under sudo. A provider that marks such a step `privilege="sudo"` is a bug; `engine/privilege.py` refuses the step.
- aiup runs `sudo <argv>` with the real terminal as stdin and lets sudo ask. It never uses `sudo -S`, never reads, stores, pipes or caches a password, and never starts a `sudo -v` keep-alive loop. sudo's own timestamp policy applies as it would in the user's shell.
- Without a terminal (`aiup notify`, cron, agent shells), system steps run as `sudo -n`. If sudo would need a password, the tool is recorded `deferred` with the note "needs sudo; run aiup in a terminal" and the run goes on. Nothing hangs waiting for input nobody can see.
- While any `sudo` process is a descendant of aiup, the progress line reads `sudo password:` and stops redrawing (Linux: walk `/proc/<pid>/stat` parents; `Platform.process_tree_has`).
- Only the main lane gets the terminal. Parallel lanes have stdin closed and never contain a sudo step (section 9.1).
- flatpak system installations authenticate through polkit; aiup passes `--noninteractive` without a terminal and treats an auth failure as `deferred`.
- Package manager locks (`/var/lib/pacman/db.lck`, dpkg lock, dnf/zypper locks) are checked before a system step. A held lock gives `deferred` with "another package manager is running".

### 7.2 AUR

AUR packages are user-submitted build scripts. aiup only uses an existing helper (`paru`, then `yay`), always as the user, and never runs `makepkg` itself or as root. `settings aur review` (default) runs the helper interactively so its PKGBUILD diff and prompts appear; without a terminal, AUR updates are `deferred`. `settings aur trust` passes the helper's no-confirm flag for updates of already-installed AUR packages only; new AUR installs always run interactively.

### 7.3 `settings system report|ask|auto` and `aiup system`

Applies to catalog tools whose active channel is system-scope, and to the `packages` extras on system managers.

| Setting | Plain `aiup` run |
| --- | --- |
| `report` | Never touches system packages. The report lists them with "update with: aiup system" or "aiup only TOOL". |
| `ask` (default) | In a terminal, one question before any system step, naming each command that will run with sudo (for pacman: "This runs a full system upgrade: sudo pacman -Syu"). No terminal: same as `report`, tools `deferred`. |
| `auto` | Runs the steps without the question. sudo still asks for a password on screen when its policy needs one. |

Because pacman cannot update one package safely (`targeted_update=False`), a pacman-channel tool that is behind is updated only through `aiup system` or an approved full upgrade in a plain run; otherwise it is `deferred` with that note. `aiup only TOOL` on a pacman tool asks once and then runs `sudo pacman -Syu`, saying so first.

`aiup system` runs each available system provider's `system_upgrade` in turn, with a `[y/N]` question first unless `settings system auto`:

| Manager | Command |
| --- | --- |
| pacman (with AUR helper) | `paru -Syu` or `yay -Syu` as the user (interactive per 7.2), else `sudo pacman -Syu` |
| apt | `sudo apt-get update`, then `sudo apt-get upgrade` (never `dist-upgrade` or `full-upgrade`) |
| dnf | `sudo dnf upgrade --refresh` |
| zypper | `sudo zypper dup` (Tumbleweed) or `sudo zypper update` |
| snap | `sudo snap refresh` |
| flatpak | `flatpak update -y` (both installations; system one through polkit) |
| winget | `winget upgrade --all --silent --accept-package-agreements --accept-source-agreements --disable-interactivity` |
| choco | `choco upgrade all -y`, only in an elevated terminal |

### 7.4 Windows

- aiup never elevates itself: no `Start-Process -Verb RunAs`, no scheduled-task tricks, no `runas`, no gsudo, no Windows `sudo`. It runs at whatever level the user started it.
- winget: installers that need machine scope show their own UAC prompt. That prompt is Windows asking the user, so it is allowed for the same actions sudo is allowed on Linux (7.3), and only in an interactive session. Steps are marked `uac-possible`; the progress line shows "waiting for Windows approval" while a step runs past 5 seconds with a UAC-capable installer. Without an interactive desktop (SSH, scheduled task), machine-scope winget steps are `deferred` with "needs Windows approval; run aiup in a desktop terminal".
- New winget installs ask for `--scope user` when the package offers it, so most installs need no approval.
- choco needs administrator rights for almost everything. choco steps are `elevated-required`: they run only when aiup is already elevated (`Platform.is_elevated()`: token elevation through `ctypes`). Otherwise they are `deferred` with the exact command and "run from an elevated terminal".
- When aiup runs elevated, it prints one note at start: user-level tools will be installed for this account and choco steps are enabled.
- scoop, npm, uv, pipx, cargo, go, vendor and script steps never need elevation. A provider marking them otherwise is refused by `engine/privilege.py`.

### 7.5 `engine/privilege.py` API (WP6)

```python
@dataclass(frozen=True)
class PrivilegeDecision:
    allowed: bool
    wrap: Tuple[str, ...]      # e.g. ("sudo",) or ("sudo", "-n") or ()
    defer_note: str            # set when allowed is False

def decide(step: Step, provider: Provider, op: str, explicit: bool, ctx: Context,
           tool: str = "") -> PrivilegeDecision: ...
def confirm_step(ctx: Context, question: str) -> str: ...   # "yes" | "no" | "no-terminal" (Step.confirm)
```

`helper-sudo` is a step that runs as the user and calls sudo itself (the AUR helper, `paru` or `yay`). aiup never wraps it, but it follows the sudo rules: only for system package managers, never on Windows, the same `settings system` gate. An interactive one without a terminal is deferred; without a terminal the AUR provider passes `-n` to the helper's sudo, and a password request becomes `deferred`.

`explicit` is True for `only`, `install`, `remove`, `system` and picker actions; False for plain runs and `resume` (which, like macOS, never install what is missing). `retry` passes True unless `--no-install` is given, so like macOS it may install a missing tool.

---

## 8. Detection model

A separate research worker is writing `docs/research/system-detection-2026-11-02.md` (per-manager inventory commands, ownership queries, output formats, speed). This section defines the structure that research plugs into; it does not repeat it.

### 8.1 Three populations

Same split as `docs/public-catalog-facts.md` and `scan_inventory_index`:

1. **Managed:** catalog entries found installed on at least one channel (`Resolution.installed` non-empty).
2. **Package-manager inventory** (`packages` category): `PackageRecord`s from every available provider's `inventory()`, with `explicit=True` rows shown by default (pacman `-Qe`, apt manual marks, dnf user-installed, `brew leaves --installed-on-request`, winget, scoop, choco, flatpak apps, snaps), minus packages a catalog entry already covers (macOS `catalog_covers_brew`). Row ids are `pkg:<manager>:<name>`.
3. **Detected only:** software matched by nothing above, from PATH commands in user-facing prefixes, freedesktop `.desktop` files (Linux), and the Uninstall registry keys under HKCU and HKLM (Windows, read with `winreg`).

### 8.2 From a detected item to an action

```python
@dataclass(frozen=True)
class InventoryItem:
    id: str                    # catalog id, pkg:<manager>:<name>, or det:<source>:<key>
    name: str
    version: str
    population: str            # "managed" | "package" | "detected"
    source: str                # detection source name
    paths: Tuple[str, ...]
    owner: Optional[Ownership]

def owner_of(path: str, ctx: Context) -> Optional[Ownership]: ...
def actions_for(item: InventoryItem, ctx: Context) -> Tuple[str, ...]: ...   # "update", "remove", "adopt", "docs", "search"
```

`owner_of` asks every available provider's `owns(path)` and prefers `exact` answers (pacman `-Qo`, `dpkg -S`, `rpm -qf`, `go version -m`, scoop app folder, choco lib folder, aiup's npm prefix) over `prefix` answers. A detected item with an owner gets that manager's update and remove. A detected item that matches a catalog `commands` entry on another channel offers "adopt" (macOS: `brew_cask_adopt`), which is `aiup channel TOOL <channel>` plus the move. With no owner it offers only docs and a web search the user chooses on purpose (`detected_search_url`), as macOS does.

### 8.3 Hooks for the research doc (`detect/sources.py`, WP10)

```python
class DetectionSource:
    name: str = ""
    oses: FrozenSet[str] = frozenset()
    cost: str = "cheap"        # "cheap" | "slow": slow sources run after the picker opens
    def available(self, ctx: Context) -> bool: ...
    def scan(self, ctx: Context) -> Iterable[InventoryItem]: ...
    def fingerprint(self, ctx: Context) -> str: ...   # cheap stamp for cache validity (macOS: inventory_source_fingerprint)

def register(source: DetectionSource) -> None: ...
def all_sources() -> Tuple[DetectionSource, ...]: ...
```

Package-manager inventories are not sources: they come from `Provider.inventory()`, so each manager's knowledge lives in one module. WP10 implements PATH, desktop-entry and registry sources and the merge, using the research doc for commands and edge cases.

---

## 9. Runtime services

### 9.1 Concurrency and performance

- **Read workers:** `concurrent.futures.ThreadPoolExecutor`. Installed-version reads use `clamp(os.cpu_count() // 2, 2, 6)` workers (`check_worker_count`, `AIUP_CHECK_WORKERS`). Network reads use up to 8 workers with at most 2 per host. TUI prefetch uses 2 to 3 workers (`AIUP_TUI_PREFETCH_WORKERS`) and starts after the picker is interactive (`tui_prefetch_start`).
- **Bulk first:** before per-tool reads, each available provider's `outdated()` runs once (macOS `brew_outdated_snapshot_load`, `tui_prefetch_brew_consolidated`).
- **Lanes during a run:** steps are grouped by `Provider.lane`. The main lane runs first-class work in order (required infrastructure, then dependencies, then tools, like `main_update`). Other lanes (`npm`, `python`, `rust`, `go`, `brew`, `scoop`, `flatpak`, `nix`) run beside it in threads, each lane sequential inside, output to `<log>.lanes/<lane>` and merged into the run log afterwards (`lanes_start`, `lanes_finish`). Exclusive providers (`system` lane) run in the main lane, never beside an interactive step, and parallel lanes pause before an interactive step starts. Lanes are off with `AIUP_PARALLEL=0`, `--verbose`, `--dry-run`, or after Ctrl-C (`lanes_enabled`).
- **Child processes and Ctrl-C:** children run in aiup's foreground process group on Linux so terminal Ctrl-C and sudo prompts reach them. On Ctrl-C aiup stops starting work, waits up to 5 seconds for the running child, then `Platform.kill_tree(pid)` (Linux: SIGTERM, then SIGKILL, to the child's descendants found in `/proc`; Windows: `taskkill /T /F /PID`). Results: the interrupted tool `cancelled`, unreached tools `pending`, exit 130 (as macOS does since 2026.10.14).
- **Caches and TTLs** (same defaults and clamps as the top of `macos/aiup`):

| Cache | TTL | Where |
| --- | --- | --- |
| Inventory index | 300 s, plus source fingerprint | `<cache>/inventory-index.tsv`, `.meta` |
| TUI snapshot generations | 300 s | `<cache>/tui/v<schema>/generations/` |
| TUI session | 86400 s | `<runtime>/sessions/<token>/` |
| Available version per tool | 900 s, failures 60 s, limit 512 entries | `<cache>/available-versions/` |
| Provider timeout | 5 s interactive, 60 s during runs | (`AIUP_RUN_PROVIDER_TIMEOUT`) |
| Package-manager metadata | 900 s (like `brew-metadata.stamp`) | `<cache>/metadata/<manager>.stamp` |
| Release notes | per version, no expiry | `<cache>/release-notes/` |

- Every cache file is written to a temp file in the same folder and moved with `os.replace`. A cache is never trusted for a mutation: before changing a tool, the engine re-reads its installed version and channel live (macOS `mutation_authoritative_preflight`).

### 9.2 State, preferences, history and logs

`runtime/aiup/paths.py` returns:

```python
@dataclass(frozen=True)
class Dirs:
    config: Path       # preferences.json, channels.tsv
    data: Path         # generations, launcher, npm prefix, methods
    state: Path        # logs and history, notify-last, list-query, list-category, fzf-expanded
    cache: Path        # indexes, available-versions, release-notes, downloads, pycache
    runtime: Path      # TUI sessions, fzf socket (private, per user)

def dirs_for(platform_name: str, env: Mapping[str, str]) -> Dirs: ...
```

| Dir | Linux | Windows |
| --- | --- | --- |
| config | `${XDG_CONFIG_HOME:-~/.config}/aiup` | `%LOCALAPPDATA%\aiup\config` |
| data | `${XDG_DATA_HOME:-~/.local/share}/aiup` | `%LOCALAPPDATA%\aiup\data` |
| state | `${XDG_STATE_HOME:-~/.local/state}/aiup` | `%LOCALAPPDATA%\aiup\state` |
| cache | `${XDG_CACHE_HOME:-~/.cache}/aiup` | `%LOCALAPPDATA%\aiup\cache` |
| runtime | `$XDG_RUNTIME_DIR/aiup` when set and owned by the user with mode 700, else `<cache>/run` | `%LOCALAPPDATA%\aiup\cache\run` |

Generations live under `data/generations` (Linux keeps the macOS default `~/.local/share/aiup` for them). With `AIUP_STATE_DIR` set, the five dirs become `$AIUP_STATE_DIR/{config,data,state,cache,run}`. XDG values that are not absolute paths are ignored (XDG spec). Folders are created mode 700 on Linux; on Windows `%LOCALAPPDATA%` already has a per-user ACL. Files with private content (logs, preferences, exports) are created mode 600 on Linux. Symbolic-link state folders and files are refused, as the macOS Python helpers do (`Refusing symbolic-link preferences`).

File names and formats carry over unchanged: `preferences.json`, `channels.tsv`, `methods/<tool>`, `logs/update-YYYYmmdd-HHMMSS.<rand>` with `.json` (schema `aiup-run-v1`) and `.active` (pid), `notify-last.txt`, `list-query`, `list-category`, `list-selected`, `fzf-expanded`, `pnpm-store-prune.stamp`. Run retention: newest 20 completed runs (`AIUP_LOG_LIMIT`), active and recent runs protected (`run_history prune`). The `.active` pid check uses `Platform.pid_alive`.

### 9.3 JSON output

Same schemas, same field names, same `result` vocabulary as `docs/scripting.md`. Additive fields only, so v1 consumers keep working:

- top level: `"platform": "linux" | "windows"`;
- per tool: `"channel"` (the channel used or read).

No new `result` values: "needs sudo" and "needs Windows approval" are `deferred` with a `note`. The JSON goes to stdout, everything else to stderr.

### 9.4 Export and import

`aiup-export-v1` with these additive keys: `"platform"`, and `"packages": {"<manager>": ["name", ...]}` holding explicitly installed packages that no catalog entry covers (Linux and Windows equivalent of `homebrew.formulae` / `homebrew.casks`). Import on any platform applies `tools` and `preferences` as macOS does (unknown ids listed and skipped); it offers `packages` only for managers available here, and `homebrew` only on macOS or where Linuxbrew is available. The macOS `cmd_import` reads only `tools`, `homebrew` and `preferences`, so a Linux or Windows export still imports there.

### 9.5 Terminal, color and the TUI on each OS

- **Color:** ANSI 256-color like macOS, off with `NO_COLOR` or `--plain` or when the stream is not a terminal. `TERM=dumb` also turns it off.
- **Windows console:** at start, `term.enable()` sets `ENABLE_VIRTUAL_TERMINAL_PROCESSING` on stdout and stderr through `ctypes` (`GetConsoleMode` / `SetConsoleMode`); if that fails, aiup runs plain. It calls `SetConsoleOutputCP(65001)` and `SetConsoleCP(65001)` for the session and restores the old code pages at exit. Output streams are reconfigured to UTF-8 with replacement.
- **Glyphs:** row marks `●◐○◇◆`, `❯`, the rounded frame and the installed bar. `AIUP_ASCII=1` switches to `* ~ o ? !`, `>`, square frame and `#`. The TUI worker decides when to switch automatically (for example the legacy console host without a font that has the glyphs) and documents the rule.
- **fzf version:** the picker needs fzf 0.73.0 or newer (`tui/picker.py` `FZF_MINIMUM`). 0.73.0 is the release that exports `FZF_CURRENT_ITEM` to child processes. The other features are older: `--id-nth` (0.71), `--with-shell` and `FZF_POS` (0.51), `FZF_QUERY` (0.46), `transform` (0.45), `--listen-unsafe` (0.44), `FZF_API_KEY` (0.43), `transform-header` (0.40), `--track` and `FZF_PORT` (0.39). aiup refuses an older fzf with the minimum and the command that gets a newer one (`aiup only fzf` when the catalog offers fzf here) in the message, and `aiup list` falls back to the plain table. Distro fzf on stable releases can be older than that.
- **Bindings:** no binding takes a `{q}` or `{1}` placeholder, on either OS. `tui/fast.py` reads `FZF_QUERY` and `FZF_CURRENT_ITEM` from its environment, so typed text never passes through a shell. Windows: fzf runs the command through `cmd.exe /v:on/s/c`; the command line is the quoted interpreter path, `-I -S -B`, the quoted `fast.py` path and a fixed verb, and a path holding `%`, `!`, `^` or a quote is refused. Linux: fzf runs it with `--with-shell "sh -c"` and every word is shell-quoted.
- **fzf listen:** both OSes use `--listen-unsafe=127.0.0.1:0` with a random API key (`secrets.token_urlsafe(32)`) in fzf's `FZF_API_KEY`. The `load` and `resize` header bindings run the fast helper, which writes `$FZF_PORT` into the session folder once. Background prefetch posts its `reload` to `127.0.0.1:<port>` with the `x-api-key` header.
- **Updates states:** a pending update (`Latest.pending`, version unknown) is a normal Updates row with `unknown` as the available version and the note "An update is waiting; its version is not published." in its preview. A managed copy (`Latest.managed`) gets no Updates row and is not counted in the header; the tool's preview and `aiup preview TOOL` show the managed note on the available line.
- **Fast helper:** `tui/fast.py` imports nothing outside the stdlib and the session files it reads, so each keystroke costs one small Python start. `--timings` reports its time. Session folders hold the token, the owner pid and SHA-256 stamps of the row files (`tui_session_context_valid`).
- **Clipboard (`ctrl-y`):** Linux `wl-copy`, then `xclip -selection clipboard`, then `xsel -b`; Windows `Set-Clipboard` through `powershell -NoProfile` with the text on stdin (never in the command line). No clipboard tool: the key prints the URL.
- **Docs key:** `Platform.open_url`.

### 9.6 Notifications

Same text and same "only when the set of updates changed" rule as `cmd_notify` (`notify-last.txt`, `--always`). Text is never placed in command source:

- **Linux:** `notify-send --app-name=aiup -- TITLE BODY`. Without it, `gdbus call --session --dest org.freedesktop.Notifications --object-path /org/freedesktop/Notifications --method org.freedesktop.Notifications.Notify aiup 0 "" TITLE BODY [] {} 5000`. For cron and timers, when `DBUS_SESSION_BUS_ADDRESS` is unset and `$XDG_RUNTIME_DIR/bus` exists, aiup sets `unix:path=$XDG_RUNTIME_DIR/bus` for the child. Failure prints one line and exits 0, as on macOS.
- **Windows:** `powershell.exe -NoProfile -NonInteractive -EncodedCommand <fixed script>` with title and body passed in environment variables (`AIUP_NOTIFY_TITLE`, `AIUP_NOTIFY_BODY`). The fixed script loads `Windows.UI.Notifications` through WinRT in Windows PowerShell 5.1, escapes the text with `[Security.SecurityElement]::Escape`, and shows a toast under PowerShell's app id. Failure prints one line and exits 0.
- `notify` widens PATH for scheduled jobs before it looks anything up (`notify_path_setup`): `~/.local/bin`, aiup's npm bin, `~/.cargo/bin`, Go's bin dir, Linuxbrew's prefix; on Windows the aiup bin dir, `%USERPROFILE%\.local\bin`, the WinGet Links folder, scoop shims.

### 9.7 Trash

`Platform.trash(path) -> Path` moves one path and returns where it went; it never deletes permanently.

- **Linux:** freedesktop Trash spec. Home trash at `$XDG_DATA_HOME/Trash/{files,info}`. Write `info/<name>.trashinfo` (`[Trash Info]`, `Path=` percent-encoded absolute path, `DeletionDate=` local time `YYYY-MM-DDThh:mm:ss`) with `O_EXCL`, then rename into `files/<name>`, picking a unique name. If the path is on another filesystem than the home trash, use `gio trash` when present; otherwise refuse and tell the user, without deleting.
- **Windows:** Recycle Bin through `SHFileOperationW` with `FO_DELETE | FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI` via `ctypes`. If the volume has no Recycle Bin, refuse and tell the user.
- `--dry-run` prints `DRY-RUN: move to Trash: PATH`, as `move_to_trash` does.

---

## 10. Work packages

Rules for every worker: own only the files listed for your package; code against the interfaces in sections 5, 6, 7, 8 and 9 exactly as written, and report any interface change you need instead of making it; never commit or push; follow the zero-testing rule and the public copy style in `AGENTS.md`; no host names, private paths or account details in any file. Pass this unchanged to anyone you hand work to: "Don't write, add, or run tests of any kind: no test suites or files, fixtures, harnesses, lint/typecheck/build ladders, smoke runs, or installs done for testing. This includes repo check, drift, count, or link scripts, syntax checks, sample-input runs of scripts or hooks, and one-off verification loops. Validate like a senior reviewer instead: re-read the request, read the whole diff and the code it touches, reason through inputs, edge cases, error paths, and callers, and use the output the work itself already produces. Say what you reviewed and what review couldn't confirm."

### Wave A: eight packages in parallel

They depend on each other only through the interfaces pinned in this document.

| WP | Scope | Files owned |
| --- | --- | --- |
| **WP1 Core and catalog** | Data classes, version compare, config, paths, CLI parsing and dispatch (every command in section 2 routed to `aiup.commands.<module>.run(args, ctx) -> int`; modules not yet written return 1 with "not implemented yet"), catalog loader, grammar, export, provider base and registry, entry points. Seeds `categories.tsv` and `tool-meta.tsv` from the macOS functions named in 5.5. | `runtime/aiup_main.py`, `runtime/README.md`, `runtime/aiup/__init__.py`, `__main__.py`, `version.py`, `errors.py`, `model.py`, `versions.py`, `config.py`, `paths.py`, `cli.py`, `runtime/aiup/catalog/*`, `runtime/aiup/providers/__init__.py`, `runtime/aiup/providers/base.py`, `runtime/aiup/commands/__init__.py`, `catalog/categories.tsv`, `catalog/tool-meta.tsv`, `.gitattributes` |
| **WP2 Linux system providers** | pacman, AUR, apt, dnf, zypper, flatpak, snap, nix, Linuxbrew providers per 6.3 and 7.1 to 7.3, including `system_upgrade`, `metadata_refresh`, locks, `owns`. | `runtime/aiup/providers/linux_pacman.py`, `linux_aur.py`, `linux_apt.py`, `linux_dnf.py`, `linux_zypper.py`, `linux_flatpak.py`, `linux_snap.py`, `linux_nix.py`, `brew.py` |
| **WP3 Windows providers** | winget, scoop, choco, Appx per 6.3 and 7.4, including output parsing that survives localized and truncated winget tables (prefer `--id --exact` queries and machine-readable forms where they exist). | `runtime/aiup/providers/win_winget.py`, `win_scoop.py`, `win_choco.py`, `win_appx.py` |
| **WP4 Cross-platform providers** | npm (aiup prefix, provenance gate, allowed install scripts: port from `npm_install_aiup_latest`, `npm_provenance_gate`, `npm_allow_scripts_*`), pnpm, bun, uv, pipx, cargo, go, vendor, script (6.7). | `runtime/aiup/providers/npm.py`, `pnpm.py`, `bun.py`, `uv.py`, `pipx.py`, `cargo.py`, `go.py`, `vendor.py`, `script.py` |
| **WP5 Platform layer** | `Platform` protocol and the three implementations: dirs hookup, `which` with PATHEXT, `is_elevated`, `pid_alive`, `process_tree_has`, `kill_tree`, `notify`, `trash`, `open_url`, `copy_text`, distro info; `proc.run_read`, `proc.run_step`, `decode_output`; terminal setup. | `runtime/aiup/platform/*` |
| **WP6 Engine** | Context, channel resolution and policy, plan, run, lanes, privilege decisions, check data, reports and JSON, history, preferences, net, cache, release notes, and the small special-tool hook table (6.6). | `runtime/aiup/engine/*` |
| **WP7 TUI** | fzf picker, rows, headers, preview, session folder, fast helper, prefetch, listen setup, glyph sets, fzf minimum version. Port from `pick_catalog_tools`, `format_catalog_display`, `format_category_header`, `category_meter`, `tui_session_create`, `tui_fast_helper_render`, `tui_prefetch_*`. | `runtime/aiup/tui/*`, `runtime/aiup/commands/listing.py` |
| **WP8 Launcher, installers, release scripts** | Python launcher with `setup-path`, Linux and Windows installers with `--uninstall` / `-Uninstall`, `bump-version`, `stamp-runtime`, `publish-release` extension. | `runtime/launcher/aiup_launcher.py`, `linux/install-aiup`, `windows/install-aiup.ps1`, `scripts/bump-version`, `scripts/stamp-runtime`, `scripts/publish-release` |

### Wave B: after Wave A lands

| WP | Scope | Files owned |
| --- | --- | --- |
| **WP9 Commands** | Every command module except `listing.py`: update, check, plan, remove, explain, doctor, overview (attention, owners, duplicates), coverage, welcome, preferences commands, channel, system, export and import, notify, docs, history and logs, inventory, catalog, project. Each ports the matching `cmd_*` function. | `runtime/aiup/commands/*` except `__init__.py` and `listing.py` |
| **WP10 Detection** | Inventory merge, detection sources (PATH, desktop entries, registry Uninstall keys), `owner_of`, `actions_for`, using `docs/research/system-detection-2026-11-02.md`. | `runtime/aiup/detect/*` |
| **WP11 Catalog data, docs and site** | Merge the research TSVs into `catalog/platforms.tsv` (format 5.2, defaults filled where the research names the fastest channel); extend `sync-public-docs` (5.6); write `linux/README.md`, `windows/README.md`; update `docs/install.md`, `docs/privacy.md` (state paths per OS), `docs/scripting.md` (additive JSON fields), `docs/status.md`, `docs/README.md` (link this doc), README; edit the release rule in `AGENTS.md` (4.4). No support claims and no `showcase.json` platform change until the orchestrator confirms a reviewed release. | `catalog/platforms.tsv`, `scripts/sync-public-docs`, `linux/README.md`, `windows/README.md`, `docs/install.md`, `docs/privacy.md`, `docs/scripting.md`, `docs/status.md`, `docs/README.md`, `README.md`, `AGENTS.md` |

### Wave C: review and release (orchestrator)

Fresh review rounds per package against this spec, then `scripts/bump-version`, CHANGELOG, `scripts/stamp-runtime`, commit, push, `scripts/publish-release`, commit and push `macos/release`. The orchestrator owns `CHANGELOG.md`, `macos/aiup` and `macos/catalog/manifest.tsv` version lines, `runtime/FILES`, `macos/release` and all git. A first real run on each OS (Arch, a Debian-family distro, Fedora, Windows 11, Windows Server) is an owner decision outside the zero-testing rule for workers.

### Dependency order

```
WP1 ──┬─> WP2, WP3, WP4 (import providers/base, model)
      ├─> WP5 (import model, paths)
      ├─> WP6 (import model, providers/base, platform/base)
      ├─> WP7 (import catalog, engine/context, platform/term)
      └─> WP8 (reads version.py and FILES rules only)
WP1..WP8 ──> WP9 (commands call engine, tui, detect)
WP5, WP6 ──> WP10
WP1, WP8 ──> WP11 (export format, release rule)
```

---

## 11. Open questions

1. **PowerShell shim precedence.** When `aiup.ps1` and `aiup.cmd` sit in the same PATH folder, which one does Windows PowerShell 5.1 and pwsh 7 run for a bare `aiup`? WP8 settles this from Microsoft's command-precedence documentation. If `.cmd` wins, Ctrl-C in PowerShell can show cmd's "Terminate batch job (Y/N)?" after aiup exits; aiup's exit code and results are unaffected.
   Settled 2026-11-03: PowerShell runs `aiup.ps1` before `aiup.cmd` in the same folder. `windows/install-aiup.ps1` writes `aiup.ps1` only when every installed PowerShell may run local scripts; otherwise PowerShell uses `aiup.cmd`.
2. **fzf minimum version** (9.5). WP7 picks it from fzf's changelog. Distros with an older fzf need another channel for it, which the catalog data has to offer.
   Settled 2026-11-03: fzf 0.73.0 (`FZF_CURRENT_ITEM`), per 9.5; an older fzf gets the plain list and the command that installs a newer one.
3. **Python on a fresh Windows install.** WP8 picks the winget package id for the installer's optional Python install (the traditional `Python.Python.3.x` packages or the newer Python install manager) from winget's official source.
   Settled 2026-11-03: `Python.Python.3.14` from the `winget` source, with `--scope user` (or `machine` with `-AllUsers`), asked first and only in an interactive session.
4. **openSUSE names.** Whether `linux_dnf` names are safe for zypper or a separate `linux_zypper` column is needed. Adding a column later is backward compatible only if it goes before `linux_default`; decide before WP11 writes the file.
   Settled 2026-11-03: no `linux_zypper` column in this version. The zypper provider covers inventory, ownership and `system_upgrade`; catalog installs on openSUSE use the cross-platform, flatpak, snap or brew channels. A zypper column can be added later before `linux_default`.
5. **winget output.** Whether a machine-readable winget list exists in the winget versions aiup supports, or WP3 must parse the table. The detection research doc may settle this.
   Settled 2026-11-03: machine-readable first: `Get-WinGetPackage` when the `Microsoft.WinGet.Client` module is installed, else `winget export --include-versions` (JSON) for the inventory. The update list and single-package reads parse the `winget upgrade` and `winget list --id ID --exact` tables by column position, never by translated header words.
6. **Desktop apps that update themselves** on Linux and Windows (Electron editors and chat apps). macOS reports them as `self-updated` (`cask_effective_version`). WP3 and WP6 need the same rule for winget and Appx so aiup never installs an older build over a newer one.
   Settled 2026-11-03: aiup never passes `--force` or `--version` to winget, and winget refuses a downgrade; `explain_exit` reports winget's "newer build already installed" exit as `self-updated`. Microsoft Store copies (winget `msstore` and Appx) are `Latest.managed`, reported as skipped with "managed by Microsoft Store".
