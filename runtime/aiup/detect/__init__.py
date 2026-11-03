"""System detection for Linux and Windows (design section 8).

Sources (``aiup.detect.sources``) read evidence without prompts, privilege or
network: PATH commands, desktop entries, Start Menu shortcuts, the Uninstall
keys, extras such as AppImages and runtimes, and slow on-demand sources
(local models, container images, MCP configs, editor extensions). Rows are
cached per source and linked in every process. ``inventory()`` adds the
package managers' own inventories and sorts everything into managed,
package and detected items with duplicate findings. ``owner_of()`` and
``actions_for()`` tie an item back to the provider that can update or remove
it.
"""

from __future__ import annotations

from aiup.detect.items import Copy, InventoryItem, Owner
from aiup.detect.merge import Finding, Inventory, detected_item, inventory, package_items
from aiup.detect.owners import action_for, actions_for, adopt_channel, owner_of, target_for
from aiup.detect.sources import DetectionSource, all_sources, forget, load_errors, register, run_batch

__all__ = [
    "Copy",
    "DetectionSource",
    "Finding",
    "Inventory",
    "InventoryItem",
    "Owner",
    "action_for",
    "actions_for",
    "adopt_channel",
    "all_sources",
    "detected_item",
    "forget",
    "inventory",
    "load_errors",
    "owner_of",
    "package_items",
    "register",
    "run_batch",
    "target_for",
]
