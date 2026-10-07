# Copyright (c) Advanced Micro Devices, Inc.
# SPDX-License-Identifier:  MIT

"""Loader capability checks used by the future HTML report."""

import pytest

from memory_chart import loader


def fail_loading(arch: str) -> dict:
    """Simulate a missing or unreadable architecture layout."""
    raise OSError(f"Cannot load {arch}")


@pytest.mark.parametrize("arch", loader.list_architectures())
def test_has_layout_accepts_every_loader_architecture(arch: str) -> None:
    """Accept every architecture with a shipped layout."""
    assert loader.has_layout(arch)


def test_has_layout_rejects_unsupported_architectures() -> None:
    """Reject architectures without a supported layout."""
    assert not loader.has_layout("gfx1030")


def test_has_layout_returns_false_if_loading_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return false when loading an architecture layout raises an error."""
    monkeypatch.setattr(loader, "load_layout", fail_loading)
    assert not loader.has_layout("gfx908")
