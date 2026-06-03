"""CLI ``--reporter`` flag on ``testo run``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write_cfg(path: Path) -> None:
    path.write_text(
        """
version: 1
defaults:
  target_repo: .
  artifacts_root: artifacts
reporters:
  - type: extent
    output_dir: ./reports/extent
cycles:
  smoke:
    stages:
      - name: s
        equipment: pytest
        args: ["--version"]
""".strip(),
        encoding="utf-8",
    )


def test_run_dry_run_with_reporter_does_not_invoke_orchestrate(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    _write_cfg(cfg)
    with patch("testo_core.reporting.reporters.orchestrate.run_configured_reporters") as mock_run:
        r = runner.invoke(
            app,
            ["run", "--config", str(cfg), "--cycle", "smoke", "--dry-run", "--reporter", "allure"],
        )
    assert r.exit_code == 0, r.stdout + r.stderr
    mock_run.assert_not_called()


def test_run_reporter_override_precedence(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    _write_cfg(cfg)
    captured: dict = {}

    def _capture(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return []

    from testo_core.engine.exit_codes import EngineExitCode
    from testo_core.engine.result import PlanResult

    fake_result = PlanResult(
        plan_name="smoke",
        started_at=0.0,
        finished_at=1.0,
        duration_s=1.0,
        stages=(),
        aggregate_returncode=0,
        exit_code=EngineExitCode.SUCCESS,
    )
    with patch("testo_core.engine.orchestrator.run_plan", return_value=fake_result):
        with patch("testo_core.reporting.reporters.orchestrate.run_configured_reporters", side_effect=_capture):
            with patch("testo_core.services.report_archive.try_persist_cycle_report", return_value=None):
                r = runner.invoke(
                    app,
                    ["run", "--config", str(cfg), "--cycle", "smoke", "--reporter", "testbeats", "--no-persist"],
                )
    assert r.exit_code == 0, r.stdout + r.stderr
    assert captured.get("reporter_override") == ("testbeats",)
