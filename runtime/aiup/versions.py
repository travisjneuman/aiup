"""Version parsing and comparison.

A line-for-line port of ``AIUP_VERSION_PY`` and ``version_is_greater`` in
macos/aiup, so both runtimes order versions the same way:

- the first run of dotted numbers is the main version;
- a letter tag right after it is a pre-release or post tag
  (dev < alpha < beta < rc and unknown tags < release < post);
- ``-N`` or ``_N`` with no tag is a revision;
- a ``,build`` suffix (Homebrew cask style) breaks ties when both sides have one;
- text with no number at all falls back to comparing every number in it.

System package managers order their own versions differently, so
``version_cmp`` takes a ``scheme``: "pacman" (libalpm ``vercmp``, also the
AUR), "dpkg" (Debian policy, apt) or "rpm" (``rpmvercmp`` with ``~`` and
``^``, dnf and zypper). All three read ``epoch:version-release``.
``scheme_for(channel)`` picks the scheme for a channel name.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple, Union

Part = Union[int, str]
VersionKey = Tuple[List[int], Optional[List[Part]], List[int], Optional[List[int]]]

_MAIN = re.compile(r"\d+(?:\.\d+)*")
_TAG = re.compile(r"[-._~]?([A-Za-z][0-9A-Za-z._-]*)")
_TAG_PARTS = re.compile(r"\d+|[A-Za-z]+")
_REVISION = re.compile(r"[-_](\d+)")
_DOTTED = re.compile(r"\d+(?:\.\d+)*")
_NUMBERS = re.compile(r"\d+")

_CHANNEL_SCHEMES: Dict[str, str] = {
    "pacman": "pacman", "aur": "pacman", "apt": "dpkg", "dnf": "rpm", "zypper": "rpm",
}

_TAG_RANK = {
    "dev": 0, "a": 1, "alpha": 1, "b": 2, "beta": 2,
    "c": 3, "rc": 3, "pre": 3, "preview": 3, "post": 5, "rev": 5,
}
_RELEASE_RANK = 4
_UNKNOWN_TAG_RANK = 3


def version_key(value: object) -> Optional[VersionKey]:
    """Split a version string into (main, tag, revision, build), or None."""
    text = str(value or "").strip()
    main_text, _, suffix = text.partition(",")
    match = _MAIN.search(main_text)
    if not match:
        return None
    main = [int(part) for part in match.group().split(".")]
    rest = main_text[match.end():].split("+", 1)[0]
    tag = _TAG.match(rest)
    pre: Optional[List[Part]] = None
    if tag:
        pre = [int(p) if p.isdigit() else p.lower() for p in _TAG_PARTS.findall(tag.group(1))]
    revision = None if tag else _REVISION.match(rest)
    tail = [int(revision.group(1))] if revision else []
    build = [int(part) for part in suffix.split(".")] if _DOTTED.fullmatch(suffix) else None
    return main, pre, tail, build


def _tag_rank(pre: Optional[List[Part]]) -> int:
    if pre is None:
        return _RELEASE_RANK
    if pre and isinstance(pre[0], str):
        return _TAG_RANK.get(pre[0], _UNKNOWN_TAG_RANK)
    return _UNKNOWN_TAG_RANK


def _sign(left: object, right: object) -> int:
    return (left > right) - (left < right)  # type: ignore[operator]


def _pad_cmp(left: List[int], right: List[int]) -> int:
    width = max(len(left), len(right))
    left = left + [0] * (width - len(left))
    right = right + [0] * (width - len(right))
    return _sign(left, right)


def _tag_cmp(pa: List[Part], pb: List[Part]) -> int:
    for x, y in zip(pa, pb):
        if x == y:
            continue
        if isinstance(x, int) and isinstance(y, int):
            return _sign(x, y)
        if isinstance(x, int):
            return -1
        if isinstance(y, int):
            return 1
        return _sign(x, y)
    return _sign(len(pa), len(pb))


def scheme_for(channel: str) -> str:
    """The version scheme of a channel: pacman, dpkg, rpm, or generic for every other one."""
    return _CHANNEL_SCHEMES.get(str(channel or ""), "generic")


def version_cmp(a: object, b: object, scheme: str = "generic") -> int:
    """Compare two versions: 1 when a is newer, -1 when older, 0 when equal.

    ``scheme`` is "generic" (the macOS order), "pacman", "dpkg" or "rpm".
    An empty side, or an unknown scheme, uses the generic order.
    """
    left, right = str(a or "").strip(), str(b or "").strip()
    if scheme != "generic" and left and right:
        if scheme == "pacman":
            return _evr_cmp(left, right, _alpm_vercmp)
        if scheme == "rpm":
            return _evr_cmp(left, right, _rpm_vercmp)
        if scheme == "dpkg":
            return _dpkg_cmp(left, right)
    return _generic_cmp(a, b)


def _generic_cmp(a: object, b: object) -> int:
    ka, kb = version_key(a), version_key(b)
    if ka is None or kb is None:
        return _pad_cmp(
            [int(p) for p in _NUMBERS.findall(str(a or ""))],
            [int(p) for p in _NUMBERS.findall(str(b or ""))],
        )
    result = _pad_cmp(ka[0], kb[0])
    if result:
        return result
    pa, pb = ka[1], kb[1]
    ra, rb = _tag_rank(pa), _tag_rank(pb)
    if ra != rb:
        return _sign(ra, rb)
    if pa is not None and pb is not None:
        result = _tag_cmp(pa, pb)
        if result:
            return result
    result = _pad_cmp(ka[2], kb[2])
    if result or ka[3] is None or kb[3] is None:
        return result
    return _pad_cmp(ka[3], kb[3])


def version_is_greater(a: str, b: str, scheme: str = "generic") -> bool:
    """True when ``a`` is newer than ``b`` (macOS ``version_is_greater``).

    A different cask build of the same version (",hash" suffix on both) counts
    as newer, as it does on macOS (generic scheme only).
    """
    result = version_cmp(a, b, scheme)
    if result > 0:
        return True
    return scheme == "generic" and result == 0 and "," in a and "," in b and a != b


# ----- epoch:version-release (pacman, rpm) ----------------------------------------------


def _split_evr(text: str) -> Tuple[str, str, Optional[str]]:
    """(epoch, version, release or None), as libalpm's ``parseEVR`` reads it."""
    index = 0
    while index < len(text) and _is_digit(text[index]):
        index += 1
    if index < len(text) and text[index] == ":":
        epoch, rest = text[:index] or "0", text[index + 1:]
    else:
        epoch, rest = "0", text
    version, dash, release = rest.rpartition("-")
    if not dash:
        return epoch, rest, None
    return epoch, version, release


def _evr_cmp(a: str, b: str, segments: Callable[[str, str], int]) -> int:
    if a == b:
        return 0
    ea, va, ra = _split_evr(a)
    eb, vb, rb = _split_evr(b)
    result = segments(ea, eb)
    if result == 0:
        result = segments(va, vb)
        if result == 0 and ra is not None and rb is not None:
            result = segments(ra, rb)
    return result


def _is_digit(char: str) -> bool:
    return "0" <= char <= "9"


def _is_alpha(char: str) -> bool:
    return ("a" <= char <= "z") or ("A" <= char <= "Z")


def _is_alnum(char: str) -> bool:
    return _is_digit(char) or _is_alpha(char)


def _segment(text: str, start: int, digits: bool) -> int:
    """The end of the digit (or letter) run starting at ``start``."""
    end = start
    test = _is_digit if digits else _is_alpha
    while end < len(text) and test(text[end]):
        end += 1
    return end


def _segment_cmp(one: str, two: str, digits: bool) -> int:
    """Compare one digit or letter segment each. Leading zeros do not count."""
    if digits:
        one, two = one.lstrip("0"), two.lstrip("0")
        if len(one) != len(two):
            return 1 if len(one) > len(two) else -1
    return _sign(one, two)


def _alpm_vercmp(a: str, b: str) -> int:
    """libalpm ``rpmvercmp``: segments, separator length, and "1.0a" before "1.0"."""
    if a == b:
        return 0
    i = j = 0
    while i < len(a) and j < len(b):
        start_i, start_j = i, j
        while i < len(a) and not _is_alnum(a[i]):
            i += 1
        while j < len(b) and not _is_alnum(b[j]):
            j += 1
        if i >= len(a) or j >= len(b):
            break
        if (i - start_i) != (j - start_j):
            return -1 if (i - start_i) < (j - start_j) else 1
        digits = _is_digit(a[i])
        end_i, end_j = _segment(a, i, digits), _segment(b, j, digits)
        if end_j == j:
            return 1 if digits else -1
        result = _segment_cmp(a[i:end_i], b[j:end_j], digits)
        if result:
            return result
        i, j = end_i, end_j
    if i >= len(a) and j >= len(b):
        return 0
    rest_a = a[i] if i < len(a) else ""
    rest_b = b[j] if j < len(b) else ""
    if (not rest_a and not _is_alpha(rest_b)) or _is_alpha(rest_a):
        return -1
    return 1


def _rpm_vercmp(a: str, b: str) -> int:
    """rpm ``rpmvercmp``: segments, ``~`` sorts before anything, ``^`` after the base version."""
    if a == b:
        return 0
    i = j = 0
    while i < len(a) or j < len(b):
        while i < len(a) and not _is_alnum(a[i]) and a[i] not in "~^":
            i += 1
        while j < len(b) and not _is_alnum(b[j]) and b[j] not in "~^":
            j += 1
        ca = a[i] if i < len(a) else ""
        cb = b[j] if j < len(b) else ""
        if ca == "~" or cb == "~":
            if ca != "~":
                return 1
            if cb != "~":
                return -1
            i, j = i + 1, j + 1
            continue
        if ca == "^" or cb == "^":
            if not ca:
                return -1
            if not cb:
                return 1
            if ca != "^":
                return 1
            if cb != "^":
                return -1
            i, j = i + 1, j + 1
            continue
        if not ca or not cb:
            break
        digits = _is_digit(ca)
        end_i, end_j = _segment(a, i, digits), _segment(b, j, digits)
        if end_j == j:
            return 1 if digits else -1
        result = _segment_cmp(a[i:end_i], b[j:end_j], digits)
        if result:
            return result
        i, j = end_i, end_j
    if i >= len(a) and j >= len(b):
        return 0
    return -1 if i >= len(a) else 1


# ----- dpkg (Debian policy 5.6.12) --------------------------------------------------------


def _dpkg_split(text: str) -> Tuple[int, str, str]:
    """(epoch, upstream version, Debian revision)."""
    epoch = 0
    head, colon, rest = text.partition(":")
    if colon and head.isdigit():
        epoch, text = int(head), rest
    upstream, dash, revision = text.rpartition("-")
    if not dash:
        return epoch, text, ""
    return epoch, upstream, revision


def _dpkg_order(char: str) -> int:
    """dpkg's character order: ``~`` first, then the end, letters, then other characters."""
    if not char or _is_digit(char):
        return 0
    if _is_alpha(char):
        return ord(char)
    if char == "~":
        return -1
    return ord(char) + 256


def _dpkg_part(a: str, b: str) -> int:
    """dpkg ``verrevcmp``."""
    i = j = 0
    while i < len(a) or j < len(b):
        while (i < len(a) and not _is_digit(a[i])) or (j < len(b) and not _is_digit(b[j])):
            ac = _dpkg_order(a[i]) if i < len(a) else 0
            bc = _dpkg_order(b[j]) if j < len(b) else 0
            if ac != bc:
                return _sign(ac, bc)
            i, j = i + 1, j + 1
        while i < len(a) and a[i] == "0":
            i += 1
        while j < len(b) and b[j] == "0":
            j += 1
        first_diff = 0
        while i < len(a) and _is_digit(a[i]) and j < len(b) and _is_digit(b[j]):
            if not first_diff:
                first_diff = _sign(a[i], b[j])
            i, j = i + 1, j + 1
        if i < len(a) and _is_digit(a[i]):
            return 1
        if j < len(b) and _is_digit(b[j]):
            return -1
        if first_diff:
            return first_diff
    return 0


def _dpkg_cmp(a: str, b: str) -> int:
    if a == b:
        return 0
    ea, ua, ra = _dpkg_split(a)
    eb, ub, rb = _dpkg_split(b)
    if ea != eb:
        return _sign(ea, eb)
    return _dpkg_part(ua, ub) or _dpkg_part(ra, rb)


def bundle_relation(short: str, build: str, cask: str) -> str:
    """How an app's own version relates to a package version.

    Returns "newer", "same", "older" or "unknown" (macOS ``bundle_relation``).
    """
    cask = str(cask or "").strip()
    bundle = str(short or "").strip() or str(build or "").strip()
    main, _, suffix = cask.partition(",")
    if not bundle or main in ("", "-", "latest") or version_key(bundle) is None or version_key(main) is None:
        return "unknown"
    result = version_cmp(bundle, main)
    build = str(build or "").strip()
    if (not result and suffix and build and build != bundle
            and _DOTTED.fullmatch(suffix) and _DOTTED.fullmatch(build)):
        result = version_cmp(build, suffix)
    if result > 0:
        return "newer"
    if result < 0:
        return "older"
    return "same"
