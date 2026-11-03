"""winget provider (Windows Package Manager), plus helpers the Windows providers share.

Rules from design doc sections 6.3, 7.4 and open questions 5 and 6:

- Reads prefer machine-readable forms. When the ``Microsoft.WinGet.Client``
  PowerShell module is installed, one ``Get-WinGetPackage`` call answers the
  inventory and the update list. Otherwise ``winget export --include-versions``
  (JSON) gives the inventory and ``winget upgrade`` (a table) the update list.
  Single packages use ``winget list|show --id ID --exact``.
- Tables are parsed without reading any header word, because headers are
  translated. The header only gives column start positions, measured in
  terminal cells so wide East Asian characters line up. Which column is which
  comes from the command aiup ran: winget drops ``Source`` when one source
  was named and drops ``Available`` when nothing has an update. Footer lines,
  rows shortened with an ellipsis and spinner noise are recognized and left
  out (``proc.decode_output`` already removes carriage-return redraws).
- Every call passes ``--accept-source-agreements --disable-interactivity``.
  Installs, updates and removals add ``--silent`` and never ``--force``.
- A new install asks for ``--scope user`` when the package has a user-scope
  installer. Updates and removals of a user-scope copy pass ``--scope user``.
  Other steps are ``uac-possible``: the installer may raise Windows' own
  approval prompt, which the engine allows only from a desktop session.
- winget never installs an older build over a newer one: aiup never passes
  ``--force`` or ``--version``, and winget refuses a downgrade by itself. When
  winget reports that a newer build is already installed (an app that updated
  itself), ``explain_exit`` turns that into ``self-updated``.
- winget can be unusable: missing App Installer, or a session where the App
  Execution Alias cannot start (Windows Server over SSH, services, SYSTEM).
  ``available`` is then False and ``unavailable_reason`` says why.

The helpers every Windows provider shares (``run_w``, ``Memo``, PowerShell
JSON calls, exit code forms, Windows folders) live in ``_win.py``.
"""

from __future__ import annotations

import os
import re
import threading
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Dict, FrozenSet, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target
from aiup.providers._win import (BULK_MAX_BYTES, MEMO_TTL, READ_TIMEOUT, SLOW_TIMEOUT, STORE_NOTE, WINDOWS, Memo,
                                 ReadOut, any_powershell, code_forms, env_dir, first_line, home_dir, is_windows,
                                 newest, path_parts, powershell_json, read_json_file, run_w, scratch_file, under,
                                 unsigned, which)
from aiup.providers.base import Provider
from aiup.versions import version_cmp

if TYPE_CHECKING:
    from aiup.engine.context import Context


# ---------------------------------------------------------------------------
# winget exit codes (winget-cli doc/windows/package-manager/winget/returnCodes.md)
# ---------------------------------------------------------------------------

CTRL_SIGNAL_RECEIVED = 0x8A150005
DOWNLOAD_FAILED = 0x8A150008
NO_APPLICABLE_INSTALLER = 0x8A150010
INSTALLER_HASH_MISMATCH = 0x8A150011
NO_APPLICATIONS_FOUND = 0x8A150014
MULTIPLE_APPLICATIONS_FOUND = 0x8A150016
NO_MANIFEST_FOUND = 0x8A150017
COMMAND_REQUIRES_ADMIN = 0x8A150019
MSSTORE_BLOCKED_BY_POLICY = 0x8A15001B
MSSTORE_APP_BLOCKED_BY_POLICY = 0x8A15001C
UPDATE_NOT_APPLICABLE = 0x8A15002B
UPDATE_ALL_HAS_FAILURE = 0x8A15002C
BLOCKED_BY_POLICY = 0x8A15003A
PACKAGE_AGREEMENTS_NOT_ACCEPTED = 0x8A150041
SOURCE_OPEN_FAILED = 0x8A150045
SOURCE_AGREEMENTS_NOT_ACCEPTED = 0x8A150046
FAILED_TO_OPEN_ALL_SOURCES = 0x8A15004B
UPGRADE_VERSION_NOT_NEWER = 0x8A15004F
UPGRADE_VERSION_UNKNOWN = 0x8A150050
INSTALLER_PROHIBITS_ELEVATION = 0x8A150056
PACKAGE_ALREADY_INSTALLED = 0x8A150061
PACKAGE_IS_PINNED = 0x8A150068
APPTERMINATION_RECEIVED = 0x8A15006A
SERVICE_UNAVAILABLE = 0x8A15006D
ADMIN_CONTEXT_ACTION_PROHIBITED = 0x8A15007D
UPDATE_INSTALL_TECHNOLOGY_MISMATCH = 0x8A15008E
INSTALL_PACKAGE_IN_USE = 0x8A150101
INSTALL_IN_PROGRESS = 0x8A150102
INSTALL_FILE_IN_USE = 0x8A150103
INSTALL_DISK_FULL = 0x8A150105
INSTALL_NO_NETWORK = 0x8A150107
INSTALL_REBOOT_REQUIRED_TO_FINISH = 0x8A150109
INSTALL_REBOOT_REQUIRED_FOR_INSTALL = 0x8A15010A
INSTALL_REBOOT_INITIATED = 0x8A15010B
INSTALL_CANCELLED_BY_USER = 0x8A15010C
INSTALL_ALREADY_INSTALLED = 0x8A15010D
INSTALL_DOWNGRADE = 0x8A15010E
INSTALL_BLOCKED_BY_POLICY = 0x8A15010F
INSTALL_PACKAGE_IN_USE_BY_APPLICATION = 0x8A150111
INSTALL_UPGRADE_NOT_SUPPORTED = 0x8A150114

APP_OPEN_NOTE = "the app is open; close it and run aiup again"
NETWORK_NOTE = "winget could not reach its source; try again later"
POLICY_NOTE = "blocked by a Windows policy on this computer"

# (result, note). result "" means: keep the engine's own result, add the note.
_EXIT_MEANINGS: Mapping[int, Tuple[str, str]] = {
    UPDATE_NOT_APPLICABLE: ("unchanged", "winget has no newer version for this package"),
    UPGRADE_VERSION_NOT_NEWER: ("unchanged", "winget has no newer version for this package"),
    UPGRADE_VERSION_UNKNOWN: ("skipped", "winget cannot read the installed version, so it will not update it"),
    INSTALL_DOWNGRADE: ("self-updated", "a newer build is already installed (the app updated itself); aiup leaves it"),
    INSTALL_ALREADY_INSTALLED: ("unchanged", "already installed"),
    PACKAGE_ALREADY_INSTALLED: ("unchanged", "already installed"),
    PACKAGE_IS_PINNED: ("skipped", "pinned in winget; run winget pin remove to allow updates"),
    INSTALL_PACKAGE_IN_USE: ("deferred", APP_OPEN_NOTE),
    INSTALL_FILE_IN_USE: ("deferred", APP_OPEN_NOTE),
    INSTALL_PACKAGE_IN_USE_BY_APPLICATION: ("deferred", "another app is using it; close it and run aiup again"),
    INSTALL_IN_PROGRESS: ("deferred", "another installation is running; run aiup again when it finishes"),
    INSTALL_REBOOT_REQUIRED_FOR_INSTALL: ("deferred", "restart Windows, then run aiup again"),
    INSTALL_REBOOT_REQUIRED_TO_FINISH: ("", "restart Windows to finish"),
    INSTALL_REBOOT_INITIATED: ("", "Windows will restart to finish"),
    INSTALL_CANCELLED_BY_USER: ("cancelled", "the installer was cancelled"),
    CTRL_SIGNAL_RECEIVED: ("cancelled", "stopped"),
    APPTERMINATION_RECEIVED: ("cancelled", "stopped"),
    COMMAND_REQUIRES_ADMIN: ("deferred", "needs an elevated terminal"),
    ADMIN_CONTEXT_ACTION_PROHIBITED: ("deferred", "installed for your account only; run aiup from a normal (not elevated) terminal"),
    INSTALLER_PROHIBITS_ELEVATION: ("deferred", "this installer refuses to run elevated; run aiup from a normal terminal"),
    NO_APPLICABLE_INSTALLER: ("failed", "winget has no installer for this computer or scope"),
    UPDATE_INSTALL_TECHNOLOGY_MISMATCH: ("skipped", "the update uses a different installer type; remove and install again to move to it"),
    INSTALL_UPGRADE_NOT_SUPPORTED: ("failed", "this installer cannot update in place"),
    INSTALLER_HASH_MISMATCH: ("failed", "the download did not match the manifest hash; nothing was installed"),
    NO_APPLICATIONS_FOUND: ("failed", "winget does not find this package"),
    NO_MANIFEST_FOUND: ("failed", "winget does not find this package"),
    MULTIPLE_APPLICATIONS_FOUND: ("failed", "winget matched more than one package"),
    DOWNLOAD_FAILED: ("failed", NETWORK_NOTE),
    INSTALL_NO_NETWORK: ("failed", NETWORK_NOTE),
    SOURCE_OPEN_FAILED: ("failed", NETWORK_NOTE),
    FAILED_TO_OPEN_ALL_SOURCES: ("failed", NETWORK_NOTE),
    SERVICE_UNAVAILABLE: ("failed", "a Windows service winget needs is busy; try again later"),
    INSTALL_DISK_FULL: ("failed", "the disk is full"),
    SOURCE_AGREEMENTS_NOT_ACCEPTED: ("failed", "winget source agreements were not accepted"),
    PACKAGE_AGREEMENTS_NOT_ACCEPTED: ("failed", "the package agreement was not accepted"),
    BLOCKED_BY_POLICY: ("skipped", POLICY_NOTE),
    INSTALL_BLOCKED_BY_POLICY: ("skipped", POLICY_NOTE),
    MSSTORE_BLOCKED_BY_POLICY: ("skipped", POLICY_NOTE),
    MSSTORE_APP_BLOCKED_BY_POLICY: ("skipped", POLICY_NOTE),
    UPDATE_ALL_HAS_FAILURE: ("failed", "some packages did not update; run winget upgrade to see which"),
}

_REBOOT_OK = (INSTALL_REBOOT_REQUIRED_TO_FINISH, INSTALL_REBOOT_INITIATED)
INSTALL_OK = code_forms(0, PACKAGE_ALREADY_INSTALLED, INSTALL_ALREADY_INSTALLED, *_REBOOT_OK)
UPDATE_OK = code_forms(0, UPDATE_NOT_APPLICABLE, UPGRADE_VERSION_NOT_NEWER, *_REBOOT_OK)
REMOVE_OK = code_forms(0, *_REBOOT_OK)


def explain_winget_exit(code: Optional[int]) -> Optional[Tuple[str, str]]:
    """aiup's reading of a winget exit status: ``(result, note)``, or None for 0 and unknown codes.

    ``result`` uses the docs/scripting.md run vocabulary; "" keeps the result
    the engine works out itself and only adds the note.
    """
    if code is None or code == 0:
        return None
    return _EXIT_MEANINGS.get(unsigned(code))


# ---------------------------------------------------------------------------
# winget table parsing (localization-safe, see the module docstring)
# ---------------------------------------------------------------------------

ELLIPSIS = "…"
_SEPARATOR = re.compile(r"^\s*-{4,}\s*$")
_ID_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]*$")
_STORE_ID = re.compile(r"^[A-Za-z0-9]{6,20}$")
_SHA256 = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")


class WingetRow(NamedTuple):
    """One parsed table row. ``truncated`` is True when winget shortened the id or a version."""

    name: str
    id: str
    version: str
    available: str
    source: str
    truncated: bool


def cell_width(char: str) -> int:
    """Terminal cells one character takes (2 for wide East Asian characters)."""
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def split_cells(line: str, starts: Sequence[int]) -> List[str]:
    """Cut ``line`` into cells at the given cell positions, counting wide characters as two."""
    cells = [""] * len(starts)
    column, position = 0, 0
    for char in line:
        while column + 1 < len(starts) and position >= starts[column + 1]:
            column += 1
        cells[column] += char
        position += cell_width(char)
    return [cell.strip() for cell in cells]


def header_starts(header: str) -> List[int]:
    """Cell positions where each header word starts."""
    starts: List[int] = []
    position, previous_blank = 0, True
    for char in header:
        blank = char.isspace()
        if not blank and previous_blank:
            starts.append(position)
        previous_blank = blank
        position += cell_width(char)
    return starts


def _blank_at(line: str, position: int) -> bool:
    """True when the character covering cell ``position`` is a space (or the line is shorter)."""
    current = 0
    for char in line:
        width = cell_width(char)
        if current <= position < current + max(width, 1):
            return char.isspace()
        current += width
    return True


def _looks_like_row(line: str, starts: Sequence[int]) -> bool:
    """True when the cell under the Id column holds a package id (not a footer sentence)."""
    if len(starts) < 3:
        return False
    cells = split_cells(line, starts[:3])
    return bool(_ID_TOKEN.match(cells[1].rstrip(ELLIPSIS)))


def _column_starts(header: str, rows: Sequence[str], wanted: Tuple[int, ...]) -> Optional[List[int]]:
    """Column starts that fit ``wanted`` column counts.

    A translated header word with a space in it gives one start too many.
    Starts that most data rows run across (no space just before them) are
    dropped; footer sentences do not count as data rows. None when the
    result still does not fit.
    """
    starts = header_starts(header)
    if len(starts) in wanted:
        return starts
    data = [row for row in rows if _looks_like_row(row, starts)] or list(rows)
    kept = starts[:1]
    for start in starts[1:]:
        crossing = sum(1 for row in data if not _blank_at(row, start - 1))
        if crossing * 2 <= len(data):
            kept.append(start)
    return kept if len(kept) in wanted else None


def _table_spans(lines: Sequence[str]) -> List[Tuple[str, List[str]]]:
    """``(header, body lines)`` for every table in the output.

    ``winget upgrade`` can print a second table (packages that need explicit
    targeting) with its own header and column widths, so each table is cut
    at the header of the next one.
    """
    separators = [index for index, line in enumerate(lines) if _SEPARATOR.match(line)]
    headers: List[int] = []
    for index in separators:
        header = next((row for row in range(index - 1, -1, -1) if lines[row].strip()), -1)
        headers.append(header)
    spans: List[Tuple[str, List[str]]] = []
    for number, index in enumerate(separators):
        if headers[number] < 0:
            continue
        end = headers[number + 1] if number + 1 < len(separators) and headers[number + 1] > index else len(lines)
        body = [line for line in lines[index + 1:end] if line.strip()]
        spans.append((lines[headers[number]], body))
    return spans


def parse_table(text: str, has_source: bool) -> Tuple[List[WingetRow], bool]:
    """Rows of ``winget list`` or ``winget upgrade`` tables, and whether a table was found.

    Columns, in order: name, id, version, an optional available version and
    an optional source. winget hides a column that has no values: Source
    when only one source is in play (always with ``--source``), Available
    when nothing has an update. Pass ``has_source`` False when aiup named
    a source. With True, a four-column table is told apart by its last
    column: available versions hold digits, source names do not.
    """
    rows: List[WingetRow] = []
    found = False
    for header, body in _table_spans(text.split("\n")):
        wanted = (3, 4, 5) if has_source else (3, 4)
        starts = _column_starts(header, body, wanted)
        if starts is None:
            continue
        found = True
        cells_list = [split_cells(line, starts) for line in body]
        with_available = len(starts) >= 4
        with_source = len(starts) == 5
        if has_source and len(starts) == 4:
            last = [cells[3] for cells in cells_list if _table_row(cells, False, False) is not None and cells[3]]
            with_source = bool(last) and not any(any(ch.isdigit() for ch in value) for value in last)
            with_available = not with_source
        for cells in cells_list:
            row = _table_row(cells, with_available, with_source)
            if row is not None:
                rows.append(row)
    return rows, found


def _table_row(cells: List[str], with_available: bool, has_source: bool) -> Optional[WingetRow]:
    """One row from its cells, or None for footers and rows that do not parse."""
    name, ident, version = cells[0], cells[1], cells[2]
    available = cells[3] if with_available else ""
    source = cells[-1] if has_source else ""
    if not ident or not version or " " in ident.rstrip(ELLIPSIS):
        return None
    if has_source and " " in source:
        return None
    truncated = ident.endswith(ELLIPSIS)
    if truncated:
        ident = ident[:-1]
    if not _ID_TOKEN.match(ident):
        return None
    if version.endswith(ELLIPSIS) or available.endswith(ELLIPSIS):
        truncated = True
    return WingetRow(name, ident, clean_version(version), clean_version(available), source, truncated)


def clean_version(value: str) -> str:
    """A version cell as aiup stores it: "" for ranges ("< 2.0"), unknowns and shortened values."""
    value = value.strip()
    if not value or value.endswith(ELLIPSIS) or value[0] in "<>" or " " in value:
        return ""
    return value if any(char.isdigit() for char in value) else ""


def rows_for(rows: Iterable[WingetRow], ident: str) -> List[WingetRow]:
    """Rows for one package id: exact (any case) first, else one unambiguous shortened match."""
    wanted = ident.lower()
    rows = list(rows)
    exact = [row for row in rows if not row.truncated and row.id.lower() == wanted]
    if exact:
        return exact
    shortened = [row for row in rows if row.truncated and wanted.startswith(row.id.lower())]
    ids = {row.id.lower() for row in shortened}
    return shortened if len(ids) == 1 else []


def first_after_separator(text: str) -> str:
    """The first value under a one-column table (``winget show --versions``)."""
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if _SEPARATOR.match(line):
            for value in lines[index + 1:]:
                if value.strip():
                    return value.strip()
            break
    return ""


# ---------------------------------------------------------------------------
# winget provider
# ---------------------------------------------------------------------------

AGREE = ("--accept-source-agreements", "--disable-interactivity")
QUIET = ("--silent", "--accept-package-agreements") + AGREE
MIN_VERSION = (1, 6)                 # --no-upgrade and --disable-interactivity
STEP_TIMEOUT = 3600.0
_VERSION_LINE = re.compile(r"v?(\d+)\.(\d+)(?:\.(\d+))?")
_MEMO = Memo()
_REASON = Memo()                     # kept across forget(): winget does not appear mid-run
# Set when a winget read used up a full time limit. winget then counts as
# unavailable for the rest of the run, so one hung session (Windows Server
# over SSH, for example) costs one timeout instead of one per package.
_STUCK: Dict[str, str] = {}
_STUCK_LOCK = threading.Lock()

# Runtimes and frameworks winget lists beside apps. They are dependencies, so
# the inventory marks them not explicit (a heuristic: winget keeps no such flag).
_DEPENDENCY_PREFIXES = (
    "microsoft.vcredist.", "microsoft.vclibs", "microsoft.ui.xaml", "microsoft.windowsappruntime",
    "microsoft.dotnet.runtime", "microsoft.dotnet.desktopruntime", "microsoft.dotnet.aspnetcore",
    "microsoft.dotnet.hostingbundle", "microsoft.edgewebview2runtime", "microsoft.directx",
    "microsoft.appinstaller",
)
_CLIENT_MODULE = "Microsoft.WinGet.Client"
_CLIENT_SCRIPT = """
Import-Module Microsoft.WinGet.Client
$rows = @(Get-WinGetPackage | ForEach-Object {
  $versions = @($_.AvailableVersions)
  $latest = ''
  if ($_.IsUpdateAvailable -and $versions.Count -gt 0) { $latest = [string]$versions[0] }
  [pscustomobject]@{
    Id = [string]$_.Id
    Name = [string]$_.Name
    Version = [string]$_.InstalledVersion
    Source = [string]$_.Source
    Latest = $latest
  }
})
ConvertTo-Json -InputObject $rows -Depth 3 -Compress
"""


class ClientRow(NamedTuple):
    """One package from ``Get-WinGetPackage`` or ``winget export``."""

    id: str
    version: str
    source: str
    latest: str


def split_target(target: Target) -> Tuple[str, str]:
    """``(source, id)`` for a catalog cell: ``Publisher.Package`` or ``msstore:<id>``."""
    package = target.package.strip()
    if package.lower().startswith("msstore:"):
        return "msstore", package.split(":", 1)[1].strip()
    return "winget", package


def valid_id(source: str, ident: str) -> bool:
    """True for an id aiup will pass to winget (no spaces, switches or wildcards)."""
    if source == "msstore":
        return bool(_STORE_ID.match(ident))
    return bool(_ID_TOKEN.match(ident)) and "." in ident


def package_key(source: str, ident: str) -> str:
    """The key ``outdated`` uses, matching ``Target.package``."""
    return "msstore:" + ident if source == "msstore" else ident


class WingetProvider(Provider):
    """Windows Package Manager. Mixed scope: user installs and machine installs."""

    name = "winget"
    oses = WINDOWS
    scope = "mixed"
    lane = "system"
    exclusive = True
    targeted_update = True

    # ----- availability ----------------------------------------------------

    def available(self, ctx: "Context") -> bool:
        """True when winget can run in this session."""
        return not self.unavailable_reason(ctx)

    def unavailable_reason(self, ctx: "Context") -> str:
        """Why winget cannot be used here, or "" when it can. Read once per run."""
        if not is_windows(ctx):
            return "winget is Windows only"
        with _STUCK_LOCK:
            stuck = _STUCK.get("reason", "")
        if stuck:
            return stuck
        return _REASON.get("reason", 1e9, lambda: self._probe(ctx))

    def _run(self, ctx: "Context", argv: Sequence[str], timeout: float, max_bytes: int = 0) -> ReadOut:
        """One winget read. A read that hits a full time limit marks winget unavailable for the run."""
        with _STUCK_LOCK:
            stuck = _STUCK.get("reason", "")
        if stuck:
            return ReadOut(None, "", "", stuck)
        out = run_w(ctx, argv, timeout, max_bytes) if max_bytes else run_w(ctx, argv, timeout)
        if out.timed_out and timeout >= READ_TIMEOUT:
            with _STUCK_LOCK:
                _STUCK.setdefault("reason", "winget did not answer within {:.0f} seconds in this session, so aiup "
                                            "skips it for the rest of this run".format(timeout))
        return out

    def _probe(self, ctx: "Context") -> str:
        exe = which(ctx, "winget")
        if exe is None:
            return ("winget is not installed for this account. It comes with App Installer "
                    "from the Microsoft Store.")
        out = run_w(ctx, (exe, "--version"), 20.0)
        if out.code is None:
            return ("winget is on PATH but cannot start in this session ({}). It needs App Installer "
                    "registered for a signed-in user; service, SYSTEM and some SSH sessions on "
                    "Windows Server do not have it.".format(out.error))
        found = _VERSION_LINE.search(out.out)
        if out.code != 0 or found is None:
            return "winget --version failed ({})".format(first_line(out.err or out.out) or "exit {}".format(out.code))
        version = (int(found.group(1)), int(found.group(2)))
        if version < MIN_VERSION:
            return "winget {} is older than {}.{}; update App Installer from the Microsoft Store".format(
                found.group(0), *MIN_VERSION)
        return ""

    def exe(self, ctx: "Context") -> str:
        """winget's path (call after ``available``)."""
        return which(ctx, "winget") or "winget"

    # ----- single-package reads --------------------------------------------

    def _list_rows(self, ctx: "Context", source: str, ident: str, scope: str = "") -> Optional[List[WingetRow]]:
        """Installed rows for one id, [] when winget has none, None when the read failed."""
        argv = [self.exe(ctx), "list", "--id", ident, "--exact", "--source", source]
        if scope:
            argv += ["--scope", scope]
        out = self._run(ctx, argv + list(AGREE), READ_TIMEOUT)
        if out.code is None:
            return None
        if out.code == NO_APPLICATIONS_FOUND:
            return []
        rows, found = parse_table(out.out, has_source=False)
        if out.code != 0 or not found:
            return None
        return rows_for(rows, ident)

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """The installed copy winget knows for this id (live read, never cached)."""
        source, ident = split_target(target)
        if not valid_id(source, ident) or not self.available(ctx):
            return None
        rows = self._list_rows(ctx, source, ident)
        if not rows:
            return None
        version = newest(row.version for row in rows)
        return Installed(version=version, path=portable_folder(ident), scope=self.install_scope(ctx, source, ident),
                         channel=self.name)

    def install_scope(self, ctx: "Context", source: str, ident: str) -> str:
        """"user" when a user-scope copy is installed, else "machine". Remembered for the run."""
        def produce() -> str:
            rows = self._list_rows(ctx, source, ident, scope="user")
            return "user" if rows else "machine"
        return _MEMO.get("scope:" + package_key(source, ident).lower(), MEMO_TTL, produce)

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """The newest version in the package's source (``winget show --versions``)."""
        source, ident = split_target(target)
        if source == "msstore":
            return Latest("", "msstore", STORE_NOTE, managed=STORE_NOTE)
        if not valid_id(source, ident):
            return Latest("", self.name, "not a winget package id: " + ident)
        reason = self.unavailable_reason(ctx)
        if reason:
            return Latest("", self.name, reason)
        argv = (self.exe(ctx), "show", "--id", ident, "--exact", "--source", source, "--versions") + AGREE
        out = self._run(ctx, argv, max(timeout, 1.0))
        if out.code is None:
            return Latest("", self.name, "winget " + out.error)
        if out.code in (NO_APPLICATIONS_FOUND, NO_MANIFEST_FOUND):
            return Latest("", self.name, "winget has no package with this id")
        if out.code != 0:
            return Latest("", self.name, "winget show exited 0x{:08X}".format(out.code))
        version = clean_version(first_after_separator(out.out))
        if not version:
            return Latest("", self.name, "winget printed no readable version")
        return Latest(version, self.name)

    def user_scope_offered(self, ctx: "Context", source: str, ident: str) -> bool:
        """True when the package has an installer for ``--scope user``.

        ``winget show`` exits 0 even when no installer fits the scope; it then
        prints a warning instead of the installer section. Every winget
        source manifest carries the installer's SHA-256, and the section is
        the only place it appears, so a 64-digit hex value means an installer
        was selected. No header words are read, so translations do not matter.
        """
        if source != "winget":
            return False
        argv = (self.exe(ctx), "show", "--id", ident, "--exact", "--source", source, "--scope", "user") + AGREE
        out = self._run(ctx, argv, READ_TIMEOUT)
        return out.code == 0 and _SHA256.search(out.out) is not None

    # ----- bulk reads ------------------------------------------------------

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Every package with an update, keyed like ``Target.package``. One read per run."""
        if not self.available(ctx):
            return {}
        return _MEMO.get("outdated", MEMO_TTL, lambda: self._read_outdated(ctx))

    def _read_outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        client = self._client_rows(ctx)
        if client is not None:
            # Store copies stay "managed" (latest() answers that), never a version here.
            return {row.id: Latest(row.latest, self.name) for row in client if row.latest and row.source == "winget"}
        # Naming the source keeps the table's columns known (winget hides
        # Source when one source is in play). Store copies need no row here:
        # latest() answers "managed" for them without a read.
        argv = (self.exe(ctx), "upgrade", "--source", "winget") + AGREE
        out = self._run(ctx, argv, SLOW_TIMEOUT, BULK_MAX_BYTES)
        if out.code is None:
            return {}
        rows, _found = parse_table(out.out, has_source=False)
        result: Dict[str, Latest] = {}
        for row in rows:
            if row.truncated or not row.available:
                continue  # a shortened id never matches a catalog id; latest() reads those one by one
            result[row.id] = Latest(row.available, self.name)
        return result

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Packages winget matched to a source. Registry-only and MSIX entries belong to other sources."""
        if not self.available(ctx):
            return ()
        return _MEMO.get("inventory", MEMO_TTL, lambda: self._read_inventory(ctx))

    def _read_inventory(self, ctx: "Context") -> Tuple[PackageRecord, ...]:
        rows = self._client_rows(ctx)
        if rows is None:
            rows = self._export_rows(ctx)
        if rows is None:
            rows = self._table_rows(ctx)
        best: Dict[str, ClientRow] = {}
        for row in rows:
            key = package_key(row.source, row.id).lower()
            held = best.get(key)
            if held is None or (row.version and version_cmp(row.version, held.version) > 0):
                best[key] = row
        user_ids = self._user_scope_ids(ctx)
        return tuple(
            PackageRecord(manager=self.name, name=package_key(row.source, row.id), version=row.version,
                          scope="user" if row.id.lower() in user_ids else "machine",
                          explicit=not row.id.lower().startswith(_DEPENDENCY_PREFIXES),
                          paths=tuple(p for p in (portable_folder(row.id),) if p))
            for row in sorted(best.values(), key=lambda item: item.id.lower())
        )

    def _user_scope_ids(self, ctx: "Context") -> FrozenSet[str]:
        """Lower-case ids winget lists under ``--scope user`` (one table read)."""
        argv = (self.exe(ctx), "list", "--scope", "user", "--source", "winget") + AGREE
        out = self._run(ctx, argv, SLOW_TIMEOUT, BULK_MAX_BYTES)
        if out.code != 0:
            return frozenset()
        rows, _found = parse_table(out.out, has_source=False)
        return frozenset(row.id.lower() for row in rows if not row.truncated)

    def _client_rows(self, ctx: "Context") -> Optional[List[ClientRow]]:
        """Rows from the Microsoft.WinGet.Client module, or None when it is not installed or fails."""
        if not client_module_installed():
            return None
        return _MEMO.get("client", MEMO_TTL, lambda: self._read_client(ctx))

    def _read_client(self, ctx: "Context") -> Optional[List[ClientRow]]:
        exe = any_powershell(ctx)
        if exe is None:
            return None
        value, _reason = powershell_json(ctx, exe, _CLIENT_SCRIPT, SLOW_TIMEOUT)
        if not isinstance(value, list):
            return None
        rows: List[ClientRow] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            ident, source = str(item.get("Id") or ""), str(item.get("Source") or "").lower()
            if source and _ID_TOKEN.match(ident):
                rows.append(ClientRow(ident, clean_version(str(item.get("Version") or "")), source,
                                      clean_version(str(item.get("Latest") or ""))))
        return rows

    def _export_rows(self, ctx: "Context") -> Optional[List[ClientRow]]:
        """Rows from ``winget export --include-versions``: a JSON file aiup reads, then deletes."""
        try:
            path = scratch_file(ctx, "winget-export", ".json")
        except OSError:
            return None
        try:
            argv = (self.exe(ctx), "export", "-o", str(path), "--include-versions") + AGREE
            out = self._run(ctx, argv, SLOW_TIMEOUT, BULK_MAX_BYTES)
            if out.code is None:
                return None
            # winget may exit non-zero when some packages have no source; the
            # file still lists the rest, and export_rows refuses a bad one.
            return export_rows(read_json_file(path))
        finally:
            try:
                path.unlink()
            except OSError:
                pass

    def _table_rows(self, ctx: "Context") -> List[ClientRow]:
        """Last resort: the ``winget list --source winget`` table."""
        out = self._run(ctx, (self.exe(ctx), "list", "--source", "winget") + AGREE, SLOW_TIMEOUT, BULK_MAX_BYTES)
        if out.code is None:
            return []
        rows, _found = parse_table(out.out, has_source=False)
        return [ClientRow(row.id, row.version, "winget", row.available) for row in rows if not row.truncated]

    # ----- actions ---------------------------------------------------------

    def install(self, ctx: "Context", target: Target) -> Action:
        """``winget install`` that never touches an existing copy, in user scope when offered."""
        source, ident = split_target(target)
        if not valid_id(source, ident):
            return Action(target.package, "install", self.name, (), "not a winget package id")
        user = self.user_scope_offered(ctx, source, ident)
        argv = [self.exe(ctx), "install", "--id", ident, "--exact", "--source", source, "--no-upgrade"]
        argv += list(QUIET) + (["--scope", "user"] if user else [])
        note = "" if user or source == "msstore" else "installs for all users; Windows may ask for approval"
        step = Step(argv=tuple(argv), label="winget install " + ident,
                    privilege="none" if user or source == "msstore" else "uac-possible",
                    timeout=STEP_TIMEOUT, ok_codes=INSTALL_OK)
        return Action(target.package, "install", self.name, (step,), note)

    def update(self, ctx: "Context", target: Target) -> Action:
        """``winget upgrade`` for one id, in the scope of the installed copy. Never ``--force``."""
        source, ident = split_target(target)
        if source == "msstore":
            return Action(target.package, "update", self.name, (), STORE_NOTE, result="skipped")
        if not valid_id(source, ident):
            return Action(target.package, "update", self.name, (), "not a winget package id")
        user = self.install_scope(ctx, source, ident) == "user"
        argv = [self.exe(ctx), "upgrade", "--id", ident, "--exact", "--source", source]
        argv += list(QUIET) + (["--scope", "user"] if user else [])
        step = Step(argv=tuple(argv), label="winget upgrade " + ident,
                    privilege="none" if user else "uac-possible", timeout=STEP_TIMEOUT, ok_codes=UPDATE_OK)
        return Action(target.package, "update", self.name, (step,))

    def remove(self, ctx: "Context", target: Target) -> Action:
        """``winget uninstall`` for one id, in the scope of the installed copy."""
        source, ident = split_target(target)
        if not valid_id(source, ident):
            return Action(target.package, "remove", self.name, (), "not a winget package id")
        user = source == "msstore" or self.install_scope(ctx, source, ident) == "user"
        argv = [self.exe(ctx), "uninstall", "--id", ident, "--exact", "--source", source, "--silent"]
        argv += list(AGREE) + (["--scope", "user"] if user and source == "winget" else [])
        step = Step(argv=tuple(argv), label="winget uninstall " + ident,
                    privilege="none" if user else "uac-possible", timeout=STEP_TIMEOUT, ok_codes=REMOVE_OK)
        return Action(target.package, "remove", self.name, (step,))

    def system_upgrade(self, ctx: "Context") -> Optional[Action]:
        """``winget upgrade --all`` for ``aiup system``. UAC prompts are Windows' own."""
        if not self.available(ctx):
            return None
        argv = (self.exe(ctx), "upgrade", "--all") + QUIET
        step = Step(argv=argv, label="winget upgrade --all", privilege="uac-possible",
                    ok_codes=code_forms(0, UPDATE_NOT_APPLICABLE, *_REBOOT_OK))
        return Action("system", "update", self.name, (step,))

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """winget portable packages: ``WinGet\\Packages\\<Id>_<SourceId>_<suffix>`` (and Links pointing there)."""
        parts = path_parts(path)
        for root in winget_package_roots():
            rest = under(parts, root)
            if rest:
                ident = portable_id(rest[0])
                if ident:
                    return Ownership(self.name, ident, "exact")
        return None

    # ----- engine hooks beyond the base interface --------------------------

    def explain_exit(self, op: str, code: Optional[int]) -> Optional[Tuple[str, str]]:
        """``(result, note)`` for a winget exit status; see ``explain_winget_exit``."""
        return explain_winget_exit(code)

    def forget(self) -> None:
        """Drop cached reads after a mutation (availability is kept)."""
        _MEMO.clear()


def export_rows(document: Optional[object]) -> Optional[List[ClientRow]]:
    """Packages from a ``winget export`` document (schema winget-packages 2.0)."""
    if not isinstance(document, dict):
        return None
    sources = document.get("Sources")
    if not isinstance(sources, list):
        return None
    rows: List[ClientRow] = []
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        details = entry.get("SourceDetails")
        source = str(details.get("Name") or "").lower() if isinstance(details, dict) else ""
        packages = entry.get("Packages")
        if not source or not isinstance(packages, list):
            continue
        for package in packages:
            if not isinstance(package, dict):
                continue
            ident = str(package.get("PackageIdentifier") or "")
            if _ID_TOKEN.match(ident):
                rows.append(ClientRow(ident, clean_version(str(package.get("Version") or "")), source, ""))
    return rows


def client_module_installed() -> bool:
    """True when ``Microsoft.WinGet.Client`` is in a PowerShell module folder (no PowerShell started)."""
    folders: List[Path] = [Path(entry) for entry in os.environ.get("PSModulePath", "").split(os.pathsep) if entry]
    documents = home_dir() / "Documents"
    folders += [documents / "PowerShell" / "Modules", documents / "WindowsPowerShell" / "Modules"]
    for base in ("ProgramFiles", "ProgramW6432"):
        root = env_dir(base)
        if root is not None:
            folders += [root / "PowerShell" / "Modules", root / "WindowsPowerShell" / "Modules"]
    for folder in folders:
        try:
            if (folder / _CLIENT_MODULE).is_dir():
                return True
        except OSError:
            continue
    return False


def winget_package_roots() -> Tuple[Path, ...]:
    """Where winget unpacks portable and zip packages, user scope first."""
    roots = [env_dir("LOCALAPPDATA", "Microsoft\\WinGet\\Packages")]
    for base in ("ProgramFiles", "ProgramFiles(x86)"):
        roots.append(env_dir(base, "WinGet\\Packages"))
    return tuple(root for root in roots if root is not None)


def portable_id(folder: str) -> str:
    """The package id from a portable folder name such as ``junegunn.fzf_Microsoft.Winget.Source_8wekyb3d8bbwe``."""
    pieces = folder.rsplit("_", 2)
    if len(pieces) != 3 or not pieces[0]:
        return ""
    return pieces[0] if _ID_TOKEN.match(pieces[0]) else ""


def portable_folder(ident: str) -> Optional[str]:
    """The user-scope portable folder for ``ident`` when one exists."""
    root = env_dir("LOCALAPPDATA", "Microsoft\\WinGet\\Packages")
    if root is None:
        return None
    prefix = ident.lower() + "_"
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                if entry.name.lower().startswith(prefix) and portable_id(entry.name).lower() == ident.lower():
                    return entry.path
    except OSError:
        return None
    return None
