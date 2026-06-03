"""Tests for :func:`testo_core.engine.orchestrator.run_plan`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from testo_core.config.schema import Plan, Stage
from testo_core.engine.events import PlanFinished, PlanStarted, StageFinished, StageStarted
from testo_core.engine.exit_codes import EngineExitCode
from testo_core.engine.orchestrator import run_plan
from testo_core.engine.result import StageResult
from tests.fixtures.engine.conftest import NoopRenderer, fake_stage_result


def _two_stage_plan(tmp_path: Path) -> Plan:
    s1 = Stage(name="a", framework="pytest", target_repo=tmp_path, args=("-q",))
    s2 = Stage(name="b", framework="pytest", target_repo=tmp_path, args=("-q",))
    return Plan(name="p", description=None, stages=(s1, s2), trigger=None, tags=frozenset())


def test_run_plan_happy_path_two_stages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, noop_renderer: NoopRenderer
) -> None:
    plan = _two_stage_plan(tmp_path)
    art = tmp_path / "artifacts"

    def fake_run_stage(stage, **_kwargs: object) -> StageResult:
        return fake_stage_result(stage, returncode=0, tmp_path=art / plan.name / stage.name)

    monkeypatch.setattr("testo_core.engine.orchestrator.run_stage", fake_run_stage)
    result = run_plan(plan, renderer=noop_renderer, artifacts_root=art, persist=False)

    assert len(result.stages) == 2
    assert result.exit_code == EngineExitCode.SUCCESS
    events_path = art / plan.name / "events.ndjson"
    lines = [json.loads(ln) for ln in events_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    event_types = [e["event"] for e in lines]
    assert event_types[0] == "plan_started"
    assert event_types.count("stage_finished") == 2
    assert event_types[-1] == "plan_finished"

    started = [e for e in noop_renderer.events if isinstance(e, PlanStarted)]
    finished = [e for e in noop_renderer.events if isinstance(e, PlanFinished)]
    stage_started = [e for e in noop_renderer.events if isinstance(e, StageStarted)]
    stage_finished = [e for e in noop_renderer.events if isinstance(e, StageFinished)]
    assert len(started) == 1
    assert len(finished) == 1
    assert len(stage_started) == 2
    assert len(stage_finished) == 2


def test_run_plan_fail_fast_stops_after_first_failing_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan = _two_stage_plan(tmp_path)
    art = tmp_path / "artifacts"

    def fake_run_stage(stage, **_kwargs: object) -> StageResult:
        rc = 1 if stage.name == "a" else 0
        return fake_stage_result(stage, returncode=rc, tmp_path=art / plan.name / stage.name)

    monkeypatch.setattr("testo_core.engine.orchestrator.run_stage", fake_run_stage)
    renderer = NoopRenderer()
    result = run_plan(
        plan, renderer=renderer, artifacts_root=art, persist=False, fail_fast=True
    )

    assert len(result.stages) == 1
    assert result.stages[0].stage_name == "a"
    lines = (art / plan.name / "events.ndjson").read_text(encoding="utf-8")
    assert "plan_aborted" in lines


def test_run_plan_internal_exception_maps_to_domain_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, noop_renderer: NoopRenderer
) -> None:
    plan = _two_stage_plan(tmp_path)
    art = tmp_path / "artifacts"

    def boom(*_args: object, **_kwargs: object) -> StageResult:
        raise RuntimeError("unexpected")

    monkeypatch.setattr("testo_core.engine.orchestrator.run_stage", boom)
    result = run_plan(plan, renderer=noop_renderer, artifacts_root=art, persist=False)

    assert len(result.stages) == 2
    assert all(s.returncode == 4 for s in result.stages)
    assert all(s.internal_failure for s in result.stages)
    assert result.stages[0].error is not None
    assert "internal error" in result.stages[0].error
    assert result.exit_code == EngineExitCode.INTERNAL_ERROR


def test_run_plan_persists_plan_result_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, noop_renderer: NoopRenderer
) -> None:
    plan = _two_stage_plan(tmp_path)
    art = tmp_path / "artifacts"

    def fake_run_stage(stage, **_kwargs: object) -> StageResult:
        return fake_stage_result(stage, returncode=0, tmp_path=art / plan.name / stage.name)

    monkeypatch.setattr("testo_core.engine.orchestrator.run_stage", fake_run_stage)
    run_plan(plan, renderer=noop_renderer, artifacts_root=art, persist=True)

    summary_path = art / plan.name / "plan_result.json"
    assert summary_path.is_file()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["plan"] == plan.name
    assert payload["exit_code"] == 0
    assert len(payload["stages"]) == 2
