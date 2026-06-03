"""Archive exit-code tests for ``testo run`` / :func:`_maybe_archive_cycle_report`."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.cli.runner import _maybe_archive_cycle_report
from testo_core.engine.exit_codes import EngineExitCode
from testo_core.engine.result import PlanResult
from tests.fixtures.engine.conftest import write_minimal_config


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_async_archive_spawns_thread_when_not_ci(
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

    with patch("threading.Thread") as mock_thread_cls:
        def make_thread(*_args, target=None, **_kwargs):  # type: ignore[no-untyped-def]
            mock_thread = MagicMock()

            def start() -> None:
                if target is not None:
                    target()

            mock_thread.start = start
            mock_thread.is_alive.return_value = False
            return mock_thread

        mock_thread_cls.side_effect = make_thread
        with patch(
            "testo_core.services.report_archive.try_persist_cycle_report",
            return_value=archive_id,
        ):
            ec = _maybe_archive_cycle_report(
                cfg=cfg,
                plan=plan,
                console=console,
                ci=False,
                persist=True,
                report_db=True,
                async_report_db=True,
                plan_exit_code=0,
            )

    mock_thread_cls.assert_called_once()
    assert ec == 0


def test_async_archive_join_timeout_exits_3(
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

    with patch("threading.Thread") as mock_thread_cls:
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        mock_thread_cls.return_value = mock_thread
        ec = _maybe_archive_cycle_report(
            cfg=cfg,
            plan=plan,
            console=console,
            ci=False,
            persist=True,
            report_db=True,
            async_report_db=True,
            plan_exit_code=0,
        )

    assert ec == int(EngineExitCode.INFRA_FAILURE)


def test_ci_archive_failure_exits_3(
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
                ["run", "--config", str(cfg), "--cycle", "smoke", "--ci"],
            )
    assert result.exit_code == int(EngineExitCode.INFRA_FAILURE)


def test_archive_failure_bumps_plan_exit_when_plan_failed(
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
        aggregate_returncode=1,
        exit_code=EngineExitCode.DOMAIN_FAILURE,
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


def test_no_report_db_skips_archive(
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
        ) as mock_persist:
            result = runner.invoke(
                app,
                [
                    "run",
                    "--config",
                    str(cfg),
                    "--cycle",
                    "smoke",
                    "--no-report-db",
                ],
            )
    assert result.exit_code == 0
    mock_persist.assert_not_called()
