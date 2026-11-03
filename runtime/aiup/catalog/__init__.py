"""The catalog: loading, cell grammar, data paths and export.

Where the files are:

- ``AIUP_CATALOG_DIR`` set: it names the ``catalog/`` folder, and the manifest
  is read from ``<that folder>/../macos/catalog/manifest.tsv``.
- Otherwise the files are found next to this package, the layout of both a
  checkout and an installed generation: ``<root>/runtime/aiup/catalog`` here,
  ``<root>/catalog/*.tsv`` and ``<root>/macos/catalog/manifest.tsv`` there.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional

from aiup.catalog.loader import (
    MISSING_PLATFORMS_NOTICE, Catalog, CatalogPaths, Category, default_paths, load_catalog,
    paths_from_catalog_dir,
)

__all__ = [
    "MISSING_PLATFORMS_NOTICE", "Catalog", "CatalogPaths", "Category", "catalog_paths",
    "default_paths", "load", "load_catalog", "paths_from_catalog_dir", "release_root",
]


def release_root() -> Path:
    """The checkout or generation root that holds ``runtime/`` and ``catalog/``."""
    return Path(__file__).resolve().parents[3]


def catalog_paths(env: Optional[Mapping[str, str]] = None) -> CatalogPaths:
    """The four catalog file paths for this run."""
    source: Mapping[str, str] = os.environ if env is None else env
    override = source.get("AIUP_CATALOG_DIR", "")
    if override:
        return paths_from_catalog_dir(Path(override).expanduser().absolute())
    return default_paths(release_root())


def load(env: Optional[Mapping[str, str]] = None) -> Catalog:
    """Find and load the catalog. Raises CatalogError."""
    return load_catalog(catalog_paths(env))
