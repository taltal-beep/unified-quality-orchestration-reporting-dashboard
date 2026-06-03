"""Lifecycle and state-preservation tests for :func:`run_plan`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from testo_core.config.schema import Plan, Stage
from testo_core.engine.exit_codes import EngineExitCode
from testo_core.engine.orchestrator import run_plan
from tests.fixtures.engine.conftest import (
    NoopRenderer,
    assert_ndjson_events,
    fake_stage_result,
)


def _two_stage_plan(tmp_path: Path) -> Plan:
    s1 = Stage(name="a", framework="pytest", target_repo=tmp_path, args=("-q",))
    s2 = Stage(name="b", framework="pytest", target_repo=tmp_path, args=("-q",))
    return Plan(name="p", description=None, stages=(s1, s2), trigger=None, tags=frozenset())


def test_run_plan_passes_same_parent_env_to_all_stages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan = _two_stage_plan(tmp_path)
    art = tmp_path / "artifacts"
    parent_env_ids: list[int] = []

    def fake_run_stage(stage, *, parent_env, **_kwargs: object):
        parent_env_ids.append(id(parent_env))
        return fake_stage_result(stage, returncode=0, tmp_path=art / plan.name / stage.name)

    monkeypatch.setattr("testo_core.engine.orchestrator.run_stage", fake_run_stage)
    parent = {"TESTO_PARENT_MARKER": "stable", "PATH": "/usr/bin"}
    run_plan(
        plan,
        renderer=NoopRenderer(),
        artifacts_root=art,
        parent_env=parent,
        persist=False,
    )

    assert len(parent_env_ids) == 2
    assert parent_env_ids[0] == parent_env_ids[1]


def test_run_plan_aggregate_returncode_is_max_stage_rc(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan = _two_stage_plan(tmp_path)
    art = tmp_path / "artifacts"

    def fake_run_stage(stage, **_kwargs: object):
        rc = 0 if stage.name == "a" else 2
        return fake_stage_result(stage, returncode=rc, tmp_path=art / plan.name / stage.name)

    monkeypatch.setattr("testo_core.engine.orchestrator.run_stage", fake_run_stage)
    result = run_plan(plan, renderer=NoopRenderer(), artifacts_root=art, persist=False)

    assert result.aggregate_returncode == 2
    assert result.exit_code == EngineExitCode.DOMAIN_FAILURE
    events_path = art / plan.name / "events.ndjson"
    events = assert_ndjson_events(
        events_path,
        ["plan_started", "stage_started", "stage_finished", "stage_started", "stage_finished", "plan_finished"],
    )
    finished = events[-1]
    assert finished["aggregate_returncode"] == 2
    assert finished["exit_code"] == int(EngineExitCode.DOMAIN_FAILURE)


def test_stage_finished_ndjson_includes_timeout_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan = Plan(
        name="timeout-plan",
        description=None,
        stages=(Stage(name="slow", framework="pytest", target_repo=tmp_path, args=()),),
        trigger=None,
        tags=frozenset(),
    )
    art = tmp_path / "artifacts"

    def fake_run_stage(stage, **_kwargs: object):
        return fake_stage_result(
            stage,
            returncode=124,
            timed_out=True,
            error="stage exceeded timeout_s=1",
            tmp_path=art / plan.name / stage.name,
        )

    monkeypatch.setattr("testo_core.engine.orchestrator.run_stage", fake_run_stage)
    result = run_plan(plan, renderer=NoopRenderer(), artifacts_root=art, persist=False)

    assert result.exit_code == EngineExitCode.INFRA_FAILURE
    events = json.loads((art / plan.name / "events.ndjson").read_text(encoding="utf-8").splitlines()[2])
    assert events["event"] == "stage_finished"
    assert events["timed_out"] is True
    assert events["returncode"] == 124
    assert events["error"] == "stage exceeded timeout_s=1"
    assert events["log_path"] is not None
