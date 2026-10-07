# Copyright (c) Advanced Micro Devices, Inc.
# SPDX-License-Identifier:  MIT

"""Turn a memory chart layout into a diagram model and metric slots."""

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Mapping, Optional, Set, Tuple, TypedDict

from ..loader import Layout, LayoutArrow, LayoutBlock, LayoutContentItem
from ..mem_chart import _find_scope_split

_BAR_CATEGORIES = frozenset({"hit", "util", "stall"})


class ArrowLane(LayoutArrow):
    slotId: str
    groupHeader: Optional[str]


ArrowGroup = TypedDict(
    "ArrowGroup",
    {"from": str, "to": str, "lanes": List[ArrowLane]},
)


@dataclass(frozen=True)
class SlotSpec:
    """Describe one metric value displayed in the diagram."""

    slot_id: str
    metric: str
    unit: str
    category: str
    on_arrow: bool
    cu_block: bool
    bar: bool


def diagram_payload(layout: Layout) -> Dict[str, object]:
    """Build the ordered diagram model after checking block relationships."""
    blocks = layout["blocks"]
    arrows = layout["arrows"]
    blocks_by_id = {block["id"]: block for block in blocks}
    child_ids = _collect_child_ids(blocks, arrows, blocks_by_id)

    grid_blocks: List[Dict[str, object]] = []
    io_blocks: List[Dict[str, object]] = []
    for block in blocks:
        if block["id"] in child_ids:
            continue
        payload = _block_payload(block, blocks_by_id)
        if block.get("position", "grid") == "grid":
            grid_blocks.append(payload)
        else:
            io_blocks.append(payload)

    grid_blocks.sort(key=lambda block: (block["column"], block["order"]))
    anchor_column = _find_scope_split(blocks)
    for block in io_blocks:
        block["anchorColumn"] = anchor_column
    return {
        "arch": layout["arch"],
        "gridBlocks": grid_blocks,
        "ioBlocks": io_blocks,
        "arrows": _arrow_groups(arrows),
    }


def slot_specs(layout: Layout) -> Tuple[SlotSpec, ...]:
    """Describe content slots in block order, followed by arrow slots."""
    specs: List[SlotSpec] = []
    for block in layout["blocks"]:
        for index, item in enumerate(block["content"]):
            category = item["category"]
            unit = item.get("unit", "")
            specs.append(
                SlotSpec(
                    slot_id=f"{block['id']}.{index}",
                    metric=item["metric"],
                    unit=unit,
                    category=category,
                    on_arrow=False,
                    cu_block=block["column"] == 0,
                    bar=_content_has_bar(item),
                )
            )

    for index, arrow in enumerate(layout["arrows"]):
        metric = arrow["metric"]
        metric_lower = metric.lower()
        unit = "Bytes/s" if "bw" in metric_lower or "bandwidth" in metric_lower else ""
        specs.append(
            SlotSpec(
                slot_id=f"arrow.{index}",
                metric=metric,
                unit=unit,
                category=arrow["category"],
                on_arrow=True,
                cu_block=False,
                bar=False,
            )
        )
    return tuple(specs)


def diagram_metrics(layout: Layout) -> FrozenSet[str]:
    """Return every metric referenced by content and arrows."""
    metrics = {
        item["metric"] for block in layout["blocks"] for item in block["content"]
    }
    metrics.update(arrow["metric"] for arrow in layout["arrows"])
    return frozenset(metrics)


def _collect_child_ids(
    blocks: List[LayoutBlock],
    arrows: List[LayoutArrow],
    blocks_by_id: Mapping[str, LayoutBlock],
) -> Set[str]:
    """Check relationships and return child IDs before building nested blocks."""
    child_ids: Set[str] = set()
    parent_by_child: Dict[str, str] = {}
    for block in blocks:
        for child_id in block.get("children", []):
            if child_id not in blocks_by_id:
                raise ValueError(f"Unknown child block {child_id!r}")
            if child_id in child_ids:
                raise ValueError(f"Child block {child_id!r} has several parents")
            if blocks_by_id[child_id]["column"] != block["column"]:
                raise ValueError(f"Child block {child_id!r} is in another column")
            child_ids.add(child_id)
            parent_by_child[child_id] = block["id"]

    for arrow in arrows:
        for endpoint in (arrow["from"], arrow["to"]):
            if endpoint not in blocks_by_id:
                raise ValueError(f"Unknown arrow endpoint {endpoint!r}")

    _validate_acyclic_children(parent_by_child)
    return child_ids


def _validate_acyclic_children(parent_by_child: Mapping[str, str]) -> None:
    """Reject recursive children before building their nested payloads."""
    for child_id in parent_by_child:
        ancestors: Set[str] = set()
        current = child_id
        while current in parent_by_child:
            if current in ancestors:
                raise ValueError(f"Child block {current!r} forms a cycle")
            ancestors.add(current)
            current = parent_by_child[current]


def _block_payload(
    block: LayoutBlock, blocks_by_id: Mapping[str, LayoutBlock]
) -> Dict[str, object]:
    """Copy display fields and nest children in their declared order."""
    payload = dict(block)
    payload["order"] = block.get("order", 0)
    payload["position"] = block.get("position", "grid")
    payload["content"] = [
        {
            **item,
            "slotId": f"{block['id']}.{index}",
            "bar": _content_has_bar(item),
        }
        for index, item in enumerate(block["content"])
    ]
    payload["children"] = [
        _block_payload(blocks_by_id[child_id], blocks_by_id)
        for child_id in block.get("children", [])
    ]
    return payload


def _content_has_bar(item: LayoutContentItem) -> bool:
    """Show a bar only for an explicitly marked percentage metric."""
    return item.get("unit", "") == "%" and item["category"] in _BAR_CATEGORIES


def _arrow_groups(arrows: List[LayoutArrow]) -> List[ArrowGroup]:
    """Collect lanes by endpoint pair without changing either file order."""
    groups: Dict[Tuple[str, str], ArrowGroup] = {}
    for index, arrow in enumerate(arrows):
        pair = (arrow["from"], arrow["to"])
        if pair not in groups:
            groups[pair] = {"from": pair[0], "to": pair[1], "lanes": []}
        lanes = groups[pair]["lanes"]
        previous_group = lanes[-1].get("group") if lanes else None
        lane: ArrowLane = {
            **arrow,
            "slotId": f"arrow.{index}",
            "groupHeader": (
                arrow.get("group") if arrow.get("group") != previous_group else None
            ),
        }
        lanes.append(lane)
    return list(groups.values())
