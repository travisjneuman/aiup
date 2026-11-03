"""Load and validate the catalog (design doc sections 5.1 to 5.7).

Four files, all UTF-8 TSV with ``#`` comment lines:

- ``macos/catalog/manifest.tsv``: the base list (id, category, kind,
  lifecycle, label, docs, macOS target, endpoint).
- ``catalog/platforms.tsv``: Linux and Windows targets. When it is missing the
  catalog still loads, with no Linux or Windows targets, and
  :attr:`Catalog.notice` says so.
- ``catalog/categories.tsv``: category id, order, name, emoji, blurb.
- ``catalog/tool-meta.tsv``: aliases, commands, processes, data paths.

Anything that breaks the schema stops with a :class:`CatalogError` naming the
file and line, the role ``catalog_validate`` plays in macos/aiup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Mapping, Optional, Pattern, Sequence, Set, Tuple

from aiup.catalog.targets import (
    OS_NAMES, TARGET_COLUMNS, CellRef, check_default, order_targets, parse_cell,
)
from aiup.catalog.userdata import check_data_path
from aiup.errors import CatalogError
from aiup.model import CatalogEntry, Target
from aiup.version import AIUP_VERSION

VERSION_HEADER = "# aiup-runtime-version:"
LIFECYCLES = ("active", "maintenance", "sunset", "archived")
PSEUDO_CATEGORIES = ("updates", "packages", "detected")
REQUIRED_TOOL = "fzf"

PLATFORM_COLUMNS: Tuple[str, ...] = ("id",) + TARGET_COLUMNS + ("linux_default", "windows_default", "notes")
META_COLUMNS: Tuple[str, ...] = ("id", "aliases", "commands", "processes", "linux_data", "windows_data")

_ID = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?")
_ALIAS = re.compile(r"[a-z0-9][a-z0-9._-]*")
_COMMAND = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
_PROCESS = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9 ._+-]*[A-Za-z0-9._+-])?")
_CATEGORY_ID = re.compile(r"[a-z0-9][a-z0-9-]*(?:/[a-z0-9-]+)?")


@dataclass(frozen=True)
class Category:
    """One category from catalog/categories.tsv."""

    id: str
    order: int
    name: str
    emoji: str
    blurb: str

    @property
    def pseudo(self) -> bool:
        """True for updates, packages and detected, which hold no catalog tools."""
        return self.id in PSEUDO_CATEGORIES


@dataclass(frozen=True)
class CatalogPaths:
    """Where the four catalog files are."""

    manifest: Path
    platforms: Path
    categories: Path
    tool_meta: Path


@dataclass(frozen=True)
class Catalog:
    """The loaded catalog: entries in manifest order, categories in display order."""

    version: str
    entries: Tuple[CatalogEntry, ...]
    categories: Tuple[Category, ...]
    has_platforms: bool
    notice: str = ""
    _by_id: Mapping[str, CatalogEntry] = field(default_factory=dict, repr=False, compare=False)
    _aliases: Mapping[str, str] = field(default_factory=dict, repr=False, compare=False)
    _categories: Mapping[str, Category] = field(default_factory=dict, repr=False, compare=False)

    def ids(self) -> Tuple[str, ...]:
        """Every catalog id, in manifest order."""
        return tuple(entry.id for entry in self.entries)

    def get(self, tool_id: str) -> Optional[CatalogEntry]:
        """The entry for an exact id, or None."""
        return self._by_id.get(tool_id)

    def resolve(self, name: str) -> Optional[str]:
        """An id or alias to its catalog id (macOS ``resolve_tools``), or None."""
        if name in self._by_id:
            return name
        return self._aliases.get(name)

    def category(self, category_id: str) -> Optional[Category]:
        """The category with this id, or None."""
        return self._categories.get(category_id)

    def tool_categories(self) -> Tuple[Category, ...]:
        """Categories that hold catalog tools, in display order."""
        return tuple(c for c in self.categories if not c.pseudo)

    def in_category(self, category_id: str) -> Tuple[CatalogEntry, ...]:
        """Entries in one category, in manifest order."""
        return tuple(e for e in self.entries if e.category == category_id)

    def available_on(self, os_name: str) -> Tuple[CatalogEntry, ...]:
        """Entries with at least one target for this OS."""
        return tuple(e for e in self.entries if e.available_on(os_name))


@dataclass(frozen=True)
class _ManifestRow:
    id: str
    category: str
    kind: str
    lifecycle: str
    label: str
    docs: str
    target: str
    endpoint: str


@dataclass(frozen=True)
class _PlatformRow:
    targets: Dict[str, Tuple[Target, ...]]
    defaults: Dict[str, str]
    notes: str


@dataclass(frozen=True)
class _MetaRow:
    aliases: Tuple[str, ...]
    commands: Tuple[str, ...]
    processes: Tuple[str, ...]
    user_data: Dict[str, Tuple[str, ...]]


def default_paths(root: Path) -> CatalogPaths:
    """The catalog files under a checkout or generation root."""
    catalog_dir = root / "catalog"
    return CatalogPaths(
        manifest=root / "macos" / "catalog" / "manifest.tsv",
        platforms=catalog_dir / "platforms.tsv",
        categories=catalog_dir / "categories.tsv",
        tool_meta=catalog_dir / "tool-meta.tsv",
    )


def paths_from_catalog_dir(catalog_dir: Path) -> CatalogPaths:
    """Paths when ``AIUP_CATALOG_DIR`` names the ``catalog/`` folder itself."""
    return default_paths(catalog_dir.parent)


def _read_lines(path: Path, label: str) -> List[str]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            text = handle.read()
    except FileNotFoundError as exc:
        raise CatalogError("catalog file not found: " + str(path)) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise CatalogError("could not read {}: {}".format(label, exc)) from exc
    if "\r" in text:
        raise CatalogError("{} has Windows line endings (CR); it must use LF".format(label))
    return text.split("\n")


def _rows(lines: Sequence[str]) -> Iterator[Tuple[int, List[str]]]:
    """Data rows with their 1-based line numbers; comments and blank lines skipped."""
    for number, line in enumerate(lines, start=1):
        if not line.strip() or line.startswith("#"):
            continue
        yield number, line.split("\t")


def _version_header(lines: Sequence[str]) -> str:
    for line in lines:
        if line.startswith(VERSION_HEADER):
            return line[len(VERSION_HEADER):].strip()
    return ""


def _check_version(lines: Sequence[str], label: str, expected: str) -> None:
    found = _version_header(lines)
    if found != expected:
        raise CatalogError("{} version '{}' does not match aiup '{}'".format(label, found, expected))


def _fit(cells: List[str], width: int, optional_tail: int, where: str) -> List[str]:
    """Pad missing trailing optional cells; refuse too few or too many columns."""
    while len(cells) > width and cells[-1] == "":
        cells = cells[:-1]
    if len(cells) > width:
        raise CatalogError("{} columns, expected at most {}".format(len(cells), width), where)
    if len(cells) < width - optional_tail:
        raise CatalogError("{} columns, expected at least {}".format(len(cells), width - optional_tail), where)
    return cells + [""] * (width - len(cells))


def _load_manifest(path: Path, label: str, expected: str) -> List[_ManifestRow]:
    lines = _read_lines(path, label)
    _check_version(lines, label, expected)
    rows: List[_ManifestRow] = []
    seen: Set[str] = set()
    for number, cells in _rows(lines):
        where = "{} line {}".format(label, number)
        c = _fit(cells, 8, 2, where)
        row = _ManifestRow(id=c[0], category=c[1], kind=c[2], lifecycle=c[3], label=c[4],
                           docs=c[5], target=c[6], endpoint=c[7])
        if not _ID.fullmatch(row.id):
            raise CatalogError("unstable id '{}'".format(row.id), where)
        if row.id in seen:
            raise CatalogError("id '{}' repeats".format(row.id), where)
        seen.add(row.id)
        if not (row.category and row.kind and row.label and row.docs):
            raise CatalogError("row for '{}' needs a category, kind, label and docs URL".format(row.id), where)
        if row.lifecycle not in LIFECYCLES:
            raise CatalogError("'{}' has invalid lifecycle '{}'".format(row.id, row.lifecycle), where)
        rows.append(row)
    if not rows:
        raise CatalogError(label + " has no tools")
    return rows


def _load_categories(path: Path, label: str) -> List[Category]:
    out: List[Category] = []
    seen: Set[str] = set()
    for number, cells in _rows(_read_lines(path, label)):
        where = "{} line {}".format(label, number)
        c = _fit(cells, 5, 1, where)
        if not _CATEGORY_ID.fullmatch(c[0]):
            raise CatalogError("bad category id '{}'".format(c[0]), where)
        if c[0] in seen:
            raise CatalogError("category '{}' repeats".format(c[0]), where)
        if not c[1].isdigit() or not c[2]:
            raise CatalogError("category '{}' needs a numeric order and a name".format(c[0]), where)
        seen.add(c[0])
        out.append(Category(id=c[0], order=int(c[1]), name=c[2], emoji=c[3], blurb=c[4]))
    out.sort(key=lambda cat: (cat.order, cat.id))
    return out


def _load_platforms(path: Path, label: str, expected: str, ids: Set[str]) -> Dict[str, _PlatformRow]:
    lines = _read_lines(path, label)
    _check_version(lines, label, expected)
    out: Dict[str, _PlatformRow] = {}
    width = len(PLATFORM_COLUMNS)
    for number, cells in _rows(lines):
        where = "{} line {}".format(label, number)
        c = _fit(cells, width, 1, where)
        tool = c[0]
        if tool not in ids:
            raise CatalogError("id '{}' is not in manifest.tsv".format(tool), where)
        if tool in out:
            raise CatalogError("id '{}' repeats".format(tool), where)
        found: Dict[str, List[Target]] = {name: [] for name in OS_NAMES}
        for index, column in enumerate(TARGET_COLUMNS, start=2):
            ref = CellRef(label, number, column, index)
            os_name = column.split("_", 1)[0]
            found[os_name].extend(parse_cell(ref, c[index - 1]))
        targets: Dict[str, Tuple[Target, ...]] = {}
        defaults: Dict[str, str] = {}
        for offset, os_name in enumerate(OS_NAMES):
            index = len(TARGET_COLUMNS) + 2 + offset
            ref = CellRef(label, number, os_name + "_default", index)
            default = check_default(ref, os_name, c[index - 1], tuple(found[os_name]))
            defaults[os_name] = default
            targets[os_name] = order_targets(os_name, tuple(found[os_name]), default)
        out[tool] = _PlatformRow(targets=targets, defaults=defaults, notes=c[width - 1])
    if REQUIRED_TOOL not in out:
        raise CatalogError("{} has no {} row; the picker needs it".format(label, REQUIRED_TOOL))
    return out


def _comma_list(raw: str, pattern: Pattern[str], what: str, where: str) -> Tuple[str, ...]:
    if raw == "":
        return ()
    items = raw.split(",")
    for item in items:
        if not pattern.fullmatch(item):
            raise CatalogError("bad {} '{}' in '{}'".format(what, item, raw), where)
    return tuple(items)


def _data_list(os_name: str, raw: str, where: str) -> Tuple[str, ...]:
    if raw == "":
        return ()
    return tuple(check_data_path(os_name, item, where) for item in raw.split(";"))


def _load_meta(path: Path, label: str, ids: Set[str]) -> Dict[str, _MetaRow]:
    out: Dict[str, _MetaRow] = {}
    alias_owner: Dict[str, str] = {}
    for number, cells in _rows(_read_lines(path, label)):
        where = "{} line {}".format(label, number)
        c = _fit(cells, len(META_COLUMNS), 5, where)
        tool = c[0]
        if tool not in ids:
            raise CatalogError("id '{}' is not in manifest.tsv".format(tool), where)
        if tool in out:
            raise CatalogError("id '{}' repeats".format(tool), where)
        aliases = _comma_list(c[1], _ALIAS, "alias", where)
        for alias in aliases:
            if alias in ids:
                raise CatalogError("alias '{}' is also a catalog id".format(alias), where)
            if alias in alias_owner:
                raise CatalogError("alias '{}' already belongs to '{}'".format(alias, alias_owner[alias]), where)
            alias_owner[alias] = tool
        out[tool] = _MetaRow(
            aliases=aliases,
            commands=_comma_list(c[2], _COMMAND, "command", where),
            processes=_comma_list(c[3], _PROCESS, "process name", where),
            user_data={"linux": _data_list("linux", c[4], where),
                       "windows": _data_list("windows", c[5], where)},
        )
    return out


def _entry(row: _ManifestRow, platform: Optional[_PlatformRow], meta: Optional[_MetaRow]) -> CatalogEntry:
    empty_targets: Dict[str, Tuple[Target, ...]] = {name: () for name in OS_NAMES}
    return CatalogEntry(
        id=row.id, category=row.category, lifecycle=row.lifecycle, label=row.label,
        docs=row.docs, endpoint=row.endpoint, macos_kind=row.kind, macos_target=row.target,
        targets=platform.targets if platform else empty_targets,
        defaults=platform.defaults if platform else {name: "" for name in OS_NAMES},
        aliases=meta.aliases if meta else (),
        # No tool-meta row: the command is the id, as binary_of_tool defaults.
        commands=meta.commands if meta else (row.id,),
        processes=meta.processes if meta else (),
        user_data=meta.user_data if meta else {name: () for name in OS_NAMES},
        notes=platform.notes if platform else "",
    )


MISSING_PLATFORMS_NOTICE = (
    "catalog/platforms.tsv is missing, so no Linux or Windows install targets are loaded. "
    "Every catalog tool shows as not available on this system."
)


def load_catalog(paths: CatalogPaths, expected_version: str = AIUP_VERSION) -> Catalog:
    """Read and validate all four catalog files. Raises CatalogError."""
    manifest = _load_manifest(paths.manifest, "macos/catalog/manifest.tsv", expected_version)
    ids = {row.id for row in manifest}
    categories = _load_categories(paths.categories, "catalog/categories.tsv")
    known = {c.id for c in categories}
    for row in manifest:
        if row.category not in known or row.category in PSEUDO_CATEGORIES:
            raise CatalogError("'{}' has category '{}', which is not in catalog/categories.tsv"
                               .format(row.id, row.category))
    has_platforms = paths.platforms.is_file()
    platforms = (_load_platforms(paths.platforms, "catalog/platforms.tsv", expected_version, ids)
                 if has_platforms else {})
    meta = _load_meta(paths.tool_meta, "catalog/tool-meta.tsv", ids)
    entries = tuple(_entry(row, platforms.get(row.id), meta.get(row.id)) for row in manifest)
    aliases = {alias: entry.id for entry in entries for alias in entry.aliases}
    return Catalog(
        version=expected_version,
        entries=entries,
        categories=tuple(categories),
        has_platforms=has_platforms,
        notice="" if has_platforms else MISSING_PLATFORMS_NOTICE,
        _by_id={entry.id: entry for entry in entries},
        _aliases=aliases,
        _categories={c.id: c for c in categories},
    )
