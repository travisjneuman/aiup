"""What's new for tools with an update (port of macOS ``release_notes_lookup``, ``print_release_notes``).

The GitHub repository comes from the docs URL, the npm package's repository
field or the PyPI project links. The release must name the version whole
(1.2.0 never matches v11.2.0 or 1.2.01). Summaries are the release title and
its first two lines, at most 180 characters.

Cache: one JSON file per tool under ``<cache>/release-notes``. A found
release never changes. A miss is asked again after a day, or after an hour
when GitHub was busy or rate limited. ``AIUP_RELEASE_NOTES=0`` shows only the
links.
"""

from __future__ import annotations

import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, TextIO, Tuple

from aiup.errors import AiupError
from aiup.model import CatalogEntry
from aiup.paths import ensure_dir, refuse_symlink

from aiup.engine import host
from aiup.engine.cache import atomic_write_json, read_json

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.engine.context import Context

WORKERS = 6
SUMMARY_MAX = 180
MISS_RETRY_SECONDS = 86400
BUSY_RETRY_SECONDS = 3600
FETCH_TIMEOUT = 10.0

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_GITHUB = re.compile(r"github\.com[/:]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:[/#?]|$)")
_VERSION = re.compile(r"\d+(?:\.\d+)+[^\s,;()]*")
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_BULLET = re.compile(r"^(?:#+|[-*+]|\d+\.)\s*")
_SKIP_PREFIXES = ("what's changed", "full changelog", "changelog")


@dataclass(frozen=True)
class Note:
    """One tool's what's-new line."""

    tool: str
    summary: str
    link: str


def clean(text: object) -> str:
    """One line of plain text: no escapes, controls become spaces."""
    return _CONTROL.sub(" ", _ANSI.sub("", str(text or ""))).strip()


def github_repo(url: str) -> Optional[Tuple[str, str]]:
    """(owner, repo) from a GitHub URL, or None."""
    found = _GITHUB.search(url or "")
    return (found.group(1), found.group(2)) if found else None


def summarize(release: Dict[str, object]) -> str:
    """The title plus the first two meaningful lines of the body."""
    title = clean(release.get("name") or release.get("tag_name"))
    lines: List[str] = []
    for raw in str(release.get("body") or "").splitlines():
        line = clean(_MD_LINK.sub(r"\1", raw))
        line = _BULLET.sub("", line).strip(" *_`")
        lowered = line.lower()
        if line and lowered != title.lower() and not lowered.startswith(_SKIP_PREFIXES):
            lines.append(line)
        if len(lines) == 2:
            break
    text = title + (": " + "; ".join(lines) if lines else "")
    return text if len(text) <= SUMMARY_MAX else text[:SUMMARY_MAX - 3].rstrip() + "..."


class _Lookup:
    """Release-note lookups for one command; remembers who was busy."""

    def __init__(self, ctx: "Context", folder: Path) -> None:
        self.ctx = ctx
        self.folder = folder

    def _get(self, url: str) -> Tuple[Dict[str, object], bool]:
        """(JSON object or {}, busy)."""
        result = self.ctx.net.fetch(url, timeout=FETCH_TIMEOUT)
        busy = result.status in (0, 403, 429) or result.status >= 500
        data = result.json() if result.ok else None
        return (data if isinstance(data, dict) else {}), busy

    def repo(self, entry: CatalogEntry, version: str) -> Tuple[Optional[Tuple[str, str]], bool]:
        """The GitHub repository for a tool, and whether a registry was busy."""
        found = github_repo(entry.docs)
        if found:
            return found, False
        packages = _packages(entry, self.ctx.os_name)
        npm = packages.get("npm", "")
        if npm:
            url = ("https://registry.npmjs.org/" + urllib.parse.quote(npm, safe="@/") + "/"
                   + urllib.parse.quote(version, safe=""))
            data, busy = self._get(url)
            repo = data.get("repository")
            text = str(repo.get("url", "")) if isinstance(repo, dict) else str(repo or "")
            return github_repo(text), busy
        python = packages.get("uv") or packages.get("pipx", "")
        if python:
            data, busy = self._get("https://pypi.org/pypi/" + urllib.parse.quote(python, safe="") + "/json")
            info = data.get("info")
            if isinstance(info, dict):
                urls = info.get("project_urls")
                links = list(urls.values()) if isinstance(urls, dict) else []
                for link in links + [info.get("home_page") or ""]:
                    found = github_repo(str(link))
                    if found:
                        return found, busy
            return None, busy
        return None, False

    def lookup(self, entry: CatalogEntry, raw_version: str) -> Note:
        """One tool's note, from the cache when it still holds."""
        found = _VERSION.search(raw_version)
        version = found.group(0) if found else raw_version
        key = self.folder / (re.sub(r"[^A-Za-z0-9_.@-]", "_", entry.id) + ".json")
        cached = _cached(key, version)
        if cached is not None:
            return Note(entry.id, cached[0], cached[1] or entry.docs)
        text, link, busy = self._ask(entry, version)
        if not key.is_symlink():
            try:
                atomic_write_json(key, {"version": version, "summary": text, "url": link,
                                        "at": time.time(), "busy": busy})
            except (OSError, ValueError, AiupError):
                pass
        return Note(entry.id, text, link)

    def _ask(self, entry: CatalogEntry, version: str) -> Tuple[str, str, bool]:
        repo, busy = self.repo(entry, version)
        if repo is None:
            return "", entry.docs, busy
        owner, name = repo
        link = "https://github.com/" + owner + "/" + name + "/releases"
        bare = version.lstrip("v")
        same = re.compile(r"(?<![\d.])" + re.escape(bare) + r"(?![\d])")
        for path in ("latest", "tags/v" + bare, "tags/" + bare):
            if self.ctx.net.github_limited:
                return "", link, True
            result = self.ctx.net.github("repos/" + owner + "/" + name + "/releases/" + path,
                                         timeout=FETCH_TIMEOUT)
            if result.status in (0, 403, 429) or result.status >= 500:
                return "", link, True
            if result.status == 404 and path == "latest":
                break  # the project does not publish releases
            release = result.json()
            if not isinstance(release, dict):
                continue
            if same.search(str(release.get("tag_name", "")) + " " + str(release.get("name", ""))):
                page = str(release.get("html_url") or "")
                return summarize(release), (page if page.startswith("https://github.com/") else link), busy
        return "", link, busy


def _packages(entry: CatalogEntry, os_name: str) -> Dict[str, str]:
    """channel -> package for the entry on this OS."""
    found: Dict[str, str] = {}
    for target in entry.targets_for(os_name):
        found.setdefault(target.channel, target.package)
    return found


def _cached(key: Path, version: str) -> Optional[Tuple[str, str]]:
    """(summary, url) when the cache still answers for this version."""
    if key.is_symlink():
        return None
    data = read_json(key, 65536)
    if not isinstance(data, dict) or data.get("version") != version:
        return None
    summary = str(data.get("summary") or "")
    wait = BUSY_RETRY_SECONDS if data.get("busy") else MISS_RETRY_SECONDS
    try:
        at = float(data.get("at", 0) or 0)
    except (TypeError, ValueError):
        at = 0.0
    if summary or time.time() - at < wait:
        return summary, str(data.get("url") or "")
    return None


def lookup_notes(ctx: "Context", catalog: "Catalog", items: Sequence[Tuple[str, str]]) -> List[Note]:
    """Notes for (tool, version) pairs, in order. Links only with AIUP_RELEASE_NOTES=0."""
    pairs = [(catalog.get(tool), version) for tool, version in items if tool and version]
    entries = [(entry, version) for entry, version in pairs if entry is not None]
    if not entries:
        return []
    if not ctx.config.release_notes:
        return [Note(entry.id, "", entry.docs) for entry, _ in entries]
    folder = ctx.cache.release_notes
    try:
        refuse_symlink(folder)
        ensure_dir(folder)
    except (OSError, AiupError):
        return [Note(entry.id, "", entry.docs) for entry, _ in entries]
    finder = _Lookup(ctx, folder)
    return host.map_threads(min(WORKERS, len(entries)), lambda item: finder.lookup(item[0], item[1]), entries)


def print_release_notes(ctx: "Context", catalog: "Catalog", items: Sequence[Tuple[str, str]],
                        out: Optional[TextIO] = None) -> None:
    """The "What's new" block (stdout) for (tool, new version) pairs."""
    if not items:
        return
    stream = out or sys.stdout
    try:
        notes = lookup_notes(ctx, catalog, items)
    except Exception:  # noqa: BLE001  release notes must never fail a command
        return
    if not notes:
        return
    shade, reset = _colors(ctx, stream)
    stream.write("\n  " + shade + "What's new" + reset + "\n")
    for note in notes:
        stream.write("  " + shade + note.tool + reset + " · " + (clean(note.summary) or "release notes") + "\n")
        if note.link:
            stream.write("      " + clean(note.link) + "\n")
    stream.flush()


def _colors(ctx: "Context", stream: TextIO) -> Tuple[str, str]:
    try:
        tty = stream.isatty()
    except (AttributeError, ValueError, OSError):
        tty = False
    if tty and not ctx.config.no_color:
        return "\033[38;5;81m", "\033[0m"
    return "", ""
