"""Cheap file and registry reads beyond PATH and app menus (research 4.13, 5.5, 5.6, 6).

- AppImages in the usual folders (Linux);
- JetBrains IDEs from ``product-info.json`` (Toolbox, /opt, Program Files);
- runtimes kept by version managers: mise and asdf installs, rustup
  toolchains, nvm, fnm and Volta Node versions;
- Windows: WSL distributions, PEP 514 Python installs, and folders under
  ``%LOCALAPPDATA%\\Programs`` that no Uninstall entry names.

Every read is a folder listing or a small file; nothing is run.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from aiup.detect import files, owners
from aiup.detect.items import InventoryItem, Owner, det_id
from aiup.detect.sources import DetectionSource, register

if TYPE_CHECKING:
    from aiup.engine.context import Context

MAX_ROWS = 2000


def _item(item_id: str, name: str, version: str, path: str, kind: str, owner: Optional[Owner],
          scope: str, evidence: str, guidance: str = "", target: str = "", description: str = "",
          self_updates: bool = False, extra: Tuple[Tuple[str, str], ...] = ()) -> InventoryItem:
    facts: Tuple[Tuple[str, str], ...] = extra
    if target:
        facts = (("target", target),) + facts
    paths = tuple(p for p in dict.fromkeys((target, path)) if p)
    confidence = "heuristic"
    if owner is not None:
        confidence = "exact" if owner.confidence == "exact" else ("strong" if owner.manager == "arp" else "heuristic")
    return InventoryItem(
        id=item_id, name=name, version=version, population="detected", source="extras", paths=paths,
        owner=owner, kind=kind, scope=scope, confidence=confidence, evidence=evidence,
        self_updates=self_updates, needs_admin=scope == "system", guidance=guidance,
        description=description, facts=facts,
    )


def _scope(ctx: "Context", path: str) -> str:
    return "user" if files.inside(path, str(files.home(ctx))) else "system"


# ----- AppImages --------------------------------------------------------------------------


def appimage_dirs(ctx: "Context") -> Tuple[Path, ...]:
    home = files.home(ctx)
    return (home / "Applications", home / "AppImages", home / ".local" / "share" / "AppImages", Path("/opt"))


def appimages(ctx: "Context") -> List[InventoryItem]:
    out: List[InventoryItem] = []
    for folder in appimage_dirs(ctx):
        for entry in files.scandir(folder):
            try:
                if not entry.is_file():
                    continue
            except OSError:
                continue
            head = files.read_head(entry.path, 16)
            if not files.appimage_type(head):
                continue
            stem = entry.name.rsplit(".", 1)[0] if entry.name.lower().endswith(".appimage") else entry.name
            name, version = files.split_name_version(stem)
            resolved = files.real(entry.path)
            out.append(_item(
                det_id("extras", "appimage:" + entry.name.lower()), name or stem, version, entry.path, "app", None,
                _scope(ctx, entry.path), "AppImage file",
                guidance="It is a single file. Replace it with a newer download to update it, or delete it to remove it.",
                target=resolved, extra=(("appimage", "1"),),
            ))
    return out


# ----- JetBrains --------------------------------------------------------------------------


def _toolbox_apps(ctx: "Context") -> Path:
    if files.is_windows(ctx):
        return files.local_appdata(ctx) / "JetBrains" / "Toolbox" / "apps"
    return files.xdg_data_home(ctx) / "JetBrains" / "Toolbox" / "apps"


def jetbrains_roots(ctx: "Context") -> List[Path]:
    roots = [_toolbox_apps(ctx)]
    if files.is_windows(ctx):
        roots.append(files.local_appdata(ctx) / "Programs")
        for name in ("ProgramFiles", "ProgramFiles(x86)"):
            value = files.env_get(ctx, name)
            if value:
                roots.append(Path(value) / "JetBrains")
    else:
        roots.append(Path("/opt"))
        roots.append(files.home(ctx) / ".local" / "share" / "JetBrains")
    return roots


def _product_infos(root: Path) -> List[Path]:
    """``product-info.json`` files up to three folders below ``root``."""
    out: List[Path] = []
    level: List[Path] = [root]
    for _depth in range(4):
        following: List[Path] = []
        for folder in level:
            info = folder / "product-info.json"
            if folder != root and info.is_file():
                out.append(info)
                continue
            for entry in files.scandir(folder):
                try:
                    if entry.is_dir() and not entry.name.startswith("."):
                        following.append(Path(entry.path))
                except OSError:
                    continue
        level = following[:500]
    return out


def jetbrains(ctx: "Context") -> List[InventoryItem]:
    out: List[InventoryItem] = []
    toolbox = str(_toolbox_apps(ctx))
    found: List[Tuple[Path, Dict[str, object], str]] = []
    for root in jetbrains_roots(ctx):
        for info in _product_infos(root):
            data = files.read_json(info)
            if not isinstance(data, dict) or not isinstance(data.get("name"), str) or not data.get("name"):
                continue
            launch = data.get("launch")
            first = launch[0] if isinstance(launch, list) and launch and isinstance(launch[0], dict) else {}
            launcher = first.get("launcherPath")
            target = ""
            if isinstance(launcher, str) and launcher:
                path = os.path.normpath(os.path.join(str(info.parent), launcher))
                if os.path.isfile(path):
                    target = files.real(path)
            found.append((info, data, target))
    outside = [target for info, _data, target in found if target and not files.inside(str(info), toolbox)]
    owned = owners.attribute(ctx, outside, system=not files.is_windows(ctx))
    for info, data, target in found:
        version = data.get("version")
        code = data.get("productCode")
        name = str(data.get("name"))
        folder = str(info.parent)
        owner: Optional[Owner] = None
        guidance = ""
        self_updates = False
        if files.inside(folder, toolbox):
            owner = Owner(manager="jetbrains-toolbox", package=code if isinstance(code, str) and code else name,
                          confidence="exact", label="JetBrains Toolbox", evidence="Toolbox apps folder")
            guidance = "Update or remove it in JetBrains Toolbox."
            self_updates = True
        elif target and target in owned:
            owner = owned[target].owner
        out.append(_item(
            det_id("extras", "jetbrains:" + files.norm(folder)), name, version if isinstance(version, str) else "",
            folder, "app", owner, _scope(ctx, folder), "product-info.json", guidance=guidance, target=target,
            self_updates=self_updates,
        ))
    return out


# ----- runtimes ---------------------------------------------------------------------------


def _runtime(ctx: "Context", manager: str, label: str, tool: str, version: str, folder: str,
             hint: str) -> InventoryItem:
    owner = Owner(manager=manager, package=tool, confidence="exact", label=label, evidence="version manager folder")
    return _item(
        det_id("extras", "runtime:" + manager + ":" + tool + "@" + version), tool, version, folder, "runtime",
        owner, _scope(ctx, folder), "version manager folder",
        guidance=("Manage it with: " + hint) if hint else "Manage it with " + label + ".",
        description="Kept by " + label,
    )


def _dirs(folder: object) -> List[os.DirEntry]:
    out: List[os.DirEntry] = []
    for entry in files.scandir(folder):
        try:
            if entry.is_dir() and not entry.name.startswith("."):
                out.append(entry)
        except OSError:
            continue
    return out


def runtimes(ctx: "Context") -> List[InventoryItem]:
    out: List[InventoryItem] = []
    for manager, label, root, depth in owners.manager_dirs(ctx):
        if manager in ("volta", "proto", "n"):
            continue    # their tool folders hold packages and caches, not one version per folder
        if depth < 0:
            for entry in _dirs(root):
                if entry.name[:1] in "v0123456789":
                    out.append(_runtime(ctx, manager, label, "node", entry.name.lstrip("v"), entry.path,
                                        manager + " uninstall " + entry.name))
            continue
        for tool in _dirs(root):
            for version in _dirs(tool.path):
                if version.is_symlink() or version.name == "latest":
                    continue
                hint = {"mise": "mise uninstall " + tool.name + "@" + version.name,
                        "asdf": "asdf uninstall " + tool.name + " " + version.name}.get(manager, "")
                out.append(_runtime(ctx, manager, label, tool.name, version.name, version.path, hint))
    volta_node = (files.env_dir(ctx, "VOLTA_HOME") or files.home(ctx) / ".volta") / "tools" / "image" / "node"
    for entry in _dirs(volta_node):
        out.append(_runtime(ctx, "volta", "Volta", "node", entry.name, entry.path, ""))
    rustup_home = files.env_dir(ctx, "RUSTUP_HOME") or files.home(ctx) / ".rustup"
    for entry in _dirs(rustup_home / "toolchains"):
        out.append(_runtime(ctx, "rustup", "rustup", "rust", entry.name, entry.path,
                            "rustup toolchain uninstall " + entry.name))
    return out[:MAX_ROWS]


def runtime_roots(ctx: "Context") -> List[Path]:
    roots = [root for _m, _l, root, _d in owners.manager_dirs(ctx)]
    roots.append((files.env_dir(ctx, "RUSTUP_HOME") or files.home(ctx) / ".rustup") / "toolchains")
    return roots


# ----- Windows ----------------------------------------------------------------------------


def _reg_values(root: object, path: str, flag: int = 0) -> List[Tuple[str, Dict[str, object]]]:
    """``(subkey, values)`` for each subkey of ``path``; [] off Windows or on errors."""
    try:
        import winreg
    except ImportError:
        return []
    out: List[Tuple[str, Dict[str, object]]] = []
    try:
        parent = winreg.OpenKey(root, path, 0, winreg.KEY_READ | flag)
    except OSError:
        return []
    with parent:
        index = 0
        while index < 512:
            try:
                name = winreg.EnumKey(parent, index)
            except OSError:
                break
            index += 1
            values: Dict[str, object] = {}
            try:
                with winreg.OpenKey(parent, name, 0, winreg.KEY_READ | flag) as key:
                    position = 0
                    while position < 64:
                        try:
                            value_name, data, _kind = winreg.EnumValue(key, position)
                        except OSError:
                            break
                        values[value_name] = data
                        position += 1
            except OSError:
                continue
            out.append((name, values))
    return out


def _text(values: Dict[str, object], name: str) -> str:
    value = values.get(name)
    return value.strip() if isinstance(value, str) else ""


def wsl(ctx: "Context") -> List[InventoryItem]:
    try:
        import winreg
    except ImportError:
        return []
    out: List[InventoryItem] = []
    lxss = "Software\\Microsoft\\Windows\\CurrentVersion\\Lxss"
    for key, values in _reg_values(winreg.HKEY_CURRENT_USER, lxss):
        name = _text(values, "DistributionName")
        if not name:
            continue
        folder = _text(values, "BasePath")
        if folder.startswith("\\\\?\\"):
            folder = folder[4:]
        owner = Owner(manager="wsl", package=name, confidence="exact", label="WSL", evidence="Lxss key")
        out.append(_item(
            det_id("extras", "wsl:" + key.lower()), name, "", folder, "distro", owner, "user", "Lxss key",
            guidance="Manage it with the wsl command. Removing a distribution deletes its files.",
            description="WSL distribution",
        ))
    return out


def pep514(ctx: "Context") -> List[InventoryItem]:
    try:
        import winreg
    except ImportError:
        return []
    out: List[InventoryItem] = []
    seen: Dict[str, bool] = {}
    views = (
        (winreg.HKEY_CURRENT_USER, 0, "user"),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY, "system"),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY, "system"),
    )
    found: List[Tuple[str, str, str, str]] = []
    for root, flag, scope in views:
        for company, _values in _reg_values(root, "Software\\Python", flag):
            if company.lower() == "pylauncher":
                continue
            for tag, values in _reg_values(root, "Software\\Python\\" + company, flag):
                try:
                    with winreg.OpenKey(root, "Software\\Python\\" + company + "\\" + tag + "\\InstallPath", 0,
                                        winreg.KEY_READ | flag) as key:
                        folder = str(winreg.QueryValueEx(key, "")[0] or "")
                        try:
                            exe = str(winreg.QueryValueEx(key, "ExecutablePath")[0] or "")
                        except OSError:
                            exe = os.path.join(folder, "python.exe") if folder else ""
                except OSError:
                    continue
                if not exe or not os.path.isfile(exe) or files.norm(exe) in seen:
                    continue
                seen[files.norm(exe)] = True
                version = _text(values, "Version") or tag
                name = _text(values, "DisplayName") or ("Python " + tag)
                found.append((name, version, files.real(exe), scope))
    owned = owners.attribute(ctx, [f[2] for f in found], system=False)
    for name, version, exe, scope in found:
        hit = owned.get(exe)
        out.append(_item(
            det_id("extras", "python:" + files.norm(exe)), name, version, os.path.dirname(exe), "runtime",
            hit.owner if hit is not None else None, scope, "PEP 514 key", target=exe,
            extra=(("command", "python"),),
        ))
    return out


_PROGRAMS_SKIP = frozenset(("common", "python"))


def program_leftovers(ctx: "Context") -> List[InventoryItem]:
    """``%LOCALAPPDATA%\\Programs`` folders that no Uninstall entry names."""
    from aiup.detect import registry

    out: List[InventoryItem] = []
    programs = files.local_appdata(ctx) / "Programs"
    for entry in files.scandir(programs):
        try:
            if not entry.is_dir() or entry.name.lower() in _PROGRAMS_SKIP or entry.name.startswith("."):
                continue
        except OSError:
            continue
        probe = os.path.join(entry.path, "x")
        if registry.entry_for_path(ctx, probe) is not None:
            continue
        if (Path(entry.path) / "product-info.json").is_file():
            continue    # a JetBrains IDE, listed above
        exe = os.path.join(entry.path, entry.name + ".exe")
        target = files.real(exe) if os.path.isfile(exe) else ""
        out.append(_item(
            det_id("extras", "programs:" + entry.name.lower()), entry.name,
            files.pe_version(target) if target else "", entry.path, "app", None, "user", "Programs folder",
            guidance="No uninstall entry names this folder. It may be left from an old install.",
            target=target,
        ))
    return out


# ----- the source ---------------------------------------------------------------------------


class ExtrasSource(DetectionSource):
    name = "extras"
    oses = frozenset(("linux", "windows"))
    cost = "cheap"

    def _folders(self, ctx: "Context") -> List[Path]:
        folders: List[Path] = list(jetbrains_roots(ctx)) + runtime_roots(ctx)
        if files.is_windows(ctx):
            folders.append(files.local_appdata(ctx) / "Programs")
        else:
            folders.extend(appimage_dirs(ctx))
        return folders

    def fingerprint(self, ctx: "Context") -> str:
        parts: List[str] = []
        for folder in self._folders(ctx):
            parts.append(str(folder) + "=" + files.stat_stamp(folder))
            for entry in files.scandir(folder)[:200]:
                parts.append(entry.name + "=" + files.stat_stamp(entry.path))
        if files.is_windows(ctx):
            parts.append(_registry_stamp())
        return files.stamp(parts)

    def read(self, ctx: "Context") -> List[InventoryItem]:
        items: List[InventoryItem] = []
        if files.is_windows(ctx):
            items.extend(jetbrains(ctx))
            items.extend(runtimes(ctx))
            items.extend(wsl(ctx))
            items.extend(pep514(ctx))
            items.extend(program_leftovers(ctx))
        else:
            items.extend(appimages(ctx))
            items.extend(jetbrains(ctx))
            items.extend(runtimes(ctx))
        return items


def _registry_stamp() -> str:
    """Last-write times of the WSL, Python and Uninstall keys."""
    try:
        import winreg
    except ImportError:
        return ""
    parts: List[str] = []
    for root, path, flag in (
        (winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Lxss", 0),
        (winreg.HKEY_CURRENT_USER, "Software\\Python", 0),
        (winreg.HKEY_LOCAL_MACHINE, "Software\\Python", winreg.KEY_WOW64_64KEY),
        (winreg.HKEY_LOCAL_MACHINE, "Software\\Python", winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall", 0),
        (winreg.HKEY_LOCAL_MACHINE, "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
         winreg.KEY_WOW64_64KEY),
        (winreg.HKEY_LOCAL_MACHINE, "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
         winreg.KEY_WOW64_32KEY),
    ):
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_READ | flag) as key:
                info = winreg.QueryInfoKey(key)
                parts.append("{}:{}:{}:{}".format(path, flag, info[0], info[2]))
        except OSError:
            parts.append("{}:{}:-".format(path, flag))
    return "|".join(parts)


register(ExtrasSource())
