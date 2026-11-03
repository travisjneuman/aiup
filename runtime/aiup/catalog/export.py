"""``aiup catalog --json`` and ``--markdown`` (design doc sections 2.1 and 5.6).

The JSON keeps the shape of macOS ``print_catalog_definition``: top-level
``name``, ``version``, ``categories``, ``tools`` and ``recommended``. Each tool
gains an additive ``platforms`` object. A missing platform key means the tool
is not available there. The first entry of each Linux or Windows list is the
row's default channel when it names one, then the section 5.4 order.

This is a definition export only: no scan, no state, no network.
"""

from __future__ import annotations

import json
from typing import Dict, List, Tuple, Union

from aiup.catalog.loader import Catalog
from aiup.errors import UsageError
from aiup.model import CatalogEntry, Target

PLATFORM_CHOICES = ("linux", "windows", "all")
FORMAT_CHOICES = ("json", "markdown")
# macOS leaves `detected` out of the export; `updates` is a picker row only.
_EXPORT_SKIP = ("updates", "detected")

JsonValue = Union[str, int, bool, None, List["JsonValue"], Dict[str, "JsonValue"]]
JsonObject = Dict[str, JsonValue]


def default_platform(os_name: str) -> str:
    """The ``--platform`` value when none is given: this OS, or all on macOS."""
    return os_name if os_name in ("linux", "windows") else "all"


def _oses(platform: str) -> Tuple[str, ...]:
    if platform == "all":
        return ("linux", "windows")
    if platform in ("linux", "windows"):
        return (platform,)
    raise UsageError("--platform takes linux, windows or all, not '{}'".format(platform))


def _target_json(target: Target) -> JsonObject:
    out: JsonObject = {"channel": target.channel, "package": target.package}
    if target.flags:
        out["flags"] = list(target.flags)
    if target.install_script and target.install_script != target.package:
        out["install_script"] = target.install_script
    return out


def _platforms_json(entry: CatalogEntry, platform: str) -> JsonObject:
    out: JsonObject = {}
    if platform == "all":
        out["macos"] = {"kind": entry.macos_kind, "target": entry.macos_target}
    for os_name in _oses(platform):
        targets = entry.targets_for(os_name)
        if targets:
            out[os_name] = [_target_json(t) for t in targets]
    return out


def _tool_json(entry: CatalogEntry, platform: str) -> JsonObject:
    return {
        "id": entry.id,
        "category": entry.category,
        "kind": entry.macos_kind,
        "lifecycle": entry.lifecycle,
        "docs": entry.docs,
        "label": entry.label,
        "platforms": _platforms_json(entry, platform),
    }


def build_json(catalog: Catalog, platform: str) -> JsonObject:
    """The export as a JSON-ready dict."""
    _oses(platform)
    tools = [_tool_json(entry, platform) for entry in catalog.entries]
    categories: List[JsonValue] = []
    for cat in catalog.categories:
        if cat.id in _EXPORT_SKIP:
            continue
        members: List[JsonValue] = [t for t in tools if t["category"] == cat.id]
        categories.append({"id": cat.id, "name": cat.name, "emoji": cat.emoji,
                           "blurb": cat.blurb, "tools": members})
    tool_values: List[JsonValue] = list(tools)
    # Recommended extras are Homebrew casks and formulae on macOS; the new
    # runtime has none, so the array stays for shape compatibility.
    return {"name": "aiup", "version": catalog.version, "categories": categories,
            "tools": tool_values, "recommended": []}


def default_channel(entry: CatalogEntry, os_name: str) -> str:
    """The row's default channel, else its first target's channel, else ''."""
    declared = entry.defaults.get(os_name, "")
    if declared:
        return declared
    targets = entry.targets_for(os_name)
    return targets[0].channel if targets else ""


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def build_markdown(catalog: Catalog, platform: str) -> str:
    """The export as a Markdown document, one table per category."""
    oses = _oses(platform)
    titles = {"linux": "Linux", "windows": "Windows"}
    lines = ["# Catalog ({})".format(catalog.version), "",
             "Generated from `runtime/aiup` via `aiup catalog --markdown`.", ""]
    if catalog.notice:
        lines += [catalog.notice, ""]
    for cat in catalog.tool_categories():
        lines += ["## {} {}".format(cat.emoji, cat.id).strip(), "", cat.blurb, ""]
        lines.append("| Id | Label | " + " | ".join(titles[o] for o in oses) + " |")
        lines.append("|---|---|" + "---|" * len(oses))
        for entry in catalog.in_category(cat.id):
            cells = ["`{}`".format(entry.id), _md_cell(entry.label)]
            cells += [default_channel(entry, o) for o in oses]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def render(catalog: Catalog, fmt: str, platform: str) -> str:
    """The export text for ``fmt`` (json or markdown), ending in a newline."""
    if fmt == "json":
        return json.dumps(build_json(catalog, platform), indent=2, ensure_ascii=False) + "\n"
    if fmt == "markdown":
        return build_markdown(catalog, platform) + "\n"
    raise UsageError("catalog format must be json or markdown, not '{}'".format(fmt))
