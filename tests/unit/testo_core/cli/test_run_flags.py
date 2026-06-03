"""CLI flag tests for ``testo run`` (workers, stream, reporters)."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.cli.ui.renderers import StreamRenderer
from testo_core.engine.exit_codes import EngineExitCode
from testo_core.engine.result import PlanResult
from testo_core.triggers import TriggerResult
from tests.fixtures.engine.conftest import write_minimal_config, write_tagged_cycles_config


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _success_plan(name: str = "smoke") -> PlanResult:
    return PlanResult(
        plan_name=name,
        started_at=0.0,
        finished_at=1.0,
        duration_s=1.0,
        stages=(),
        aggregate_returncode=0,
        exit_code=EngineExitCode.SUCCESS,
    )


def test_run_workers_override_passed_to_run_plan(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    captured: dict = {}

    def fake_run_plan(plan, **_kwargs: object) -> PlanResult:
        captured["plan"] = plan
        return _success_plan(plan.name)

    with patch("testo_core.engine.orchestrator.run_plan", side_effect=fake_run_plan):
        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                str(cfg),
                "--cycle",
                "smoke",
                "--workers",
                "4",
                "--no-persist",
                "--no-report-db",
            ],
        )
    assert result.exit_code == 0
    plan = captured["plan"]
    assert all(s.workers == 4 for s in plan.stages)


def test_run_stream_uses_stream_renderer(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    captured: dict = {}

    def fake_run_plan(plan, *, renderer, **_kwargs: object) -> PlanResult:
        captured["renderer"] = renderer
        return _success_plan(plan.name)

    with patch("testo_core.engine.orchestrator.run_plan", side_effect=fake_run_plan):
        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                str(cfg),
                "--cycle",
                "smoke",
                "--stream",
                "--no-persist",
                "--no-report-db",
            ],
        )
    assert result.exit_code == 0
    assert isinstance(captured["renderer"], StreamRenderer)
    assert captured["renderer"].wants_streaming is True


def test_run_reporter_invoked_after_plan(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    with patch("testo_core.engine.orchestrator.run_plan", return_value=_success_plan()):
        with patch(
            "testo_core.reporting.reporters.orchestrate.run_configured_reporters"
        ) as mock_reporters:
            with patch(
                "testo_core.services.report_archive.try_persist_cycle_report",
                return_value=uuid.uuid4(),
            ):
                result = runner.invoke(
                    app,
                    [
                        "run",
                        "--config",
                        str(cfg),
                        "--cycle",
                        "smoke",
                        "--reporter",
                        "allure",
                    ],
                )
    assert result.exit_code == 0
    mock_reporters.assert_called_once()
    call_kw = mock_reporters.call_args.kwargs
    assert call_kw.get("reporter_override") == ("allure",)


def test_run_cycle_all_tag_smoke_runs_only_tagged(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_tagged_cycles_config(cfg)
    calls: list[str] = []

    def fake_run_plan(plan, **_kwargs: object) -> PlanResult:
        calls.append(plan.name)
        return _success_plan(plan.name)

    with patch("testo_core.engine.orchestrator.run_plan", side_effect=fake_run_plan):
        with patch("testo_core.cli.runner.evaluate_cycle_trigger") as mock_trig:
            mock_trig.return_value = TriggerResult(
                stimulus=True,
                reason="forced",
                matched_paths=(),
                mode="snapshot",
                persist_snapshot_after_run=False,
            )
            result = runner.invoke(
                app,
                [
                    "run",
                    "--config",
                    str(cfg),
                    "--cycle",
                    "all",
                    "--tag",
                    "smoke",
                    "--force",
                    "--no-persist",
                    "--no-report-db",
                ],
            )
    assert result.exit_code == 0
    assert calls == ["smoke-cycle"]


def test_trigger_snapshot_persisted_after_successful_run(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    tr = TriggerResult(
        stimulus=True,
        reason="changed",
        matched_paths=("foo.py",),
        mode="snapshot",
        persist_snapshot_after_run=True,
    )
    with patch("testo_core.cli.runner.evaluate_cycle_trigger", return_value=tr):
        with patch("testo_core.engine.orchestrator.run_plan", return_value=_success_plan("triggered")):
            with patch("testo_core.cli.runner.persist_trigger_snapshot") as mock_snap:
                with patch(
                    "testo_core.services.report_archive.try_persist_cycle_report",
                    return_value=uuid.uuid4(),
                ):
                    result = runner.invoke(
                        app,
                        ["run", "--config", str(cfg), "--cycle", "triggered"],
                    )
    assert result.exit_code == 0
    mock_snap.assert_called_once()
