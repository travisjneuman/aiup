"""``go install`` binaries (channel ``go``, design doc section 6.3).

Versions come from the binaries themselves (``go version -m``), latest
versions from proxy.golang.org, and updates run ``go install module@latest``.
Go has no uninstall command, so removing deletes the binary from the Go bin
folder.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers.base import Provider
from aiup.providers.script import (
    ALL_OSES, READ_MAX_BYTES, READ_TIMEOUT, empty_action, home, is_windows, path_inside, path_setup_step,
    remove_file_step, which,
)

if TYPE_CHECKING:
    from aiup.engine.context import Context

_INVENTORY_MAX = 8 * 1024 * 1024
_TTL = 60.0
_MAX_PREFIX_TRIES = 4


class Binary(NamedTuple):
    """What ``go version -m`` says about one binary."""

    file: str
    package: str    # path line: the package that was installed
    module: str     # mod line: the module it belongs to
    version: str    # "" for (devel) builds


def package_path(target: Target) -> str:
    """The package path without any ``@version``: aiup always installs ``@latest``."""
    return target.package.split("@", 1)[0]


def binary_name(package: str) -> str:
    """The command ``go install`` makes: the last path element, skipping ``/vN``."""
    parts = [p for p in package.split("/") if p]
    if len(parts) > 1 and parts[-1][:1] == "v" and parts[-1][1:].isdigit():
        parts = parts[:-1]
    return parts[-1] if parts else ""


def go_read(ctx: "Context", argv: Sequence[str], timeout: float = READ_TIMEOUT,
            max_bytes: int = READ_MAX_BYTES) -> Optional[str]:
    """Run a read-only go command; stdout, or None when it failed.

    It runs in the home folder with ``GOTOOLCHAIN=local``, so a go.mod in the
    current folder can never make a read download another Go toolchain.
    """
    try:
        result: Any = ctx.run_read(argv, timeout, max_bytes, cwd=str(home(ctx)), env={"GOTOOLCHAIN": "local"})
    except (OSError, ValueError):
        return None
    if not getattr(result, "ok", False):
        return None
    out = getattr(result, "stdout", "")
    return out if isinstance(out, str) else None


_BIN_CACHE: Dict[str, Tuple[float, Optional[Path]]] = {}
_LOCK = threading.Lock()


def bin_dir(ctx: "Context") -> Optional[Path]:
    """``GOBIN``, else the first ``GOPATH`` entry's ``bin``, else ``~/go/bin``."""
    go = which(ctx, "go")
    if not go:
        return None
    with _LOCK:
        cached = _BIN_CACHE.get(go)
        if cached and time.monotonic() - cached[0] < _TTL:
            return cached[1]
    out = go_read(ctx, (go, "env", "GOBIN", "GOPATH"), max_bytes=64 * 1024)
    lines = (out or "").splitlines() + ["", ""]
    gobin, gopath = lines[0].strip(), lines[1].strip().split(os.pathsep)[0]
    if gobin and os.path.isabs(gobin):
        found: Optional[Path] = Path(gobin)
    elif gopath and os.path.isabs(gopath):
        found = Path(gopath) / "bin"
    else:
        found = home(ctx) / "go" / "bin"
    with _LOCK:
        _BIN_CACHE[go] = (time.monotonic(), found)
    return found


def parse_version_m(text: str) -> List[Binary]:
    """Parse ``go version -m`` output for one file or a whole folder."""
    binaries: List[Binary] = []
    current: Optional[List[str]] = None
    for line in text.splitlines():
        if not line.startswith("\t"):
            if current is not None:
                binaries.append(Binary(*current))
            head = line.rsplit(": go", 1)[0] if ": go" in line else ""
            current = [head, "", "", ""] if head else None
            continue
        if current is None:
            continue
        fields = line.strip().split("\t")
        if fields[0] == "path" and len(fields) > 1:
            current[1] = fields[1]
        elif fields[0] == "mod" and len(fields) > 2:
            current[2] = fields[1]
            current[3] = "" if fields[2] == "(devel)" else fields[2].lstrip("v")
    if current is not None:
        binaries.append(Binary(*current))
    return binaries


def read_binary(ctx: "Context", path: str, run_go: bool = True) -> Optional[Binary]:
    """What ``go version -m`` says about one file.

    The build info is read in this process (``detect.files.go_buildinfo``), so
    checking many files starts no process. With ``run_go``, ``go version -m``
    runs for a binary that reader cannot parse (built before Go 1.18).
    """
    go = which(ctx, "go")
    if not go or not os.path.isfile(path):
        return None
    # Imported here so loading the providers does not load the detection package.
    from aiup.detect.files import go_buildinfo

    info = go_buildinfo(path)
    if info is not None:
        package, module, version = info
        return Binary(path, package, module, "" if version == "(devel)" else version.lstrip("v"))
    if not run_go:
        return None
    found = parse_version_m(go_read(ctx, (go, "version", "-m", path)) or "")
    return found[0] if found and found[0].package else None


def _module_candidates(package: str) -> List[str]:
    """The package path, then shorter prefixes (the module may sit higher up)."""
    parts = package.split("/")
    candidates = ["/".join(parts[:end]) for end in range(len(parts), 2, -1)]
    return candidates[:_MAX_PREFIX_TRIES] or [package]


class GoProvider(Provider):
    """Commands installed with ``go install``."""

    name = "go"
    oses = ALL_OSES
    scope = "user"
    lane = "go"
    exclusive = False
    targeted_update = True

    def available(self, ctx: "Context") -> bool:
        return which(ctx, "go") is not None

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        path = self._binary_path(ctx, target)
        info = read_binary(ctx, path) if path else None
        if info is None or info.package != package_path(target):
            return None
        return Installed(info.version, path, "user", self.name)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        path = self._binary_path(ctx, target)
        info = read_binary(ctx, path) if path else None
        modules = [info.module] if info and info.module else _module_candidates(package_path(target))
        for module in modules:
            version = ctx.net.go_latest(module, timeout)
            if version:
                return Latest(version, "proxy.golang.org")
        return Latest("", "proxy.golang.org", "the Go module proxy did not answer")

    def install(self, ctx: "Context", target: Target) -> Action:
        return self._install(ctx, target, "install")

    def update(self, ctx: "Context", target: Target) -> Action:
        return self._install(ctx, target, "update")

    def remove(self, ctx: "Context", target: Target) -> Action:
        path = self._binary_path(ctx, target)
        if not path or not os.path.isfile(path):
            return empty_action(target, "remove", "Nothing to remove: " + binary_name(package_path(target)) + " is not in the Go bin folder.")
        step = remove_file_step(ctx, path, "remove " + path)
        return Action(tool=target.package, op="remove", channel=self.name, steps=(step,))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        folder = bin_dir(ctx)
        if folder is None or not path_inside(path, str(folder)):
            return None
        # In-process only: ownership checks run for many files, so no process per file.
        info = read_binary(ctx, path, run_go=False)
        return Ownership(self.name, info.package, "exact") if info else None

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        go = which(ctx, "go")
        folder = bin_dir(ctx)
        if not go or folder is None or not folder.is_dir():
            return ()
        out = go_read(ctx, (go, "version", "-m", str(folder)), timeout=30.0, max_bytes=_INVENTORY_MAX) or ""
        return tuple(PackageRecord(self.name, b.package, b.version, "user", True, (b.file,))
                     for b in parse_version_m(out) if b.package)

    def _binary_path(self, ctx: "Context", target: Target) -> str:
        folder = bin_dir(ctx)
        name = binary_name(package_path(target))
        if folder is None or not name:
            return ""
        return str(folder / (name + (".exe" if is_windows(ctx) else "")))

    def _install(self, ctx: "Context", target: Target, op: str) -> Action:
        go = which(ctx, "go")
        if not go:
            return empty_action(target, op, "go is not on PATH.")
        spec = package_path(target) + "@latest"
        steps: List[Step] = [Step(argv=(go, "install", spec), label="go install " + spec)]
        folder = bin_dir(ctx)
        setup = path_setup_step(ctx, str(folder)) if folder is not None else None
        if setup is not None:
            steps.append(setup)
        return Action(tool=target.package, op=op, channel=self.name, steps=tuple(steps))
