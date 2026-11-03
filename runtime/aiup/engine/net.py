"""Bounded HTTPS reads and downloads (design doc sections 6.2, 6.7, 9.1).

- HTTPS only. A redirect to anything else is refused.
- Every read has a size cap (4 MiB by default, as macOS ``AIUP_LIVE_PY``) and
  a time limit; a download has its own cap and a 300 second limit.
- At most 8 requests at once, and at most 2 to one host.
- No credentials are ever sent. GitHub is asked without a login; after it
  answers 403 or 429 once, GitHub lookups stop for the rest of the process.

Registry helpers (npm, PyPI, crates.io, the Go module proxy) return a cleaned
version string or "" when the answer could not be read.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional

READ_MAX_BYTES = 4 * 1024 * 1024
DOWNLOAD_MAX_BYTES = 64 * 1024 * 1024
DOWNLOAD_TIMEOUT = 300.0
DOWNLOAD_RETRIES = 2
DEFAULT_TIMEOUT = 10.0
MAX_CONNECTIONS = 8
MAX_PER_HOST = 2
USER_AGENT = "aiup"
_CHUNK = 65536

_VERSION = re.compile(r"^[A-Za-z0-9._+-]+$")
_MAIN_COMMIT = re.compile(r"^main@[0-9a-f]{7,40}$")


class NetError(Exception):
    """A download that could not finish (the message says why)."""


@dataclass(frozen=True)
class FetchResult:
    """One HTTPS read. ``status`` is 0 when no HTTP answer came back."""

    url: str
    status: int
    body: bytes
    error: str = ""

    @property
    def ok(self) -> bool:
        """True for a 2xx answer that fit the size cap."""
        return 200 <= self.status < 300 and not self.error

    def text(self) -> str:
        """The body as UTF-8 text, bad bytes replaced."""
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Optional[object]:
        """The body parsed as JSON, or None."""
        if not self.ok:
            return None
        try:
            return json.loads(self.text())
        except ValueError:
            return None


def clean_version(text: object) -> str:
    """A version string from a release source, or "" when it does not look like one.

    Strips a leading ``v`` and surrounding space. Accepts the characters macOS
    ``AIUP_LIVE_PY`` accepts and needs at least one digit; ``main@<hash>``
    is kept as is.
    """
    value = str(text or "").strip()
    if _MAIN_COMMIT.match(value):
        return value
    if value[:1] in ("v", "V") and value[1:2].isdigit():
        value = value[1:]
    if not value or len(value) > 80 or not _VERSION.match(value):
        return ""
    if not any(ch.isdigit() for ch in value):
        return ""
    return value


def is_https(url: str) -> bool:
    """True for an https URL with a host."""
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" and bool(parts.hostname)


class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    """Follows redirects only when they stay on https."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        if not is_https(newurl):
            raise urllib.error.HTTPError(newurl, code, "refused a redirect away from https", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Net:
    """HTTPS access for providers and the engine (``ctx.net``)."""

    def __init__(self, default_timeout: float = DEFAULT_TIMEOUT) -> None:
        self.default_timeout = default_timeout
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
            _HttpsOnlyRedirects(),
        )
        self._all = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self._hosts: Dict[str, threading.BoundedSemaphore] = {}
        self._hosts_lock = threading.Lock()
        self._github_limited = threading.Event()

    # ----- core ----------------------------------------------------------

    def _host_slot(self, host: str) -> threading.BoundedSemaphore:
        with self._hosts_lock:
            slot = self._hosts.get(host)
            if slot is None:
                slot = threading.BoundedSemaphore(MAX_PER_HOST)
                self._hosts[host] = slot
            return slot

    def fetch(self, url: str, *, max_bytes: int = READ_MAX_BYTES, timeout: Optional[float] = None,
              headers: Optional[Mapping[str, str]] = None) -> FetchResult:
        """GET one https URL with a size cap and a time limit. Never raises."""
        if not is_https(url):
            return FetchResult(url, 0, b"", "refused: not an https URL")
        limit = self.default_timeout if timeout is None else max(0.5, float(timeout))
        host = urllib.parse.urlsplit(url).hostname or ""
        request = urllib.request.Request(url, headers=self._headers(headers))
        # The host slot first: threads queued on one busy host hold no global slot.
        with self._host_slot(host), self._all:
            return self._read(request, url, max_bytes, limit)

    def _headers(self, extra: Optional[Mapping[str, str]]) -> Dict[str, str]:
        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
        for key, value in (extra or {}).items():
            if key.lower() in ("authorization", "cookie"):
                continue  # never send credentials
            headers[key] = value
        return headers

    def _read(self, request: urllib.request.Request, url: str, max_bytes: int, limit: float) -> FetchResult:
        deadline = time.monotonic() + limit
        try:
            with self._opener.open(request, timeout=min(limit, 10.0)) as response:
                status = int(getattr(response, "status", 200) or 200)
                body = bytearray()
                while True:
                    if time.monotonic() > deadline:
                        return FetchResult(url, status, b"", "timed out")
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        return FetchResult(url, status, b"", "answer too large")
                return FetchResult(response.geturl() or url, status, bytes(body))
        except urllib.error.HTTPError as exc:
            try:
                exc.close()  # the error carries the open connection
            except (OSError, AttributeError):
                pass
            return FetchResult(url, int(exc.code or 0), b"", "HTTP " + str(exc.code))
        except (urllib.error.URLError, socket.timeout, OSError, ValueError, http.client.HTTPException) as exc:
            return FetchResult(url, 0, b"", _reason(exc))

    def fetch_json(self, url: str, *, timeout: Optional[float] = None,
                   max_bytes: int = READ_MAX_BYTES) -> Optional[object]:
        """GET a URL and parse JSON, or None."""
        return self.fetch(url, timeout=timeout, max_bytes=max_bytes,
                          headers={"Accept": "application/json"}).json()

    # ----- registries ------------------------------------------------------

    def npm_latest(self, package: str, timeout: Optional[float] = None) -> str:
        """The ``latest`` dist-tag of an npm package."""
        url = "https://registry.npmjs.org/" + urllib.parse.quote(package, safe="@/") + "/latest"
        data = self.fetch_json(url, timeout=timeout)
        return clean_version(data.get("version")) if isinstance(data, dict) else ""

    def npm_metadata(self, package: str, version: str, timeout: Optional[float] = None) -> Optional[Dict[str, object]]:
        """One version record of an npm package (for its repository link)."""
        url = ("https://registry.npmjs.org/" + urllib.parse.quote(package, safe="@/") + "/"
               + urllib.parse.quote(version, safe=""))
        data = self.fetch_json(url, timeout=timeout)
        return data if isinstance(data, dict) else None

    def pypi_info(self, package: str, timeout: Optional[float] = None) -> Optional[Dict[str, object]]:
        """The ``info`` block of a PyPI project."""
        url = "https://pypi.org/pypi/" + urllib.parse.quote(package, safe="") + "/json"
        data = self.fetch_json(url, timeout=timeout)
        info = data.get("info") if isinstance(data, dict) else None
        return info if isinstance(info, dict) else None

    def pypi_latest(self, package: str, timeout: Optional[float] = None) -> str:
        """The newest release of a PyPI project."""
        info = self.pypi_info(package, timeout)
        return clean_version(info.get("version")) if info else ""

    def crates_latest(self, crate: str, timeout: Optional[float] = None) -> str:
        """The newest stable version of a crate on crates.io."""
        url = "https://crates.io/api/v1/crates/" + urllib.parse.quote(crate, safe="")
        data = self.fetch_json(url, timeout=timeout)
        record = data.get("crate") if isinstance(data, dict) else None
        if not isinstance(record, dict):
            return ""
        return clean_version(record.get("max_stable_version") or record.get("max_version"))

    def go_latest(self, module: str, timeout: Optional[float] = None) -> str:
        """The newest version of a Go module from proxy.golang.org."""
        escaped = "".join("!" + ch.lower() if ch.isupper() else ch for ch in module)
        url = "https://proxy.golang.org/" + urllib.parse.quote(escaped, safe="/!.-_~") + "/@latest"
        data = self.fetch_json(url, timeout=timeout)
        return clean_version(data.get("Version")) if isinstance(data, dict) else ""

    # ----- GitHub (anonymous) -------------------------------------------------

    @property
    def github_limited(self) -> bool:
        """True after GitHub answered 403 or 429 in this process."""
        return self._github_limited.is_set()

    def github(self, path: str, timeout: Optional[float] = None) -> FetchResult:
        """GET ``https://api.github.com/<path>`` without a login.

        After one 403 or 429 every later call returns status 429 without
        asking, so the anonymous hourly limit is not spent further.
        """
        url = "https://api.github.com/" + path.lstrip("/")
        if self.github_limited:
            return FetchResult(url, 429, b"", "rate limited")
        result = self.fetch(url, timeout=timeout,
                            headers={"Accept": "application/vnd.github+json"})
        if result.status in (403, 429):
            self._github_limited.set()
        return result

    # ----- downloads ---------------------------------------------------------

    def download(self, url: str, dest: Path, *, max_bytes: int = DOWNLOAD_MAX_BYTES,
                 timeout: float = DOWNLOAD_TIMEOUT, retries: int = DOWNLOAD_RETRIES) -> None:
        """Download an https URL into ``dest`` (a new file in a private folder).

        Retries ``retries`` times, stops at ``timeout`` seconds overall, and
        refuses an empty or oversized answer (macOS ``run_vendor_installer``).
        Raises :class:`NetError`.
        """
        if not is_https(url):
            raise NetError("refused: installer URL is not https")
        started = time.monotonic()
        last = "no answer"
        for attempt in range(retries + 1):
            left = timeout - (time.monotonic() - started)
            if left <= 0:
                break
            result = self.fetch(url, max_bytes=max_bytes, timeout=left)
            if result.ok and result.body:
                _write_new(dest, result.body)
                return
            last = result.error or ("empty answer" if result.ok else "HTTP " + str(result.status))
            if 400 <= result.status < 500 and result.status not in (408, 429):
                break
            if attempt < retries:
                time.sleep(min(2.0, max(0.0, left - 1)))
        raise NetError("could not download " + url + ": " + last)


def _write_new(dest: Path, body: bytes) -> None:
    """Create ``dest`` (it must not exist yet) with mode 600 and write ``body``."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(dest), flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(body)


def _reason(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None)
    text = str(reason if reason is not None else exc) or exc.__class__.__name__
    return text[:200]
