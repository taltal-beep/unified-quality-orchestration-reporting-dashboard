"""CI NDJSON contract tests for ``testo run --ci``."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.engine.orchestrator import run_plan
from tests.fixtures.engine.conftest import NoopRenderer, parse_ndjson, write_minimal_config


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_ci_invalid_config_emits_error_ndjson(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", "--cycle", "smoke", "--ci"])
    assert result.exit_code == 2
    events = parse_ndjson(result.stdout)
    assert len(events) >= 1
    err = events[0]
    assert err["event"] == "error"
    assert err["code"] == "invalid_input"
    assert "message" in err


def test_ci_dry_run_emits_dry_run_stage(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    result = runner.invoke(
        app,
        ["run", "--config", str(cfg), "--cycle", "smoke", "--dry-run", "--ci", "--no-persist"],
    )
    assert result.exit_code == 0
    events = parse_ndjson(result.stdout)
    dry = [e for e in events if e.get("event") == "dry_run_stage"]
    assert len(dry) == 1
    stage = dry[0]
    assert stage["cycle"] == "smoke"
    assert "argv" in stage
    assert "cwd" in stage
    assert stage["framework"] == "pytest"


def test_ci_run_emits_plan_finished_on_success(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from testo_core.config.schema import Stage

    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    art = tmp_path / "artifacts"

    def fake_run_stage(stage: Stage, **_kwargs: object):
        from tests.fixtures.engine.conftest import fake_stage_result

        return fake_stage_result(stage, returncode=0, tmp_path=art / "smoke" / stage.name)

    with patch("testo_core.engine.orchestrator.run_stage", side_effect=fake_run_stage):
        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                str(cfg),
                "--cycle",
                "smoke",
                "--ci",
                "--no-persist",
                "--no-report-db",
            ],
        )
    assert result.exit_code == 0
    events = parse_ndjson(result.stdout)
    finished = [e for e in events if e.get("event") == "plan_finished"]
    assert len(finished) == 1
    assert finished[0]["exit_code"] == 0
    assert finished[0]["aggregate_returncode"] == 0


def test_ci_cycle_trigger_emits_ndjson(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from testo_core.triggers import TriggerResult

    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(
        cfg,
        cycle_name="triggered",
        cycle_extra="""
    trigger:
      paths:
        - "**/*.py"
""",
    )
    resting = TriggerResult(
        stimulus=False,
        reason="no changes",
        matched_paths=(),
        mode="snapshot",
        persist_snapshot_after_run=False,
    )
    with patch("testo_core.cli.runner.evaluate_cycle_trigger", return_value=resting):
        result = runner.invoke(
            app,
            ["run", "--config", str(cfg), "--cycle", "triggered", "--ci", "--no-persist"],
        )
    assert result.exit_code == 0
    events = parse_ndjson(result.stdout)
    trig = [e for e in events if e.get("event") == "cycle_trigger"]
    assert len(trig) == 1
    assert trig[0]["status"] == "resting"
    assert trig[0]["mode"] == "snapshot"
    assert "reason" in trig[0]


def test_ci_fail_fast_emits_plan_aborted(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from testo_core.config.schema import Stage

    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(
        cfg,
        stages_yaml="""
      - name: fail
        equipment: pytest
        args: ["--version"]
      - name: skip
        equipment: pytest
        args: ["--version"]
""",
    )
    art = tmp_path / "artifacts"

    def fake_run_stage(stage: Stage, **_kwargs: object):
        from tests.fixtures.engine.conftest import fake_stage_result

        rc = 1 if stage.name == "fail" else 0
        return fake_stage_result(stage, returncode=rc, tmp_path=art / "smoke" / stage.name)

    with patch("testo_core.engine.orchestrator.run_stage", side_effect=fake_run_stage):
        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                str(cfg),
                "--cycle",
                "smoke",
                "--ci",
                "--fail-fast",
                "--no-persist",
                "--no-report-db",
            ],
        )
    assert result.exit_code == 1
    events_path = tmp_path / "artifacts" / "smoke" / "events.ndjson"
    assert events_path.is_file()
    lines = [json.loads(ln) for ln in events_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    aborted = [e for e in lines if e.get("event") == "plan_aborted"]
    assert len(aborted) == 1
    assert aborted[0]["reason"] == "fail_fast"
    assert aborted[0]["completed_stages"] == 1


def test_ci_stage_finished_includes_timed_out_and_error(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from testo_core.config.schema import Stage

    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    art = tmp_path / "artifacts"

    def fake_run_stage(stage: Stage, **_kwargs: object):
        from tests.fixtures.engine.conftest import fake_stage_result

        return fake_stage_result(
            stage,
            returncode=124,
            timed_out=True,
            error="stage exceeded timeout_s=30",
            tmp_path=art / "smoke" / stage.name,
        )

    with patch("testo_core.engine.orchestrator.run_stage", side_effect=fake_run_stage):
        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                str(cfg),
                "--cycle",
                "smoke",
                "--ci",
                "--no-persist",
                "--no-report-db",
            ],
        )
    assert result.exit_code == 3
    events = parse_ndjson(result.stdout)
    finished = [e for e in events if e.get("event") == "stage_finished"]
    assert len(finished) == 1
    assert finished[0]["timed_out"] is True
    assert finished[0]["returncode"] == 124
    assert finished[0]["log_path"]

    artifact_events_path = tmp_path / "artifacts" / "smoke" / "events.ndjson"
    artifact_lines = [
        json.loads(ln)
        for ln in artifact_events_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    artifact_finished = [e for e in artifact_lines if e.get("event") == "stage_finished"]
    assert artifact_finished[0]["error"] is not None
    assert "timeout" in artifact_finished[0]["error"].lower()


def test_ci_plan_started_emits_stage_count(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from testo_core.config.schema import Stage

    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    art = tmp_path / "artifacts"

    def fake_run_stage(stage: Stage, **_kwargs: object):
        from tests.fixtures.engine.conftest import fake_stage_result

        return fake_stage_result(stage, returncode=0, tmp_path=art / "smoke" / stage.name)

    with patch("testo_core.engine.orchestrator.run_stage", side_effect=fake_run_stage):
        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                str(cfg),
                "--cycle",
                "smoke",
                "--ci",
                "--no-persist",
                "--no-report-db",
            ],
        )
    assert result.exit_code == 0
    events = parse_ndjson(result.stdout)
    started = [e for e in events if e.get("event") == "plan_started"]
    assert len(started) == 1
    assert started[0]["plan"] == "smoke"
    assert started[0]["stage_count"] == 1


def test_events_ndjson_mirror_written_by_run_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, noop_renderer: NoopRenderer
) -> None:
    from testo_core.config.schema import Plan, Stage

    stage = Stage(name="s", framework="pytest", target_repo=tmp_path, args=())
    plan = Plan(name="mirror", description=None, stages=(stage,), trigger=None, tags=frozenset())
    art = tmp_path / "artifacts"

    def fake_run_stage(st, **_kwargs: object):
        from tests.fixtures.engine.conftest import fake_stage_result

        return fake_stage_result(st, returncode=0, tmp_path=art / plan.name / st.name)

    monkeypatch.setattr("testo_core.engine.orchestrator.run_stage", fake_run_stage)
    run_plan(plan, renderer=noop_renderer, artifacts_root=art, persist=False)

    events_path = art / plan.name / "events.ndjson"
    lines = events_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 3
    for line in lines:
        payload = json.loads(line)
        assert "event" in payload
