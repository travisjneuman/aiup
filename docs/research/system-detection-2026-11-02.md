# System detection research: recognizing everything installed (2026-11-02)

Research for the Python 3 cross-platform runtime (Linux and Windows) and for gaps in the current macOS runtime. The goal: aiup recognizes anything installed on an end-user machine, says who owns it, and can map it to an update and remove action.

Status: research only. Nothing here is implemented. Timings marked "measured" come from read-only runs on a few real test machines (an Arch desktop with about 1,000 packages, Windows 11 and Windows Server machines, a macOS machine) on 2026-11-02. Timings marked "estimate" were not measured. Example output below is generic and invented to show the shape; no real inventory is copied here.

Related: [command-insights.md](../command-insights.md), [privacy.md](../privacy.md), [homebrew.md](../homebrew.md). The runtime design lives in `docs/cross-platform-design.md`.

## Contents

1. [What macOS aiup does today](#1-what-macos-aiup-does-today)
2. [Ground rules for every scanner](#2-ground-rules-for-every-scanner)
3. [Proposed inventory record](#3-proposed-inventory-record)
4. [Linux sources](#4-linux-sources)
5. [Windows sources](#5-windows-sources)
6. [macOS gaps](#6-macos-gaps)
7. [Cross-platform language and tool managers](#7-cross-platform-language-and-tool-managers)
8. [Editors, IDEs, models, containers, agent integrations](#8-editors-ides-models-containers-agent-integrations)
9. [Vendor self-updating tools](#9-vendor-self-updating-tools)
10. [Which manager owns an executable on PATH](#10-which-manager-owns-an-executable-on-path)
11. [Duplicate and conflict detection](#11-duplicate-and-conflict-detection)
12. [Version strings, localization, and other cross-cutting pitfalls](#12-version-strings-localization-and-other-cross-cutting-pitfalls)
13. [Prioritized recommendations and scan budget](#13-prioritized-recommendations-and-scan-budget)
14. [What this research could not confirm](#14-what-this-research-could-not-confirm)

## 1. What macOS aiup does today

From `macos/aiup` (`scan_inventory_index`, `inventory_scan_*`, `path_insights`, `source_count_of`, `duplicates_of`, `print_doctor`, `cmd_coverage`, `cmd_explain`):

- **Catalog presence:** `scan_installed_tools` checks each catalog entry with `tool_is_present`, after one Homebrew cache load (`brew list --formula` / `--cask`).
- **Detected inventory** (`inventory-index.tsv`, cached five minutes, fingerprinted by source mtimes):
  - App bundles in `/Applications` and `~/Applications` (Info.plist `CFBundleIdentifier`, display name, short version).
  - Global npm packages for the aiup prefix and the system prefix (`npm list --global --depth=0 --json`).
  - uv tools (`uv tool list`, text parsed on ` v`).
  - Executables in `~/.local/bin`, the aiup npm bin, `~/.cargo/bin`, `~/.grok/bin`, `/usr/local/bin`, and every PATH directory except system and Homebrew prefixes.
- **Static enrichment** (`path_insights`): resolves symlinks, then reads package.json ancestry (npm owner), parent `.app` bundle, Python.framework plists, uv Python paths, a few vendor layouts, installer receipts for `/usr/local/bin/node`, and `~/.cargo/.crates.toml` for path-built crates. It never runs an unfamiliar binary.
- **Duplicates** (`duplicates_of`): a per-tool count of install channels (`source_count_of`) plus `which -a` unique resolved paths, with allowlisted wrapper cases (aiup Codex wrapper, Grok alias, Homebrew Node trio).
- **Coverage** (`cmd_coverage`): catalog tools present versus supported, plus "detected only; updater not reviewed" rows.

What it misses on macOS is listed in [section 6](#6-macos-gaps). The rules in section 2 carry its good habits across to Linux and Windows.

## 2. Ground rules for every scanner

1. **Read files before running commands.** Most package managers keep their database as plain files. Parsing them in-process avoids interpreter startup (npm and PowerShell spawn costs 300 to 900 ms each, measured) and avoids side effects.
2. **Never execute an unfamiliar binary to learn its version.** Use metadata: package databases, manifests, PE version resources, Go build info, symlink targets, file names. The current runtime already follows this rule; keep it.
3. **No network during a scan.** Several "list" commands quietly go online (section 12). Outdated checks belong to a separate, explicit step.
4. **No privilege during a scan.** Every source below can be read as a normal user, except the Docker socket (group membership) and a few macOS background-task records.
5. **Run sources in parallel with timeouts.** Each source is independent. Skip a source in under 1 ms when its directory or binary is absent.
6. **Store commands as argv lists, never shell strings.** Uninstall strings from the Windows registry are untrusted text. Parse them into argv and show them before running.
7. **Read secrets-bearing files selectively.** Agent config files hold API keys (section 8.5). Read only names, commands, and package specs, never `env` or headers.
8. **Cap file reads.** Keep the current 1 MiB style limits for JSON and manifests, and 64 KiB for script headers.

## 3. Proposed inventory record

The macOS TSV has `category, state, id, label, version, source, path`. The cross-platform record needs a few more fields so update and remove can be mapped without guessing:

| Field | Example | Notes |
|---|---|---|
| `id` | `pkg:pacman:git`, `win:arp:HKLM64:{GUID}`, `npm:system:@scope/cli` | Stable per source; unique key for caching and dedupe. |
| `name` | `git` | Display name from the source. |
| `identity` | `git` | Canonical tool identity from an alias table; used for duplicate grouping. |
| `version` | `2.50.1-1` | Raw string from the source. Never normalized in storage. |
| `source` | `pacman`, `winget`, `arp`, `scoop`, `npm`, `path` | The channel that owns it. |
| `scope` | `system`, `user`, `container` | Drives privilege for actions. |
| `paths` | install dir, binaries | Resolved paths, deduped. |
| `evidence` | `pacman -Qo`, `symlink target`, `package.json ancestry` | Why we believe the owner. |
| `update` | `["pacman","-S","git"]` | argv, or empty when inspect-only. |
| `remove` | `["pacman","-R","git"]` | argv, or empty when inspect-only. |
| `needs_admin` | `true` | Root or UAC required for actions. |
| `self_updates` | `true` | The app updates itself; aiup should not fight it. |
| `confidence` | `exact`, `strong`, `heuristic` | Only `exact` and `strong` should offer one-key actions. |

## 4. Linux sources

Run every command below with `LC_ALL=C` so labels and messages are not translated.

### 4.1 pacman (Arch, Manjaro, EndeavourOS, CachyOS, SteamOS)

- **List:** `pacman -Q` prints `name version` per line (measured 16 ms for 1,000 packages). `pacman -Qqe` lists explicitly installed names (25 ms). `expac -Q '%n\t%v\t%r'` gives tab-separated name, version, repo when expac is installed (13 ms).
- **Direct read (fastest):** `/var/lib/pacman/local/<name>-<version>/desc` holds `%NAME%`, `%VERSION%`, `%DESC%`, `%URL%`, `%REASON%` (absent or `0` means explicit, `1` means dependency), `%INSTALLDATE%`. The sibling `files` file lists owned paths. The parent directory mtime is a good cache fingerprint.
- **Details:** `pacman -Qi <name>` gives `Name : value` blocks. Labels are translated unless `LC_ALL=C`.
- **Foreign (AUR or manual) packages:** `pacman -Qm` / `-Qqm` (measured 220 to 240 ms, because it loads the sync databases). A foreign package installed with an AUR helper is owned by that helper if `yay` or `paru` exists.
- **Owner of a file:** `pacman -Qo /usr/bin/git` prints `/usr/bin/git is owned by git 2.x-1` (42 ms). It accepts many paths in one call; batch them. `pacman -Qoq` prints only names.
- **Update / remove:** `sudo pacman -S <name>` (updates one package; partial upgrades are unsupported on Arch, so the safe "update" is `sudo pacman -Syu`), `sudo pacman -Rs <name>`. AUR: `yay -S <name>` or `paru -S <name>` (no sudo; the helper elevates).
- **Pitfalls:** `yay -Qua` / `paru -Qua` query the AUR web API (measured 385 ms with network). Never run them in a scan. Versions are `epoch:pkgver-pkgrel`; compare with `vercmp`. Immutable variants (SteamOS) have a read-only root; mark actions unavailable.

### 4.2 dpkg and apt (Debian, Ubuntu, Mint, Pop!_OS)

- **List:** `dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\t${db:Status-Abbrev}\n'`. Keep rows whose status starts with `ii`. Estimate: 100 to 300 ms for 2,000 packages.
- **Direct read:** `/var/lib/dpkg/status` is a set of RFC 822 stanzas (`Package:`, `Status:`, `Version:`, `Architecture:`). Parse in-process; fingerprint by its mtime.
- **Manual versus automatic:** `/var/lib/apt/extended_states` stanzas with `Auto-Installed: 1`, or `apt-mark showmanual`.
- **Owner of a file:** `dpkg -S /path` (accepts several paths). It scans `/var/lib/dpkg/info/*.list` and can take 200 ms or more; for a handful of PATH directories, build a map once from those `.list` files.
- **Update / remove:** `sudo apt-get install --only-upgrade <pkg>`, `sudo apt-get remove <pkg>`.
- **Pitfalls:** on merged-`/usr` systems a file may be registered as `/bin/x` while PATH resolves `/usr/bin/x`. Query both. `apt list --installed` warns that its CLI is unstable; avoid it for parsing. Versions are `epoch:upstream-revision` with `~` sorting before everything; compare with `dpkg --compare-versions`.

### 4.3 rpm, dnf, zypper (Fedora, RHEL, openSUSE)

- **List:** `rpm -qa --qf '%{NAME}\t%{EPOCHNUM}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\t%{VENDOR}\n'` (estimate 150 to 500 ms). There is no supported direct file read; the rpmdb is SQLite with binary headers.
- **Repo of origin:** `dnf repoquery --installed --qf '%{name}\t%{from_repo}\n'` (dnf5 accepts `--queryformat`). Add `-C` (cache only) so it does not refresh metadata. Estimate 0.5 to 2 s; cache it. User-requested packages: `dnf repoquery --userinstalled`.
- **openSUSE:** list with `rpm`; repo with `zypper --no-refresh --xmlout search --installed-only --details`. Without `--no-refresh`, zypper may refresh repositories.
- **Owner of a file:** `rpm -qf --qf '%{NAME}\n' /path` (many paths per call).
- **Update / remove:** `sudo dnf upgrade <pkg>` / `sudo dnf remove <pkg>`; `sudo zypper update <pkg>` / `sudo zypper remove <pkg>`.
- **Pitfalls:** Fedora Atomic (Silverblue, Kinoite, Bazzite) and openSUSE MicroOS are image-based. `rpm -qa` lists the base image too. Layered packages come from `rpm-ostree status --json` (`deployments[0].requested-packages`); actions are `rpm-ostree install|uninstall` and need a reboot. `gpg-pubkey` pseudo packages appear in `rpm -qa`; skip them.

### 4.4 apk (Alpine, postmarketOS)

- **List:** `apk info -v` (`name-version-rrel`) or `apk list --installed` (`name-ver arch {origin} (license) [installed]`).
- **Direct read:** `/lib/apk/db/installed`, stanzas with `P:` name, `V:` version, `F:` directory and `R:` file lines.
- **Explicit set:** `/etc/apk/world`.
- **Owner:** `apk info --who-owns /path`.
- **Update / remove:** `apk add -u <pkg>`, `apk del <pkg>` (root).
- **Pitfall:** `name-version` splitting: the version starts at the last `-` that is followed by a digit, before `-r<n>`.

### 4.5 xbps (Void)

- **List:** `xbps-query -l` prints `ii name-1.2.3_1 description`. Manual set: `xbps-query -m`.
- **Owner:** `xbps-query -o /path`.
- **Update / remove:** `xbps-install -u <pkg>`, `xbps-remove <pkg>` (root).
- **Pitfall:** version is everything after the last `-`, with `_revision`.

### 4.6 Portage (Gentoo), briefly

- **Direct read:** `/var/db/pkg/<category>/<name>-<version>/`. `qlist -Iv` (portage-utils) lists them; `qfile /path` finds the owner. Update `emerge -u <atom>`, remove `emerge --deselect <atom>` then `--depclean`. Compilation makes updates slow; label them.

### 4.7 Flatpak

- **List:** `flatpak list --app --columns=application,name,version,branch,arch,origin,installation`. Add `--user` or `--system` to limit scope. Estimate 100 to 300 ms. Without `--app` it also lists runtimes.
- **Direct read:** `/var/lib/flatpak/app/<id>/<arch>/<branch>/active/` (system) and `~/.local/share/flatpak/app/...` (user). Version: `active/files/share/metainfo/<id>.metainfo.xml` (first `<release version=…>`); origin remote: `active/deploy` or `metadata`.
- **Launchers:** `/var/lib/flatpak/exports/bin/<id>` and `~/.local/share/flatpak/exports/bin/<id>`; desktop files under the matching `exports/share/applications`.
- **Update / remove:** `flatpak update -y [--user|--system] <id>`, `flatpak uninstall -y [--user|--system] <id>`. System changes go through polkit.
- **Pitfalls:** the Version column is often empty (apps without metainfo releases); fall back to the commit. The same app can be installed in both user and system scope; that is a duplicate. Custom installations under `/etc/flatpak/installations.d/` add more roots.

### 4.8 Snap

- **List:** `snap list` (columns `Name Version Rev Tracking Publisher Notes`). No JSON flag. `--all` adds disabled revisions; skip them. Runs without root.
- **Direct read:** `/snap/<name>/current/meta/snap.yaml` (`name`, `version`, `apps`). The mount root is `/var/lib/snapd/snap` on Fedora and Arch.
- **Launchers:** `/snap/bin/<name>` or `<name>.<app>`, symlinks to `/usr/bin/snap`.
- **Update / remove:** `sudo snap refresh <name>`, `sudo snap remove <name>`. Snaps refresh themselves on a schedule; mark `self_updates`.
- **Pitfall:** column widths vary; split on runs of two or more spaces. Publisher may carry a verified-mark symbol.

### 4.9 Homebrew on Linux (linuxbrew)

- **Prefix:** `/home/linuxbrew/.linuxbrew`, or `~/.linuxbrew` for older installs.
- **Direct read:** `Cellar/<formula>/<version>/INSTALL_RECEIPT.json` (`installed_on_request`, `source.tap`). This avoids `brew` (macOS measured `brew list --versions` 407 ms, `brew info --json=v2 --installed` 963 ms).
- **Update / remove:** `brew upgrade <f>`, `brew uninstall <f>`. Set `HOMEBREW_NO_AUTO_UPDATE=1` for anything run during a scan. No casks on Linux. Reuse the macOS Homebrew adapter.

### 4.10 Nix and Guix

- **Nix profile:** `nix profile list --json`. The docs describe the text fields (Name, Flake attribute, Original and Locked flake URL, Store paths) but not the JSON keys; confirm on a Nix machine before parsing. Legacy: `nix-env -q --json --out-path`. Update `nix profile upgrade <name>`, remove `nix profile remove <name>`.
- **Paths:** `~/.nix-profile/bin`, `/run/current-system/sw/bin` (NixOS). Every binary resolves to `/nix/store/<32-char hash>-<name>-<version>/bin/…`; parse name and version from the store directory (version starts at the first `-` followed by a digit, heuristic).
- **Declarative installs:** NixOS system packages and home-manager (`home-manager packages`) come from config. Mark inspect-only and point to the config.
- **Guix:** `guix package --list-installed` prints tab-separated name, version, output, store path (estimate 0.5 to 1.5 s, Guile startup). Update `guix upgrade <name>`, remove `guix remove <name>`.

### 4.11 AppImage

- **Where:** `~/Applications`, `~/AppImages` (Gear Lever), `~/.local/bin`, `/opt`, and any `Exec=` in desktop files ending in `.AppImage`. Scanning `~/Downloads` should be opt-in.
- **Detect without running:** ELF file with bytes 8 to 10 equal to `A I 0x02` (type 2) or `A I 0x01` (type 1).
- **Version:** file name pattern (`Name-1.2.3-x86_64.AppImage`); the embedded desktop file's `X-AppImage-Version` needs a squashfs read, skip it in a scan.
- **Update info:** the ELF section `.upd_info` holds a string such as `gh-releases-zsync|owner|repo|latest|*.zsync` or a zsync URL. It can be read from the file without executing it, and maps to AppImageUpdate or to a GitHub release check.
- **AppImageLauncher:** integrated files live in `~/Applications` with desktop files named `appimagekit_<hash>-<name>.desktop`.
- **Update / remove:** `appimageupdatetool <file>` when update info exists, else manual. Remove: delete the file plus its desktop file and icons.
- **Pitfall:** never call `--appimage-version` or `--appimage-updateinformation`; both run the image.

### 4.12 Unmanaged binaries (`~/.local/bin`, `~/bin`, `/usr/local/bin`, `/opt`)

- **Walk:** `os.scandir` on each directory; keep regular executable files and symlinks. Resolve with `os.path.realpath`.
- **Classify by resolved path** (cheap, before any package query): mise installs, npm prefixes, cargo, Go bin, uv tools, pipx venvs, vendor version dirs (section 9), Nix store, Flatpak exports, distrobox exports.
- **Classify by content** (first 64 KiB): shebang plus `exec mise x`, `asdf exec`, `distrobox-enter` or the `# distrobox_binary` marker, `flatpak run`, `deno run`.
- **Static version sources:** Go build info (magic `\xff Go buildinf:`; or run `go version -m <file>`, which reads and does not execute). Rust binaries built with cargo-auditable carry a `.dep-v0` section.
- **`/opt/<app>`:** look for `product-info.json` (JetBrains), `resources/app.asar` plus `package.json` (Electron), `.desktop` files that point into it.
- **Remove:** only offer "delete file" for a single file the user placed, after showing its path. Mark everything else inspect-only.

### 4.13 Desktop entries

- **Dirs:** `$XDG_DATA_HOME/applications` (default `~/.local/share/applications`), then `<dir>/applications` for each entry of `$XDG_DATA_DIRS` (default `/usr/local/share:/usr/share`). Flatpak and Snap add `…/flatpak/exports/share` and `/var/lib/snapd/desktop`.
- **Parse:** `[Desktop Entry]` `Type=Application`, `Name`, `Exec`, `TryExec`, `NoDisplay`, `Hidden`, `X-Flatpak`, `X-SnapInstanceName`, `X-AppImage-Version`. Strip field codes (`%U`, `%f`) and leading `env VAR=x` from `Exec`.
- **Cost:** measured about 90 files listed in well under 10 ms; parsing is estimated under 30 ms.
- **Pitfalls:** the same desktop-file ID in an earlier directory overrides later ones. Localized keys (`Name[de]`) exist; use the unlocalized `Name` for matching. `Hidden=true` in the user dir means the user removed it.

### 4.14 systemd user services (background items)

- **List:** `systemctl --user list-unit-files --type=service --state=enabled --no-pager --plain --no-legend` (measured 84 ms). Or read `~/.config/systemd/user/`, `/etc/systemd/user/`, `/usr/lib/systemd/user/` plus `*.wants/` symlinks for enabled state. Timers are similar (`--type=timer`).
- **Owner:** units under `/usr/lib` belong to a package (`pacman -Qo`, `dpkg -S`). Units under `~/.config` were made by the user or an app; resolve `ExecStart=` to find the app.
- **Actions:** `systemctl --user disable --now <unit>`. Only offer deleting a unit file the user created.
- This maps to the showcase "background" fact. Do not report a count from this scan without review (see AGENTS.md).

### 4.15 distrobox and toolbox

- **List:** `distrobox list --no-color` (calls podman or docker; does not start containers). Or `podman ps -a --format json --filter label=manager=distrobox`. Toolbox containers carry the label `com.github.containers.toolbox=true`.
- **Exports on the host:** desktop files `~/.local/share/applications/<container>-<app>.desktop` with `distrobox-enter` in `Exec`, and binaries in `~/.local/bin` containing `# distrobox_binary`.
- **Packages inside containers:** out of scope; reading them would start the container.
- **Actions:** remove an export with `distrobox enter <c> -- distrobox-export --app <app> --delete`. `distrobox rm` deletes a whole container and its data; never a routine action.

## 5. Windows sources

The fastest Windows path is Python reading the registry and file system directly (`winreg`, `os.scandir`, PE resource parsing via `ctypes`). Each `powershell.exe` launch costs several hundred ms before doing any work. If PowerShell is needed, use one process for everything it must answer.

### 5.1 Registry Uninstall keys (Programs and Features)

- **Keys:**
  - `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` (64-bit view)
  - `HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall` (32-bit view; in Python open the first key with `KEY_WOW64_32KEY`)
  - `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall` (per-user installs; HKCU is not split by bitness)
- **Values:** `DisplayName`, `DisplayVersion`, `Publisher`, `InstallLocation`, `InstallDate` (`yyyymmdd`), `UninstallString`, `QuietUninstallString`, `ModifyPath`, `DisplayIcon`, `NoRemove`, `SystemComponent`, `WindowsInstaller`, `ParentKeyName`, `ReleaseType`, `EstimatedSize`, `URLInfoAbout`, `URLUpdateInfo`.
- **Cost:** PowerShell `Get-ItemProperty` over all three measured 600 to 650 ms for 245 to 373 entries. Plain key enumeration measured 50 ms. Python `winreg` in-process is estimated under 150 ms.
- **Filter:** skip `SystemComponent=1`, entries with `ParentKeyName` or `ReleaseType` (updates, hotfixes), and entries without `DisplayName`. On two test machines, 58% and 74% of entries had `SystemComponent=1`. Driver packages (`Windows Driver Package - …`) can be kept in an "other" group.
- **Installer type from evidence:**
  - `WindowsInstaller=1` and key name is a `{GUID}`: MSI. Remove `msiexec /x {GUID} /qn /norestart`.
  - Key ends in `_is1`: Inno Setup. Quiet flags `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`.
  - `Uninstall <App>.exe` or `uninstall.exe`: NSIS or electron-builder. Quiet flag `/S` (electron-builder adds `/allusers` or `/currentuser`, seen in real strings).
  - `Update.exe --uninstall`: Squirrel (Discord, Slack style). Add `-s`.
- **Update:** the registry has no update command. Map to winget, choco, scoop, or the app's own updater; otherwise "check vendor".
- **Privilege:** reading needs none. HKLM uninstall needs elevation (UAC). HKCU uninstall does not.
- **Pitfalls:** only about 9 to 15% of entries had `QuietUninstallString` on the test machines. `UninstallString` is often unquoted with spaces in the path; parse carefully into argv and never pass it through a shell. `DisplayName` often includes the version. `DisplayVersion` formats vary (`08/08/2013 2.0.0.3` was seen on a driver). Values can be `REG_EXPAND_SZ`; expand them. The same product can appear in both 64-bit and 32-bit views. Registry key last-write time (`winreg.QueryInfoKey(key)[2]`) works as a cache fingerprint.

### 5.2 winget

- **Availability:** `winget` is an App Execution Alias of App Installer, registered per user. It was present on Windows 11 (`winget --version` 219 ms) and returned nothing over SSH on Windows Server. It is also missing for SYSTEM and before a user's first logon. Treat it as optional.
- **List (text):** `winget list --disable-interactivity --accept-source-agreements` (measured 2.06 s, about 165 lines). `--source winget` limits to source-matched rows (0.9 s). Columns: `Name Id Version Available Source`.
- **Ids tell the origin:** a real package id (`Vendor.App`) with `Source` `winget` or `msstore`; `ARP\Machine\X64\<key>`, `ARP\Machine\X86\<key>`, `ARP\User\X64\<key>` for registry entries with no source match; `MSIX\<PackageFullName>` for packaged apps.
- **List (JSON):** `winget export -o <file> --include-versions --disable-interactivity --accept-source-agreements`. Shape:

  ```json
  {
    "$schema": "https://aka.ms/winget-packages.schema.2.0.json",
    "CreationDate": "…",
    "Sources": [
      {
        "SourceDetails": {"Name": "winget", "Identifier": "…", "Argument": "https://…", "Type": "Microsoft.PreIndexed.Package"},
        "Packages": [{"PackageIdentifier": "Vendor.App", "Version": "1.2.3"}]
      }
    ],
    "WinGetVersion": "1.x"
  }
  ```

  Export only includes packages it could match to a source; it warns about the rest. Combine it with the registry scan to cover everything. It needs a temp file (keep it under 1 MiB and delete it).
- **PowerShell module:** `Microsoft.WinGet.Client` (`Get-WinGetPackage`) returns objects with `Name`, `Id`, `InstalledVersion`, `IsUpdateAvailable`, `Source`, `AvailableVersions`. It was not installed on either Windows test machine; never assume it. Use it when present because it avoids table parsing.
- **Update / remove:** `winget upgrade --id <Id> --exact --silent --accept-package-agreements --accept-source-agreements`; `winget uninstall --id <Id> --exact --silent`. winget can also uninstall listed `ARP\…` and `MSIX\…` ids.
- **Network:** `winget list` correlates with source indexes and fills `Available`; it may refresh a stale source cache. Treat it as a network source and cache its result (a day is reasonable).
- **Pitfalls:** table headers and messages are localized. Column widths follow the console width; over SSH (no console) columns were about 90 characters wide, and in narrow consoles names are truncated with `…`. East Asian wide characters break fixed-width slicing. A spinner (`\r-\|/`) can precede output. Set `[Console]::OutputEncoding` to UTF-8 or decode as UTF-8 in Python. Exit codes are HRESULT-style (`0x8A15…`). Parse by finding column start offsets from the dashed separator line, never by splitting on spaces.

### 5.3 MSIX / Appx (Microsoft Store and packaged apps)

- **PowerShell:** `Get-AppxPackage` (measured 190 to 360 ms, 42 to 118 packages) with `Name`, `Version`, `PackageFullName`, `PackageFamilyName`, `SignatureKind`, `IsFramework`, `NonRemovable`, `InstallLocation`. Keep `SignatureKind` `Store` or `Developer` with `IsFramework=False`; skip `System` (on the test machines: 4 to 27 Store, 2 to 14 Developer, 30 to 51 System). In PowerShell 7 the Appx module may need `Import-Module Appx -UseWindowsPowerShell` on older 7.x releases.
- **Registry (no PowerShell, estimate):** `HKCU\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages\<PackageFullName>` with `DisplayName` (often an `ms-resource:` reference) and `PackageRootFolder`. `PackageFullName` is `Name_Version_Arch_ResourceId_PublisherId`, so name and version parse from the key name. Confirm before relying on it.
- **Update / remove:** Store updates itself; winget can target `msstore` ids. Remove with `Remove-AppxPackage <PackageFullName>` (per user). `NonRemovable=True` means inspect-only.

### 5.4 Scoop

- **Detect:** `$env:SCOOP` (default `%USERPROFILE%\scoop`) and `$env:SCOOP_GLOBAL` (default `%ProgramData%\scoop`).
- **Direct read:** `apps\<app>\current\manifest.json` (`version`) and `apps\<app>\current\install.json` (`bucket`, `architecture`). `current` is a junction to the version directory.
- **CLI:** `scoop export` prints JSON (`{"buckets":[…],"apps":[{"Name","Version","Source","Updated","Info"}]}`); `scoop list` prints PowerShell objects as a table. Scoop is a PowerShell script, so each call pays PowerShell startup.
- **Shims:** `shims\<name>.exe` plus `shims\<name>.shim`, a text file with `path = "C:\…\apps\<app>\current\…"`. Also `.cmd` and `.ps1` shims.
- **Update / remove:** `scoop update <app>`, `scoop uninstall <app>`. Global apps need admin. `scoop status` runs git fetches (network).

### 5.5 Chocolatey (v2)

- **CLI:** `choco list --limit-output` prints `id|version`. In v2 `list` is local only (measured on 2.7.4: it returned installed packages including `chocolatey` itself). v1 needed `--local-only`. Slow: `choco --version` alone measured 1.3 to 1.6 s and `choco list` 1.9 to 2.6 s.
- **Direct read (fast):** `$env:ChocolateyInstall` (default `C:\ProgramData\chocolatey`) `\lib\<id>\<id>.nuspec`, XML with `<id>` and `<version>`.
- **Shims:** `\bin\<name>.exe` (shimgen). The target is not stored in a text file; match by the `lib\<id>\tools\` contents.
- **Update / remove:** `choco upgrade <id> -y`, `choco uninstall <id> -y` (admin).
- **Pitfalls:** meta packages: `git` depends on `git.install`; group `.install`, `.portable`, and the base id as one tool. Packages that run a vendor installer also create a registry Uninstall entry, so the same app shows up twice; dedupe (section 11).

### 5.6 Start Menu shortcuts

- **Dirs:** `%ProgramData%\Microsoft\Windows\Start Menu\Programs` and `%APPDATA%\Microsoft\Windows\Start Menu\Programs`, recursive `*.lnk` (measured 21 ms for 184 shortcuts).
- **Target:** parse the Shell Link format (MS-SHLLINK `LinkInfo` local base path) in Python, or use `WScript.Shell` COM.
- **Use:** finds portable apps with no registry entry. Map target path to an ARP `InstallLocation` or a manager directory.
- **Pitfalls:** MSI "advertised" shortcuts carry a Darwin descriptor and no path. Store apps point to `shell:AppsFolder`.

### 5.7 PATH executables and App Execution Aliases

- **PATH:** the process PATH plus the persistent values `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment\Path` and `HKCU\Environment\Path` (`REG_EXPAND_SZ`). Comparing them is the Windows version of the macOS "persistent PATH likely" check. Measured: 44 PATH dirs, about 1,000 `.exe/.cmd/.bat/.ps1` files, 358 ms in PowerShell; Python `os.scandir` is estimated well under that.
- **Resolution order:** directory order, then `PATHEXT` order. npm creates `name`, `name.cmd`, `name.ps1` triples (seen in `%APPDATA%\npm`); group them.
- **App Execution Aliases:** `%LOCALAPPDATA%\Microsoft\WindowsApps\*.exe` (51 entries measured, 7 ms). They are zero-byte reparse points (tag `IO_REPARSE_TAG_APPEXECLINK`, `0x8000001B`). The reparse data holds the package family name, app id, and target exe; read it with `DeviceIoControl(FSCTL_GET_REPARSE_POINT)` via `ctypes`. In Python, `os.lstat(p).st_reparse_tag` identifies them.
- **Pitfall:** `python.exe` and `python3.exe` in WindowsApps may be Store installer stubs that open the Microsoft Store. Never run them.
- **Version without running:** PE `VERSIONINFO` (`FileVersion`, `ProductVersion`, `CompanyName`, `ProductName`) via `GetFileVersionInfoW`. Example: the Claude Code native `claude.exe` reports its release as `FileVersion` (measured).

### 5.8 Per-user installs under `%LOCALAPPDATA%\Programs`

- electron-builder apps, VS Code user setup, per-user Python (`%LOCALAPPDATA%\Programs\Python\Python3xx`), JetBrains Toolbox 2 IDEs. Measured 10 folders in 1 ms.
- Match each folder to an HKCU Uninstall `InstallLocation`. A folder with no matching entry is probably leftover or portable; report it as such.
- Squirrel apps live in `%LOCALAPPDATA%\<App>\app-<version>\` with `Update.exe` beside them; the newest `app-*` folder is the version.

### 5.9 winget portable and zip packages

- Links: `%LOCALAPPDATA%\Microsoft\WinGet\Links\` (symlinks on PATH). Files: `%LOCALAPPDATA%\Microsoft\WinGet\Packages\<PackageId>_<Source>_<suffix>\`. The folder name carries the winget id, so ownership is exact without running winget. Machine scope uses `%ProgramFiles%\WinGet\`. (Folder naming was not confirmed on a test machine this round.)

### 5.10 PowerShell modules

- **CLI:** `Get-InstalledModule` (PowerShellGet v2; measured 1.4 s, returned none on the test machine), `Get-InstalledPSResource` (PSResourceGet, built into PowerShell 7.4+), `Get-Module -ListAvailable` (measured 2.2 s for 97 modules, includes inbox modules).
- **Direct read:** each `$env:PSModulePath` entry: `Documents\WindowsPowerShell\Modules` (5.1 user), `Documents\PowerShell\Modules` (7 user), `%ProgramFiles%\WindowsPowerShell\Modules`, `%ProgramFiles%\PowerShell\Modules`. Layout `<Name>\<Version>\<Name>.psd1`. Gallery installs leave `PSGetModuleInfo.xml` (CLIXML with `Repository`). Skip `%SystemRoot%\System32\WindowsPowerShell\v1.0\Modules` (inbox).
- **Update / remove:** `Update-PSResource <Name>` or `Update-Module <Name>`; `Uninstall-PSResource <Name>` or `Uninstall-Module <Name>`.
- **Pitfalls:** OneDrive Known Folder Move relocates Documents. Inbox modules like Pester 3.4.0 and PackageManagement 1.0.0.1 cannot be updated in place; mark them inspect-only.

### 5.11 .NET global tools

- **CLI:** `dotnet tool list -g` (measured 2.9 s). On a machine with only the .NET runtime and no SDK it prints an "SDK not found" message instead of a list (measured).
- **Direct read:** `%USERPROFILE%\.dotnet\tools\.store\<id>\<version>\` (Linux and macOS: `~/.dotnet/tools/.store`). Shims in `.dotnet\tools`.
- **Update / remove:** `dotnet tool update -g <id>`, `dotnet tool uninstall -g <id>` (needs the SDK).
- Local tools (`.config/dotnet-tools.json`) belong to a repository; skip.

### 5.12 WSL distributions

- **Registry (fast, no process):** `HKCU\Software\Microsoft\Windows\CurrentVersion\Lxss\{GUID}` with `DistributionName`, `Version` (1 or 2), `BasePath`, `PackageFamilyName` (Store distros), and `DefaultDistribution` on the parent key.
- **CLI:** `wsl.exe -l -v` (measured about 110 ms). It writes UTF-16LE unless `WSL_UTF8=1` is set. In testing it also consumed the standard input of the script that launched it; always give it an empty stdin.
- **Do not** run `wsl -d …` during a scan; it starts the distro.
- **Actions:** `wsl --update` updates the WSL platform (network). `wsl --unregister <name>` deletes the distro and all its files; never routine. Packages inside a distro belong to the Linux runtime running inside it.

### 5.13 Python on Windows

- PEP 514 registry: `HKCU\Software\Python\<Company>\<Tag>\InstallPath` and the HKLM equivalents (both views). `PythonCore` is python.org.
- Launcher: `py --list-paths` (`py -0p`). The newer Python install manager (`py install`) also registers here.
- Also uv-managed Pythons (`uv python list --only-installed --output-format json`), conda, and Store aliases. Section 11 groups them.

## 6. macOS gaps

Sources the current runtime does not read:

| Gap | Source | Cost (measured) | Why it matters |
|---|---|---|---|
| Mac App Store apps | `Contents/_MASReceipt/receipt` inside the bundle; `mas list` if installed | file check, under 1 ms per app | Today they show as plain "app bundle". Updates go through the App Store or `mas upgrade <id>`. |
| Self-updating apps | `SUFeedURL` in Info.plist or `Contents/Frameworks/Sparkle.framework`; `Squirrel.framework`; `Contents/Resources/app-update.yml` (electron-updater); cask `auto_updates` | file checks | Mark `self_updates` so aiup does not offer a conflicting update. |
| Apps outside the two Applications folders | `mdfind "kMDItemContentType == 'com.apple.application-bundle'"` | 84 ms, about 380 results including system and nested helpers | Setapp, apps in custom folders. Filter `/System` and bundles nested inside other bundles. |
| Installer packages | `pkgutil --pkgs` (49 ms), `/var/db/receipts/*.plist` (`PackageVersion`, `InstallPrefixPath`), `pkgutil --file-info <path>` | fast | Owner for files in `/usr/local/bin` and `/Library`. pkgutil has no uninstall; inspect-only. |
| MacPorts | `/opt/local/bin/port -q installed active` | estimate 200 to 500 ms | Update `sudo port upgrade <p>`, remove `sudo port uninstall <p>`. |
| Nix / nix-darwin | as in section 4.10 | | |
| launchd items | `/Library/LaunchAgents`, `/Library/LaunchDaemons`, `~/Library/LaunchAgents` plists (`ProgramArguments`); `launchctl list` | 10 ms for 26 plists; 14 ms | Background items and their owners. Login items via `sfltool dumpbtm` need root; skip. |
| Faster Homebrew | `Cellar/*/*/INSTALL_RECEIPT.json`, `Caskroom/<cask>/.metadata/` | estimate under 50 ms | `brew list --versions` measured 407 ms, `brew info --json=v2 --installed` 963 ms. |
| Language managers | pipx, cargo (beyond the path-crate special case), Go bin, gem, rustup, mise, asdf, conda, pnpm, bun, yarn, multiple Node installs | see section 7 | Today only npm and uv are listed. |
| Editors, models, containers, agent configs | section 8 | | |

Avoid `system_profiler SPApplicationsDataType -json` (measured 2.5 s).

## 7. Cross-platform language and tool managers

Each entry: where, how to list, update and remove, cost, pitfalls. Paths use `~` for the home folder and Windows environment variables.

### 7.1 npm global, and multiple Node installs

- **CLI:** `npm ls -g --depth=0 --json` (measured 490 to 820 ms). Shape: `{"name": "lib", "dependencies": {"<pkg>": {"version": "1.2.3", "overridden": false}}}`. `npm link` packages carry `resolved: "file:…"`.
- **Direct read (fast):** global root `<prefix>/lib/node_modules` on Linux and macOS, `<prefix>\node_modules` on Windows (default prefix `%APPDATA%\npm`). Read `*/package.json` and `@scope/*/package.json` (`name`, `version`, `bin`). Prefix from `NPM_CONFIG_PREFIX`, then `prefix=` in `~/.npmrc`, then the Node install directory.
- **Bins:** `<prefix>/bin` (POSIX) or `<prefix>` itself on Windows (`.cmd` and `.ps1` shims whose text names `node_modules\<pkg>\…`).
- **Node version managers** each have their own global root:
  - nvm: `~/.nvm/versions/node/v*/lib/node_modules`
  - nvm-windows: `%APPDATA%\nvm\v*\node_modules` (`NVM_HOME`)
  - fnm: `~/.local/share/fnm/node-versions/v*/installation` (macOS `~/Library/Application Support/fnm`, Windows `%APPDATA%\fnm`)
  - Volta: `~/.volta/tools/image/node/<ver>`, user packages `~/.volta/tools/user/packages/*.json`
  - mise: `~/.local/share/mise/installs/node/<ver>`; asdf: `~/.asdf/installs/nodejs/<ver>`; n: `/usr/local/n/versions/node/<ver>`
- **Update / remove:** `npm install -g <pkg>@latest` / `npm uninstall -g <pkg>`, with `--prefix` when not the default.
- **Pitfalls:** on many Linux distros the system prefix is `/usr` (seen on Arch), which is root-owned. Packages under different Node versions are separate copies on purpose; group them by Node version and do not flag them as conflicts unless the same command is on PATH twice.

### 7.2 pnpm, bun, yarn (global)

- **pnpm:** `pnpm ls -g --json` (measured about 700 ms; it failed with an error when the pnpm global bin was not on PATH). Direct: `pnpm root -g`, or `~/.local/share/pnpm/global/<n>/node_modules` (macOS `~/Library/pnpm`, Windows `%LOCALAPPDATA%\pnpm`). The `<n>` layout number changes between pnpm majors; glob it. Update `pnpm update -g <pkg>`, remove `pnpm remove -g <pkg>`.
- **bun:** `~/.bun/install/global/node_modules` and `~/.bun/install/global/package.json`; bins `~/.bun/bin`. `bun pm ls -g`. Update `bun add -g <pkg>@latest`, remove `bun remove -g <pkg>`. `bun upgrade` updates bun itself.
- **yarn classic:** global dir `~/.config/yarn/global` (Windows `%LOCALAPPDATA%\Yarn\Data\global`); read its `package.json`. `yarn global list` is slow. Yarn 2+ has no global installs.

### 7.3 Python tools

- **uv tools:** `uv tool list --show-paths` (measured 53 ms). Text only (`name vX.Y.Z (path)` then `- bin (path)` lines; uv 0.13 has no JSON flag for this). Direct: `uv tool dir` (default `~/.local/share/uv/tools`, Windows `%APPDATA%\uv\tools`), each tool has `uv-receipt.toml` (requirements, entrypoints with install paths) and a `*.dist-info` with the version. Update `uv tool upgrade <name>`, remove `uv tool uninstall <name>`. `--outdated` goes online.
- **uv Pythons:** `uv python list --only-installed --output-format json`.
- **pipx:** `pipx list --json` gives `{"pipx_spec_version": "0.1", "venvs": {"<name>": {"metadata": {"main_package": {"package", "package_version", "apps", "app_paths"}, "python_version"}}}}`. Direct: `$PIPX_HOME/venvs/<name>/pipx_metadata.json` (default `~/.local/share/pipx`, older `~/.local/pipx`). Update `pipx upgrade <name>`, remove `pipx uninstall <name>`.
- **pip --user:** `python3 -m pip list --user --format=json` (estimate 300 to 600 ms per interpreter). Direct: user site-packages (`~/.local/lib/python3.X/site-packages`, macOS `~/Library/Python/3.X/lib/python/site-packages`, Windows `%APPDATA%\Python\Python3XX\site-packages`), read `*.dist-info/METADATA` (`Name`, `Version`). The `INSTALLER` file says who installed it (`pip`, `uv`, `conda`); `RECORD` lists console scripts. Update `python3 -m pip install --user -U <pkg>`, remove `python3 -m pip uninstall <pkg>`. On PEP 668 distros, user installs are blocked by default; point users to pipx or uv.
- **conda, mamba, micromamba, pixi:** `conda env list --json` gives `{"envs": [paths]}`; `~/.conda/environments.txt` lists env paths without running conda. Per env, `conda-meta/*.json` (`name`, `version`, `channel`, `build`) reads fast; `conda list --json` takes seconds. Common roots `~/miniconda3`, `~/miniforge3`, `~/anaconda3`, `$MAMBA_ROOT_PREFIX`. Update `conda update -n <env> <pkg>`, remove `conda remove -n <env> <pkg>`. pixi global: `~/.pixi/envs`, manifest `~/.pixi/manifests/pixi-global.toml`, `pixi global list`.

### 7.4 Rust, Go, Ruby, PHP, Deno

- **cargo:** `cargo install --list` (measured 18 to 35 ms) prints `name vX.Y.Z (source):` then indented bin names. Direct: `$CARGO_HOME/.crates2.json` (default `~/.cargo`): `{"installs": {"name ver (registry+https://…)": {"bins": […], "features": […], "rustc": "…"}}}`. `(path+file://…)` or `(git+…)` sources are source-built: update by rebuilding from that source. Update `cargo install <name>` (compiles, slow) or `cargo binstall <name>` when cargo-binstall exists; remove `cargo uninstall <name>`. cargo-binstall also records to cargo's tracking files; its own metadata location was not confirmed.
- **rustup:** `rustup toolchain list` (measured 86 ms) prints `stable-<triple> (active, default)`. Direct: `~/.rustup/toolchains/*`. Update `rustup update`, remove `rustup toolchain uninstall <name>`.
- **Go binaries:** `$GOBIN` or `$(go env GOPATH)/bin` (default `~/go/bin`). `go version -m <dir>` prints each binary's `path` and `mod <module> <version>` lines by reading build info; it does not execute them. Python can find the `\xff Go buildinf:` header directly. Update `go install <path>@latest`, remove by deleting the file. Version `(devel)` means a local build.
- **gem:** `gem list --local` (measured 180 to 250 ms) prints `name (v1, default: v2)`; no JSON. Direct: `<gemdir>/specifications/*.gemspec` (`name-version.gemspec`), default gems in `specifications/default`. User gems on Arch live in `~/.local/share/gem/ruby/<ver>`. System Ruby on macOS is inspect-only. Update `gem update <name>`, remove `gem uninstall <name> -x`.
- **composer global:** `composer global show --format=json` gives `{"installed": [{"name", "version", "description"}]}`. Direct: `$COMPOSER_HOME/vendor/composer/installed.json` (Linux `~/.config/composer`, macOS `~/.composer`, Windows `%APPDATA%\Composer`). Update `composer global update <vendor/pkg>`, remove `composer global remove <vendor/pkg>`.
- **deno install:** `deno install -g` writes shims to `$DENO_INSTALL_ROOT/bin` (default `~/.deno/bin`); each shim is a script that runs `deno run … <specifier>`, and the specifier (`jsr:@scope/pkg@1.2.3`, `npm:pkg@x`) gives name and version. Update by reinstalling with `-f`, remove `deno uninstall -g <name>`.

### 7.5 Polyglot version managers

- **mise:** `mise ls --installed --json` (measured 23 ms). Shape: `{"<tool>": [{"version": "1.2.3", "install_path": "…/mise/installs/<tool>/1.2.3", "installed": true, "active": false}]}`. Tool keys may carry a backend prefix (`npm:`, `cargo:`, `aqua:`, `ubi:`, `github:`, `pipx:`), so mise can own something that looks like an npm or cargo tool. Shims in `~/.local/share/mise/shims`. Update `mise upgrade <tool>`, remove `mise uninstall <tool>@<ver>`. Without `--installed` it also lists requested but missing versions. `--outdated` goes online.
- **asdf:** `~/.asdf/installs/<plugin>/<ver>` (`$ASDF_DATA_DIR`); shims in `~/.asdf/shims` contain `asdf exec`. Update `asdf install <plugin> latest`, remove `asdf uninstall <plugin> <ver>`.
- **aqua:** packages under `$AQUA_ROOT_DIR` (default `~/.local/share/aquaproj-aqua`); config-driven (`aqua.yaml`). Inspect-only, point to the config. CLI listing flags not confirmed.
- **proto:** `~/.proto/tools/<tool>/<ver>`, shims `~/.proto/shims`, bins `~/.proto/bin`. CLI listing flags not confirmed.

## 8. Editors, IDEs, models, containers, agent integrations

### 8.1 VS Code family extensions

- **Direct read (fast):** `<extensions dir>/extensions.json`, an array of `{"identifier": {"id": "publisher.name"}, "version": "1.2.3", "location": {…}, "relativeLocation": "…", "metadata": {"installedTimestamp", "source", "isPreReleaseVersion"}}`. Entries listed in `.obsolete` are pending removal.
- **Dirs:** VS Code `~/.vscode/extensions`, Insiders `~/.vscode-insiders/extensions`, VSCodium and Code - OSS `~/.vscode-oss/extensions`, Cursor `~/.cursor/extensions`, Windsurf `~/.windsurf/extensions`, remote servers `~/.vscode-server/extensions`. Flatpak VS Code keeps them under `~/.var/app/com.visualstudio.code/`. Other forks (Antigravity and similar) likely follow `~/.<name>/extensions`; confirm each.
- **CLI:** `code --list-extensions --show-versions` prints `publisher.name@1.2.3` per line. It starts Electron (estimate 0.5 to 2 s). Cursor uses `cursor`, Windsurf `windsurf`.
- **Update / remove:** `code --install-extension <id> --force`, `code --uninstall-extension <id>`.
- **Pitfall:** `code` on PATH may be a wrapper for a Flatpak or Snap build, or the WSL remote shim, each with a different extension dir.

### 8.2 JetBrains IDEs and Toolbox

- **Every install** (Toolbox, tarball in `/opt`, snap, Windows installer, macOS app) has `product-info.json` in its root (`Contents/Resources/product-info.json` on macOS) with `name`, `version`, `buildNumber`, `productCode`, `launch`.
- **Toolbox 2 install roots:** Linux `~/.local/share/JetBrains/Toolbox/apps`, macOS `~/Applications`, Windows `%LOCALAPPDATA%\Programs`. Toolbox 1.x used `apps/<product>/ch-0/<build>/`. Toolbox settings: `.settings.json` in the Toolbox data dir.
- **Update / remove:** through the Toolbox app (no documented CLI). Mark `self_updates`. Standalone installs on Windows have registry entries.

### 8.3 Local model runtimes

- **Ollama:** `ollama list` needs the local server (loopback `127.0.0.1:11434`, JSON at `/api/tags` with `models[].name`, `size`, `digest`, `modified_at`). Offline read: `~/.ollama/models/manifests/registry.ollama.ai/<namespace>/<model>/<tag>` (`library` is the official namespace); the Linux system service uses `/usr/share/ollama/.ollama/models`; `OLLAMA_MODELS` overrides. Update `ollama pull <name>` (large download), remove `ollama rm <name>`. Report names and sizes only.
- **LM Studio:** `lms ls --json` lists downloaded models ([LM Studio docs](https://lmstudio.ai/docs/cli/local-models/ls)); the CLI talks to the LM Studio service and may start it, so prefer the offline read: `~/.lmstudio/models/<publisher>/<repo>/` (older `~/.cache/lm-studio/models`). The `lms` CLI lives in `~/.lmstudio/bin`.

### 8.4 Containers (names only)

- **Docker:** `docker image ls --format '{{json .}}'` (one JSON object per line: `Repository`, `Tag`, `ID`, `Size`). Needs socket access; it returned "permission denied" for a user outside the docker group (measured 97 ms). On macOS and Windows, Docker Desktop may not be running; never start it.
- **Podman (rootless):** `podman images --format json`.
- Removing images is inspect-only by default.

### 8.5 MCP servers as detected integrations

These are configs, not installs, but they name packages that run on the machine. Read only server name, command basename, package spec, and URL host. Never store `env`, `headers`, or arguments that look like tokens.

| Client | File | Key |
|---|---|---|
| Claude Code | `~/.claude.json` | top-level `mcpServers`, and `projects.<path>.mcpServers` |
| Claude Code (project) | `.mcp.json` in a repo | `mcpServers` (per repo; skip in a system scan) |
| Claude Desktop | macOS `~/Library/Application Support/Claude/claude_desktop_config.json`, Windows `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers` |
| Cursor | `~/.cursor/mcp.json` | `mcpServers` |
| Codex | `$CODEX_HOME/config.toml` (default `~/.codex`) | `[mcp_servers.<name>]` with `command`, `args`, `url` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `mcpServers` |
| VS Code | user `mcp.json` (Linux `~/.config/Code/User/`, macOS `~/Library/Application Support/Code/User/`, Windows `%APPDATA%\Code\User\`) | `servers` |
| Gemini CLI | `~/.gemini/settings.json` | `mcpServers` |

- `~/.claude.json` can be large and holds per-project state; cap the read and pull only the MCP keys.
- Map `npx -y <pkg>@<ver>`, `uvx <pkg>`, `docker run <image>` to the package they fetch. Unpinned `npx` and `uvx` servers fetch the newest release at launch; say so.
- Editing these files is out of scope; inspect-only.

## 9. Vendor self-updating tools

| Tool | Layout | Version without network or execution | Update / remove |
|---|---|---|---|
| Claude Code (native) | Linux/macOS: `~/.local/bin/claude` symlink to `~/.local/share/claude/versions/<ver>` (seen). Windows: `%USERPROFILE%\.local\bin\claude.exe` is a real file; older copies under `%USERPROFILE%\.local\share\claude\versions\` (seen). | Symlink target name; on Windows PE `FileVersion` (seen). | `claude update`. Remove the launcher and `~/.local/share/claude`; leave `~/.claude` (settings). Also ships via npm `@anthropic-ai/claude-code` and a Homebrew cask, which is a duplicate case. |
| Codex CLI | npm `@openai/codex` (Windows shims `codex`, `codex.cmd`, `codex.ps1` seen), Homebrew cask and formula | package.json in the npm root | npm or brew commands. |
| Cursor agent CLI | installer places `~/.local/bin/cursor-agent` (and an `agent` alias) pointing into `~/.local/share/cursor-agent/versions/<ver>/` (from the install script; not seen this round) | version folder name | its own update command; remove the links and version dir. |
| Grok CLI | `~/.grok/bin/grok`; downloads named `grok-<ver>-<platform>` under `~/.grok/downloads/` (seen) | file name | its installer. A generic name such as `agent` in `~/.local/bin` may point here (seen), so the same command name can belong to different vendors. |
| Antigravity CLI (`agy`) | single large binary in `~/.local/bin`; self-update leaves `agy.<digits>.old` backups beside it (seen) | none found offline | its installer. Treat `.old` files as backups, not separate tools. |
| Gemini CLI | npm `@google/gemini-cli`, Homebrew, or mise npm backend (seen) | package.json or mise JSON | owning manager. |
| opencode | `~/.opencode/bin/opencode` installer, npm `opencode-ai`, Homebrew | npm package.json; installer copy not confirmed | owning manager. |
| Deno, Bun, uv, rustup, mise | single binaries with self-update | Deno and Bun: none offline besides running the known binary; uv standalone writes `~/.config/uv/uv-receipt.json` (not confirmed) | `deno upgrade`, `bun upgrade`, `uv self update` (standalone installs only), `rustup self update`, `mise self-update`. If a package manager owns them, use that instead. |
| Electron and Chromium apps (Windows) | Squirrel `%LOCALAPPDATA%\<App>\app-<ver>\`; electron-builder `%LOCALAPPDATA%\Programs\<App>` with HKCU `DisplayVersion`; Chrome-style `…\Application\<ver>\` | folder names, registry, PE version | the app updates itself; mark `self_updates`. |
| macOS apps with Sparkle or Squirrel.Mac | see section 6 | Info.plist | the app updates itself. |
| Snap, Flatpak apps with auto-update, Store apps | section 4.7, 4.8, 5.3 | source metadata | refreshed by the platform. |

Running `<known tool> --version` from a path aiup itself identified is cheap (Claude Code measured 24 ms, Deno 144 ms) and consistent with "never run unfamiliar commands", but each such call should be allowlisted per tool and never run for unknown files.

## 10. Which manager owns an executable on PATH

Order of evidence, cheapest first. Stop at the first exact answer.

1. **Resolve** `realpath`, keeping the chain (Linux `/etc/alternatives` links; Windows reparse points and `.shim` files).
2. **Known prefixes:**

   | Resolved path under | Owner |
   |---|---|
   | npm global root (any prefix, section 7.1) | npm (package.json ancestry with matching `bin`, as macOS does today) |
   | `uv tool dir`, `$PIPX_HOME/venvs` | uv, pipx |
   | `$CARGO_HOME/bin` | cargo (`.crates2.json` `bins`) |
   | `$GOBIN`, `~/go/bin` | go (build info) |
   | `mise/installs`, `.asdf/installs`, `.proto/tools`, `aquaproj-aqua` | mise, asdf, proto, aqua |
   | `/nix/store` | Nix |
   | `flatpak/exports/bin`, `/snap/bin` | Flatpak, Snap |
   | Homebrew `Cellar`, `Caskroom` | Homebrew |
   | vendor version dirs (section 9) | that vendor |
   | Windows `%APPDATA%\npm` | npm (parse the `.cmd` shim) |
   | Windows `scoop\shims` | Scoop (`.shim` `path =` line) |
   | Windows `chocolatey\bin` | Chocolatey |
   | Windows `WinGet\Links`, `WinGet\Packages\<Id>_…` | winget (id from folder name) |
   | Windows `WindowsApps` | App Execution Alias (package family from reparse data) |
   | Windows `.dotnet\tools` | .NET tool |

3. **System package query, batched** (one process for all unknowns): `pacman -Qoq p1 p2 …`, `dpkg -S p1 p2 …`, `rpm -qf --qf '%{NAME}\n' p1 p2 …`, `apk info --who-owns`, `xbps-query -o`, `qfile`; macOS `pkgutil --file-info`. Query both `/bin/x` and `/usr/bin/x` on merged-`/usr` systems.
4. **Windows registry match:** longest `InstallLocation` prefix across Uninstall entries; then the folder of `DisplayIcon` or `UninstallString`. Mark as `strong`, not `exact`.
5. **Static content:** script shims (section 4.12), Go build info, PE version resource, app bundle ancestry.
6. **Otherwise:** `Local command`, owner unknown, inspect-only (the macOS wording).

## 11. Duplicate and conflict detection

Carry the macOS `doctor` model across, with a shared identity table:

1. **Group by identity.** An alias table maps source names to one identity (`nodejs`, `node`, `Node.js LTS`, `OpenJS.NodeJS` all become `node`; `github-cli` and `GitHub.cli` become `gh`). Start from the catalog and grow it.
2. **Flag a duplicate** when an identity has two or more source records that point at different resolved files, or when the command name resolves to two or more distinct real paths across PATH (the `which -a` check; on Windows include `PATHEXT` variants).
3. **Flag shadowing** when the copy aiup manages is not the first one on PATH.
4. **Flag version drift** when grouped copies report different versions.
5. **Do not flag:**
   - links and shims that resolve to the same file (`~/.local/bin/gh` linking to the distro `gh`);
   - manager shims that forward to one install (mise, asdf, Scoop, Volta);
   - companion commands (`npx` with npm, `uvx` with uv, `pip3` with its Python);
   - per-Node-version npm globals that are not on PATH;
   - aiup's own wrappers (already allowlisted on macOS).
6. **Windows double counting:** winget lists Chocolatey and Scoop installs that registered an Uninstall entry, and Chocolatey installers create Uninstall entries. Join on the registry key (`ARP\…` id or `{GUID}`), `InstallLocation`, and shim target before reporting. The same product in the 64-bit and 32-bit registry views counts once unless install folders differ.

Common real conflicts worth a named rule: distro Node plus nvm/fnm/Volta Node; distro Rust plus rustup; Python from the distro, python.org, Store alias, uv, and conda; Claude Code native plus npm global plus Homebrew cask; Codex via npm and Homebrew; VS Code system package plus Flatpak or Snap; Git for Windows via winget plus Scoop; the same Flatpak in user and system scope.

## 12. Version strings, localization, and other cross-cutting pitfalls

- **Keep the raw version.** Formats differ: Arch `epoch:ver-rel`, Debian `epoch:upstream-revision` with `~`, RPM EVR, PEP 440, semver with prerelease tags, Go pseudo-versions, date versions (`20260817.0`), four-part Windows versions, words (`Unknown`, `latest`, `< 1.2`). Compare only within a source, with that source's comparer (`vercmp`, `dpkg --compare-versions`, `rpm` EVR rules, `packaging.version`). Across sources, show both and only flag "differs".
- **Names that contain versions.** Registry `DisplayName` and winget `Name` often embed the version (`7-Zip 26.04 (x64)`). Strip trailing version-like tokens before identity matching.
- **Localization.** Use `LC_ALL=C` on Linux. On Windows prefer registry values and PowerShell objects; text output from winget and choco is localized. Some MSI `DisplayName` values are localized product names.
- **Encoding.** `wsl.exe` writes UTF-16LE (fix with `WSL_UTF8=1`). Windows console tools follow the active code page; decode explicitly. PowerShell started without a console over SSH writes progress records as CLIXML on stderr unless `$ProgressPreference = 'SilentlyContinue'` (seen).
- **stdin.** Give every child process an empty stdin. `wsl.exe` consumed a parent script's stdin in testing.
- **Truncated columns.** winget and snap tables. Prefer JSON, objects, or direct reads.
- **Hidden network calls.** `winget list` (source correlation), `yay -Qua` and `paru -Qua` (AUR), `dnf` without `-C`, `zypper` without `--no-refresh`, `brew` without `HOMEBREW_NO_AUTO_UPDATE=1`, `scoop status`, `choco outdated`, `npm outdated -g`, `uv tool list --outdated`, `mise ls --outdated`. Local only: `pacman -Q*`, `dpkg-query`, `rpm -q`, `snap list`, `flatpak list`, `pipx list`, `cargo install --list`, `uv tool list` without `--outdated`.
- **PATH shims.** mise, asdf, pyenv, rbenv, Volta, Scoop, Chocolatey, and npm `.cmd` files all hide the real target. Resolve through them before choosing an owner.
- **Name collisions.** Generic names (`agent`, `code`, `pi`) can belong to unrelated vendors. Ownership comes from the resolved path, never the name.
- **Backups and leftovers.** Self-updaters leave `.old` files; editors leave `.obsolete` lists; Windows leaves `%LOCALAPPDATA%\Programs` folders after uninstall. Label them, never count them as tools.
- **Privilege for actions.** pacman, apt, dnf, zypper, apk, xbps, snap, system Flatpak, HKLM uninstalls, Chocolatey, and global Scoop need root or UAC. aiup should say so up front and never elevate silently.

## 13. Prioritized recommendations and scan budget

### 13.1 Order of implementation (coverage per ms)

**Tier 1: file reads, in-process, largest coverage (target under 300 ms total)**

1. System package database: pacman local db, dpkg status, `rpm -qa` (the one subprocess here), apk installed db, xbps. This covers most of a Linux system in 15 to 300 ms.
2. Windows Uninstall registry via `winreg`, all three views, with filters and installer-type parsing. This covers most Windows apps, and maps removal for most of them.
3. PATH walk with realpath and the known-prefix rules from section 10. Catches vendor CLIs and unmanaged binaries on every OS.
4. npm globals by direct read, for every prefix and Node version manager.
5. Vendor CLI layouts from section 9 (the catalog's core tools).
6. GUI entry points: desktop files (Linux), Start Menu shortcuts (Windows); macOS bundles already exist, add the Mac App Store receipt and self-updater checks.

**Tier 2: cheap manager reads, parallel (target under 1 s wall)**

7. Flatpak (dir read or one `flatpak list`), Snap (`snap.yaml` reads), AppImage magic-byte scan, linuxbrew Cellar receipts, `pacman -Qqm` for foreign packages.
8. Scoop app dirs, Chocolatey nuspecs, winget portable dirs, Appx (registry, or one PowerShell call), WSL from the Lxss registry, PEP 514 Pythons.
9. uv receipts, pipx metadata, `.crates2.json`, Go build info for `GOBIN`, `mise ls --installed --json`, rustup toolchain dirs, .NET tool store.
10. Editor `extensions.json` files, JetBrains `product-info.json`.
11. Batched ownership queries for PATH entries Tier 1 could not place.

**Tier 3: on demand, cached, or opt-in**

12. winget correlation (`winget export` or `Get-WinGetPackage` when the module exists) to learn which apps winget can update. About 2 s and may touch the network. Cache for a day; refresh on `aiup inventory --refresh`.
13. conda envs, gem specs, composer, PowerShell modules (dir walk), Ollama and LM Studio model dirs, Docker or Podman images, MCP configs, systemd user units, launchd plists, distrobox exports.
14. Outdated checks for any source. Never part of a scan; a separate explicit command.

### 13.2 Scan budget

| Phase | Work | Target (warm) | Target (cold) |
|---|---|---|---|
| Startup | Python start, load cache and fingerprints | 60 ms (estimate) | 60 ms |
| Fingerprint check | stat package db files, registry key times, manager dirs | 20 ms | 20 ms |
| Tier 1 | reads above, parallel | skipped for unchanged sources | 300 ms |
| Tier 2 | reads and short subprocesses, 8 workers | skipped for unchanged sources | 1,000 ms |
| Ownership | one batched query per package manager | 50 ms | 300 ms |
| Dedupe and enrich | identity grouping, duplicate rules | 50 ms | 100 ms |
| **Total** | | **under 300 ms** | **under 2 s typical, 3 s ceiling** |

Rules that keep it there:

- A worker pool of about 8 threads (subprocess and I/O bound work releases the GIL).
- Per-source soft timeout 1.5 s and hard timeout 3 s. A timed-out source keeps its last cached rows, marked stale.
- Probe for a source's directory or binary before doing anything; absent sources cost under 1 ms.
- At most one PowerShell process per Windows scan, and none if Tier 1 and Tier 2 can be served by `winreg` and file reads.
- Cache rows per source, keyed by a fingerprint: `/var/lib/pacman/local` mtime, `/var/lib/dpkg/status` mtime, rpmdb file mtime, registry key last-write time, `node_modules` and manager dir mtimes, `.crates2.json` mtime. A warm scan rereads only sources whose fingerprint changed. Keep the five-minute TTL from macOS as an upper bound.
- No network and no privilege in any phase.

On the measured machines, the expensive commands this plan avoids add up to about 10 s (choco list 1.9 to 2.6 s, dotnet tool list 2.9 s, winget list 2.1 s, `Get-Module -ListAvailable` 2.2 s, `Get-InstalledModule` 1.4 s, npm ls 0.5 to 0.8 s, `system_profiler` 2.5 s on macOS). Their file-based equivalents are each estimated at tens of milliseconds.

## 14. What this research could not confirm

- No test machine had Flatpak, Snap, Nix, Guix, apt, dnf, zypper, apk, xbps, pipx, bun, conda, VS Code, Ollama, or LM Studio installed. Their formats come from official docs and prior knowledge and need a check on a real machine before parsers are final. Highest risk: the JSON key names of `nix profile list --json`, Flatpak column separators when piped, and Appx data in the AppModel registry key.
- Microsoft.WinGet.Client was not installed on either Windows test machine, so its object properties come from docs and community scripts, not a live run.
- `winget export` was not run (it writes a file); its shape comes from Microsoft Learn and the published schema.
- winget portable folder naming (`<Id>_<Source>_<suffix>`) and the cargo-binstall metadata location were not seen on a test machine.
- Cursor agent CLI layout comes from its install script, not a test machine. opencode and Antigravity offline version sources were not found.
- JetBrains Toolbox 2 has no documented state file listing installed tools; `product-info.json` per install is the reliable source.
- Python in-process timings (winreg, scandir, desktop parsing) are estimates; only the PowerShell and CLI equivalents were measured.
- uv 0.13.6 was checked locally; `uv tool list` may gain a JSON flag later.

Sources checked: [winget export](https://learn.microsoft.com/en-us/windows/package-manager/winget/export), [Chocolatey list command](https://docs.chocolatey.org/en-us/choco/commands/list/), [nix profile list](https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-profile-list), [LM Studio `lms ls`](https://lmstudio.ai/docs/cli/local-models/ls), [Microsoft.WinGet.Client on the PowerShell Gallery](https://www.powershellgallery.com/packages/microsoft.WinGet.Client), [Toolbox App 2.0 install locations](https://blog.jetbrains.com/toolbox-app/2023/06/toolbox-app-2-0-beta/), plus local `--help` output for uv 0.13.6 and mise 2026.10.
