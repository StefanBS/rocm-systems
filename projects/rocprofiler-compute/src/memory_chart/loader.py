# Copyright (c) Advanced Micro Devices, Inc.
# SPDX-License-Identifier:  MIT

"""Load memory chart layout JSON files by architecture name."""

import json
from pathlib import Path
from typing import Dict, List, TypedDict


class _RequiredContentItemFields(TypedDict):
    metric: str
    category: str
    title: str


class LayoutContentItem(_RequiredContentItemFields, total=False):
    unit: str


class _RequiredLayoutBlockFields(TypedDict):
    id: str
    title: str
    column: int
    content: List[LayoutContentItem]


class LayoutBlock(_RequiredLayoutBlockFields, total=False):
    order: int
    position: str
    children: List[str]


_RequiredLayoutArrowFields = TypedDict(
    "_RequiredLayoutArrowFields",
    {
        "metric": str,
        "title": str,
        "category": str,
        "direction": str,
        "from": str,
        "to": str,
    },
)


class LayoutArrow(_RequiredLayoutArrowFields, total=False):
    group: str


class Layout(TypedDict):
    arch: str
    blocks: List[LayoutBlock]
    arrows: List[LayoutArrow]


_LAYOUTS_DIR = Path(__file__).resolve().parent / "layouts"

_ARCH_TO_FILE: Dict[str, str] = {
    "gfx1150": "gfx115x.json",
    "gfx1151": "gfx115x.json",
    "gfx115x": "gfx115x.json",
    "gfx1250": "gfx1250.json",
    "gfx908": "gfx90x.json",
    "gfx90a": "gfx90x.json",
    "gfx940": "gfx94x.json",
    "gfx941": "gfx94x.json",
    "gfx942": "gfx94x.json",
    "gfx950": "gfx950.json",
}


def load_layout(arch: str) -> Layout:
    """Load the memory chart layout JSON for the given arch."""
    filename = _ARCH_TO_FILE.get(arch)
    if filename is None:
        raise ValueError(f"Unknown architecture {arch!r}. Known: {list(_ARCH_TO_FILE)}")
    path = _LAYOUTS_DIR / filename
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def has_layout(arch: str) -> bool:
    """Return whether load_layout succeeds for this architecture."""
    try:
        load_layout(arch)
    except Exception:
        return False
    return True


def list_architectures() -> List[str]:
    """Return all supported architecture names."""
    return list(_ARCH_TO_FILE)


def list_layout_files() -> List[Path]:
    """Return paths to all layout JSON files (excluding manifest)."""
    return sorted(p for p in _LAYOUTS_DIR.glob("*.json") if p.name != "manifest.json")
