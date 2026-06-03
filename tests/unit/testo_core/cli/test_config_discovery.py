"""Config discovery and resolution tests for the modern testosterone schema."""

from __future__ import annotations

from pathlib import Path

import pytest

from testo_core.config.errors import ConfigDiscoveryError, PlanNotFoundError
from testo_core.config.loader import discover_and_load, load_config
from testo_core.config.resolver import resolve_plan, resolve_stages_for_plan
from tests.fixtures.engine.conftest import write_minimal_config


def test_discover_and_load_prefers_explicit_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg_a = tmp_path / "a.yaml"
    cfg_b = tmp_path / "b.yaml"
    write_minimal_config(cfg_a, cycle_name="from-a")
    write_minimal_config(cfg_b, cycle_name="from-b")
    loaded = discover_and_load(config_path=cfg_b)
    assert "from-b" in loaded.cycles


def test_discover_and_load_falls_back_to_testosterone_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg, cycle_name="discovered")
    loaded = discover_and_load(config_path=None)
    assert "discovered" in loaded.cycles


def test_discover_and_load_raises_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigDiscoveryError):
        discover_and_load(config_path=None)


def test_resolve_plan_unknown_cycle_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg, cycle_name="only")
    loaded = load_config(cfg)
    with pytest.raises(PlanNotFoundError):
        resolve_plan(loaded, plan_name="missing")


def test_resolve_stages_filters_if_expr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(
        cfg,
        cycle_name="gated",
        stages_yaml="""
      - name: "on"
        equipment: pytest
        if: '${env:TESTO_STAGE_ON} == "yes"'
        args: ["--version"]
      - name: "off"
        equipment: pytest
        if: '${env:TESTO_STAGE_ON} == "no"'
        args: ["--version"]
""",
    )
    loaded = load_config(cfg)
    plan = loaded.cycles["gated"]
    monkeypatch.setenv("TESTO_STAGE_ON", "yes")
    stages = resolve_stages_for_plan(plan)
    assert [s.name for s in stages] == ["on"]


def test_resolve_stages_empty_when_all_gated_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(
        cfg,
        cycle_name="empty",
        stages_yaml="""
      - name: "s1"
        equipment: pytest
        if: '${env:TESTO_NEVER} == "yes"'
        args: ["--version"]
""",
    )
    loaded = load_config(cfg)
    monkeypatch.delenv("TESTO_NEVER", raising=False)
    stages = resolve_stages_for_plan(loaded.cycles["empty"])
    assert stages == ()
