"""CLI exit-code tests for ``testo run`` / :func:`execute_plan_command`."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.cli.runner import _maybe_archive_cycle_report, execute_plan_command
from testo_core.engine.exit_codes import EngineExitCode
from testo_core.engine.result import PlanResult
from testo_core.triggers import TriggerResult
from tests.fixtures.engine.conftest import write_minimal_config, write_two_cycle_config


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_run_missing_cycle_flag_exits_2(runner: CliRunner) -> None:
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 2


def test_run_missing_config_exits_2(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", "--cycle", "smoke"])
    assert result.exit_code == 2


def test_execute_plan_command_missing_config_returns_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    console = Console(file=io.StringIO(), force_terminal=False)
    code = execute_plan_command(
        console=console,
        plan_name="smoke",
        config_path=None,
        stream=False,
        ci=False,
        persist=False,
        workers_override=None,
    )
    assert code == int(EngineExitCode.INVALID_INPUT)


def test_run_unknown_cycle_exits_2(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg, cycle_name="smoke")
    result = runner.invoke(app, ["run", "--config", str(cfg), "--cycle", "missing"])
    assert result.exit_code == 2
    assert "not found" in (result.stdout + result.stderr).lower()


def test_run_no_enabled_stages_exits_2(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(
        cfg,
        cycle_name="gated",
        stages_yaml="""
      - name: "s1"
        equipment: pytest
        if: '${env:TESTO_RUN_GATED} == "yes"'
        args: ["--version"]
""",
    )
    monkeypatch.delenv("TESTO_RUN_GATED", raising=False)
    result = runner.invoke(app, ["run", "--config", str(cfg), "--cycle", "gated"])
    assert result.exit_code == 2
    assert "no stages enabled" in (result.stdout + result.stderr).lower()


def test_run_trigger_resting_exits_0(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        with patch("testo_core.engine.orchestrator.run_plan") as mock_run:
            result = runner.invoke(
                app,
                ["run", "--config", str(cfg), "--cycle", "triggered", "--no-persist", "--no-report-db"],
            )
    assert result.exit_code == 0
    mock_run.assert_not_called()


def test_run_dry_run_does_not_invoke_run_plan(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    with patch("testo_core.engine.orchestrator.run_plan") as mock_run:
        result = runner.invoke(
            app,
            ["run", "--config", str(cfg), "--cycle", "smoke", "--dry-run", "--no-persist"],
        )
    assert result.exit_code == 0
    mock_run.assert_not_called()


def test_run_engine_domain_failure_exits_1(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    fake = PlanResult(
        plan_name="smoke",
        started_at=0.0,
        finished_at=1.0,
        duration_s=1.0,
        stages=(),
        aggregate_returncode=1,
        exit_code=EngineExitCode.DOMAIN_FAILURE,
    )
    with patch("testo_core.engine.orchestrator.run_plan", return_value=fake):
        result = runner.invoke(
            app,
            ["run", "--config", str(cfg), "--cycle", "smoke", "--no-persist", "--no-report-db"],
        )
    assert result.exit_code == 1


def test_run_engine_infra_failure_exits_3(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    fake = PlanResult(
        plan_name="smoke",
        started_at=0.0,
        finished_at=1.0,
        duration_s=1.0,
        stages=(),
        aggregate_returncode=127,
        exit_code=EngineExitCode.INFRA_FAILURE,
    )
    with patch("testo_core.engine.orchestrator.run_plan", return_value=fake):
        result = runner.invoke(
            app,
            ["run", "--config", str(cfg), "--cycle", "smoke", "--no-persist", "--no-report-db"],
        )
    assert result.exit_code == 3


def test_run_cycle_all_fail_fast_stops_after_first_failure(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_two_cycle_config(cfg)
    calls: list[str] = []

    def fake_run_plan(plan, **_kwargs: object) -> PlanResult:
        calls.append(plan.name)
        ec = EngineExitCode.DOMAIN_FAILURE if plan.name == "alpha" else EngineExitCode.SUCCESS
        rc = 1 if plan.name == "alpha" else 0
        return PlanResult(
            plan_name=plan.name,
            started_at=0.0,
            finished_at=1.0,
            duration_s=1.0,
            stages=(),
            aggregate_returncode=rc,
            exit_code=ec,
        )

    with patch("testo_core.engine.orchestrator.run_plan", side_effect=fake_run_plan):
        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                str(cfg),
                "--cycle",
                "all",
                "--fail-fast",
                "--no-persist",
                "--no-report-db",
            ],
        )
    assert result.exit_code == 1
    assert calls == ["alpha"]


def test_maybe_archive_ci_forces_sync_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg_path = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg_path)
    from testo_core.config.loader import discover_and_load
    from testo_core.config.resolver import resolve_plan

    cfg = discover_and_load(config_path=cfg_path)
    plan = resolve_plan(cfg, plan_name="smoke")
    console = Console(file=io.StringIO(), force_terminal=False)
    archive_id = uuid.uuid4()

    with patch("threading.Thread") as mock_thread:
        with patch(
            "testo_core.services.report_archive.try_persist_cycle_report",
            return_value=archive_id,
        ) as mock_persist:
            ec = _maybe_archive_cycle_report(
                cfg=cfg,
                plan=plan,
                console=console,
                ci=True,
                persist=True,
                report_db=True,
                async_report_db=True,
                plan_exit_code=0,
            )

    mock_thread.assert_not_called()
    mock_persist.assert_called_once()
    assert ec == 0


def test_run_sync_archive_failure_exits_3(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    fake = PlanResult(
        plan_name="smoke",
        started_at=0.0,
        finished_at=1.0,
        duration_s=1.0,
        stages=(),
        aggregate_returncode=0,
        exit_code=EngineExitCode.SUCCESS,
    )
    with patch("testo_core.engine.orchestrator.run_plan", return_value=fake):
        with patch(
            "testo_core.services.report_archive.try_persist_cycle_report",
            return_value=None,
        ):
            result = runner.invoke(
                app,
                ["run", "--config", str(cfg), "--cycle", "smoke"],
            )
    assert result.exit_code == int(EngineExitCode.INFRA_FAILURE)


def test_run_engine_internal_error_exits_4(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    fake = PlanResult(
        plan_name="smoke",
        started_at=0.0,
        finished_at=1.0,
        duration_s=1.0,
        stages=(),
        aggregate_returncode=4,
        exit_code=EngineExitCode.INTERNAL_ERROR,
    )
    with patch("testo_core.engine.orchestrator.run_plan", return_value=fake):
        result = runner.invoke(
            app,
            ["run", "--config", str(cfg), "--cycle", "smoke", "--no-persist", "--no-report-db"],
        )
    assert result.exit_code == int(EngineExitCode.INTERNAL_ERROR)


def test_run_stage_timeout_exits_3(
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
                "--no-persist",
                "--no-report-db",
            ],
        )
    assert result.exit_code == int(EngineExitCode.INFRA_FAILURE)


def test_run_tag_mismatch_on_single_cycle_exits_2(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg, cycle_extra="    tags: [smoke]")
    result = runner.invoke(
        app,
        ["run", "--config", str(cfg), "--cycle", "smoke", "--tag", "nightly"],
    )
    assert result.exit_code == 2
    assert "does not include tag" in (result.stdout + result.stderr).lower()


def test_run_cycle_all_tag_no_match_exits_2(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.fixtures.engine.conftest import write_tagged_cycles_config

    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_tagged_cycles_config(cfg)
    result = runner.invoke(
        app,
        ["run", "--config", str(cfg), "--cycle", "all", "--tag", "nonexistent"],
    )
    assert result.exit_code == 2
    assert "no cycles match" in (result.stdout + result.stderr).lower()
