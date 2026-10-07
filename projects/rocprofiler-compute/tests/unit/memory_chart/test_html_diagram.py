# Copyright (c) Advanced Micro Devices, Inc.
# SPDX-License-Identifier:  MIT

"""Unit tests for the HTML memory chart diagram model."""

import pytest

from memory_chart.html.diagram import diagram_metrics, diagram_payload, slot_specs
from memory_chart.loader import list_architectures, load_layout
from tests.unit.memory_chart.conftest import panel_yaml_metric_keys


def synthetic_layout() -> dict:
    """Make a small valid layout for relationship checks."""
    return {
        "arch": "synthetic",
        "blocks": [
            {
                "id": "parent",
                "title": "Parent",
                "column": 0,
                "children": ["child"],
                "content": [],
            },
            {"id": "child", "title": "Child", "column": 0, "content": []},
            {"id": "other", "title": "Other", "column": 0, "content": []},
        ],
        "arrows": [
            {
                "from": "parent",
                "to": "child",
                "direction": "forward",
                "metric": "Requests",
                "title": "Requests",
                "category": "read",
            }
        ],
    }


def test_all_shipped_layouts_have_ordered_complete_payload(layout_data: dict) -> None:
    """Every shipped JSON layout can become a model without losing a slot."""
    payload = diagram_payload(layout_data)
    assert set(payload) == {"arch", "gridBlocks", "ioBlocks", "arrows"}
    assert payload["arch"] == layout_data["arch"]

    top_level = list(payload["gridBlocks"]) + list(payload["ioBlocks"])
    nested = {
        child for block in layout_data["blocks"] for child in block.get("children", [])
    }
    assert {block["id"] for block in top_level} == {
        block["id"] for block in layout_data["blocks"]
    } - nested
    assert payload["gridBlocks"] == sorted(
        payload["gridBlocks"], key=lambda block: (block["column"], block["order"])
    )
    assert all(block["position"] == "grid" for block in payload["gridBlocks"])
    assert all(block["position"] in {"above", "below"} for block in payload["ioBlocks"])
    cu = next(block for block in payload["gridBlocks"] if block["id"] == "cu")
    assert all(not item["bar"] for item in cu["content"])

    expected_pairs = list(
        dict.fromkeys((arrow["from"], arrow["to"]) for arrow in layout_data["arrows"])
    )
    assert [(group["from"], group["to"]) for group in payload["arrows"]] == (
        expected_pairs
    )
    for group in payload["arrows"]:
        expected_lanes = [
            (index, arrow)
            for index, arrow in enumerate(layout_data["arrows"])
            if (arrow["from"], arrow["to"]) == (group["from"], group["to"])
        ]
        assert [lane["slotId"] for lane in group["lanes"]] == [
            f"arrow.{index}" for index, _ in expected_lanes
        ]
        assert [lane["metric"] for lane in group["lanes"]] == [
            arrow["metric"] for _, arrow in expected_lanes
        ]


def test_gfx950_io_blocks_keep_above_and_below() -> None:
    """Preserve the declared positions of gfx950 I/O blocks."""
    payload = diagram_payload(load_layout("gfx950"))
    assert [(block["id"], block["position"]) for block in payload["ioBlocks"]] == [
        ("xgmi", "above"),
        ("pcie", "below"),
    ]
    assert all(block["anchorColumn"] == 3 for block in payload["ioBlocks"])
    assert all(block["column"] == 7 for block in payload["ioBlocks"])


@pytest.mark.parametrize("arch", ["gfx908", "gfx942"])
def test_io_without_arrows_anchors_to_fabric(arch: str) -> None:
    """Position IO at the terminal fabric split even without an arrow endpoint."""
    payload = diagram_payload(load_layout(arch))
    assert payload["ioBlocks"][0]["anchorColumn"] == 3
    assert not any(group["to"] == "xgmi" for group in payload["arrows"])


def test_gfx1250_children_are_nested_in_declared_order() -> None:
    """Nest gfx1250 child blocks in their declared order."""
    payload = diagram_payload(load_layout("gfx1250"))
    by_id = {block["id"]: block for block in payload["gridBlocks"]}
    assert [child["id"] for child in by_id["tcp"]["children"]] == ["lds", "gl0"]
    assert [child["id"] for child in by_id["sqc"]["children"]] == ["icache", "dcache"]
    assert "lds" not in by_id
    assert "icache" not in by_id
    assert by_id["tcp"]["children"][0]["content"][0]["slotId"] == "lds.0"
    assert by_id["tcp"]["children"][0]["content"][0]["bar"]


def test_gfx1250_blocks_without_order_default_to_zero() -> None:
    """Assign order zero to gfx1250 blocks that omit an order."""
    layout = load_layout("gfx1250")
    missing_order_ids = {
        block["id"] for block in layout["blocks"] if "order" not in block
    }
    payload = diagram_payload(layout)
    child_blocks = [
        child for block in payload["gridBlocks"] for child in block["children"]
    ]

    assert missing_order_ids
    assert {block["id"] for block in child_blocks} >= missing_order_ids
    assert all(
        block["order"] == 0
        for block in child_blocks
        if block["id"] in missing_order_ids
    )


def test_gfx9_lane_group_headers_follow_changes() -> None:
    """Keep lane group headers aligned with each gfx9 group change."""
    payload = diagram_payload(load_layout("gfx908"))
    group = next(
        group
        for group in payload["arrows"]
        if (group["from"], group["to"]) == ("cu", "vl1d")
    )
    assert [lane["groupHeader"] for lane in group["lanes"]] == [
        "Non-buffer Request",
        None,
        None,
        "Buffer Request",
        None,
        None,
    ]
    assert [lane["slotId"] for lane in group["lanes"]] == [
        f"arrow.{index}" for index in range(6)
    ]


def test_grid_order_defaults_and_ties_keep_file_order() -> None:
    """Default missing grid orders to zero and preserve ties by file order."""
    layout = synthetic_layout()
    layout["blocks"] = [
        {"id": "late", "title": "Late", "column": 1, "order": 2, "content": []},
        {"id": "first", "title": "First", "column": 0, "order": 1, "content": []},
        {"id": "tie_a", "title": "Tie A", "column": 1, "content": []},
        {"id": "tie_b", "title": "Tie B", "column": 1, "content": []},
    ]
    layout["arrows"] = []
    payload = diagram_payload(layout)
    assert [block["id"] for block in payload["gridBlocks"]] == [
        "first",
        "tie_a",
        "tie_b",
        "late",
    ]
    assert [block["order"] for block in payload["gridBlocks"]] == [1, 0, 0, 2]


def test_interleaved_arrow_pairs_keep_each_pairs_file_order() -> None:
    """Group interleaved arrows while preserving each pair's file order."""
    layout = synthetic_layout()
    first = layout["arrows"][0]
    first["group"] = "Alpha"
    other = dict(first, to="other", metric="Other")
    second = dict(first, metric="Second", group="Beta")
    layout["arrows"] = [first, other, second]
    groups = diagram_payload(layout)["arrows"]
    assert [(group["from"], group["to"]) for group in groups] == [
        ("parent", "child"),
        ("parent", "other"),
    ]
    assert [lane["slotId"] for lane in groups[0]["lanes"]] == ["arrow.0", "arrow.2"]
    assert [lane["groupHeader"] for lane in groups[0]["lanes"]] == ["Alpha", "Beta"]


def test_unknown_arrow_source_raises_value_error() -> None:
    """Reject an arrow whose source block does not exist."""
    layout = synthetic_layout()
    layout["arrows"][0]["from"] = "missing"
    with pytest.raises(ValueError, match="Unknown arrow endpoint"):
        diagram_payload(layout)


def test_unknown_arrow_destination_raises_value_error() -> None:
    """Reject an arrow whose destination block does not exist."""
    layout = synthetic_layout()
    layout["arrows"][0]["to"] = "missing"
    with pytest.raises(ValueError, match="Unknown arrow endpoint"):
        diagram_payload(layout)


def test_unknown_child_block_raises_value_error() -> None:
    """Reject a child relationship that references a missing block."""
    layout = synthetic_layout()
    layout["blocks"][0]["children"] = ["missing"]
    with pytest.raises(ValueError, match="Unknown child block"):
        diagram_payload(layout)


def test_child_with_multiple_parents_raises_value_error() -> None:
    """Reject a child block assigned to multiple parents."""
    layout = synthetic_layout()
    layout["blocks"][2]["children"] = ["child"]
    with pytest.raises(ValueError, match="several parents"):
        diagram_payload(layout)


def test_child_in_another_column_raises_value_error() -> None:
    """Reject a child block placed in a different column from its parent."""
    layout = synthetic_layout()
    layout["blocks"][1]["column"] = 1
    with pytest.raises(ValueError, match="another column"):
        diagram_payload(layout)


def test_slot_ids_follow_file_order_and_defaults() -> None:
    """Generate unique slot IDs in file order with the expected defaults."""
    layout = load_layout("gfx908")
    specs = slot_specs(layout)
    expected_ids = [
        f"{block['id']}.{index}"
        for block in layout["blocks"]
        for index, _ in enumerate(block["content"])
    ] + [f"arrow.{index}" for index, _ in enumerate(layout["arrows"])]
    assert [spec.slot_id for spec in specs] == expected_ids
    assert len(expected_ids) == len(set(expected_ids))

    by_id = {spec.slot_id: spec for spec in specs}
    assert by_id["cu.0"].unit == ""
    assert not by_id["cu.0"].bar
    assert by_id["cu.0"].cu_block
    assert not by_id["vl1d.0"].cu_block
    assert by_id["vl1d.0"].bar
    assert by_id["arrow.0"].unit == ""
    assert by_id["arrow.0"].on_arrow
    assert not by_id["arrow.0"].bar
    bandwidth = next(spec for spec in specs if spec.metric == "VL1_L2 Read BW")
    assert bandwidth.unit == "Bytes/s"


def test_slot_defaults_and_explicit_units_control_bars() -> None:
    """Choose slot units and bar visibility from defaults and explicit units."""
    layout = synthetic_layout()
    layout["blocks"][0]["content"] = [
        {"metric": "Hit", "title": "Hit", "category": "hit"},
        {"metric": "Cycles", "title": "Cycles", "category": "util", "unit": "cycles"},
        {"metric": "Count", "title": "Count", "category": "info"},
        {"metric": "Hit Rate", "title": "Hit Rate", "category": "hit", "unit": "%"},
        {"metric": "Other", "title": "Other", "category": "info", "unit": "%"},
    ]
    specs = slot_specs(layout)
    assert [(spec.unit, spec.bar, spec.cu_block) for spec in specs[:5]] == [
        ("", False, True),
        ("cycles", False, True),
        ("", False, True),
        ("%", True, True),
        ("%", False, True),
    ]
    payload = diagram_payload(layout)
    assert [item["bar"] for item in payload["gridBlocks"][0]["content"]] == [
        False,
        False,
        False,
        True,
        False,
    ]


@pytest.mark.parametrize("arch", list_architectures())
def test_diagram_metrics_match_panel_300_for_every_loader_arch(arch: str) -> None:
    """Match diagram metrics to panel 300 for every supported architecture."""
    config_arch = "gfx115x" if arch in {"gfx1150", "gfx1151"} else arch
    expected = panel_yaml_metric_keys(config_arch)
    assert expected, f"Missing panel-300 YAML metrics for {arch}"
    assert diagram_metrics(load_layout(arch)) == expected
