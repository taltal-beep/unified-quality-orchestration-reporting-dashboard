"""Tests for ``testo_core.reporting.pyramid_viz``."""

from __future__ import annotations

from testo_core.reporting.pyramid_viz import PyramidModel, classify_shape, render_pyramid_lines


def test_classify_healthy_pyramid() -> None:
    shape, msg = classify_shape(PyramidModel(unit=70, integration=20, e2e=10))
    assert shape.value == "healthy"
    assert "Healthy" in msg


def test_classify_top_heavy() -> None:
    shape, msg = classify_shape(PyramidModel(unit=5, integration=10, e2e=40))
    assert shape.value == "top_heavy"
    assert "TOP-HEAVY" in msg


def test_classify_mid_bulge() -> None:
    shape, msg = classify_shape(PyramidModel(unit=10, integration=50, e2e=8))
    assert shape.value == "mid_bulge"
    assert "INTEGRATION" in msg


def test_classify_empty() -> None:
    shape, _msg = classify_shape(PyramidModel(unit=0, integration=0, e2e=0))
    assert shape.value == "irregular"


def test_render_pyramid_lines_non_empty() -> None:
    lines = render_pyramid_lines(PyramidModel(30, 15, 5), width=31)
    assert len(lines) >= 4
    assert any("/" in ln for ln in lines)
