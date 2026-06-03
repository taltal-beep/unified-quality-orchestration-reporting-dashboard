"""Integration smoke: real subprocess via echo.py through the engine (no Docker)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from testo_core.config.schema import Plan, Stage
from testo_core.engine.exit_codes import EngineExitCode
from testo_core.engine.orchestrator import run_plan
from testo_core.cli.app import app
from tests.fixtures.engine.conftest import (
    EchoAdapter,
    NoopRenderer,
    SCRIPTS_DIR,
    parse_ndjson,
    write_minimal_config,
)
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_run_plan_two_stages_real_echo_subprocess(tmp_path: Path) -> None:
    echo = SCRIPTS_DIR / "echo.py"
    repo = tmp_path / "repo"
    repo.mkdir()
    s1 = Stage(name="echo-a", framework="pytest", target_repo=repo, args=(), timeout_s=10.0)
    s2 = Stage(name="echo-b", framework="pytest", target_repo=repo, args=(), timeout_s=10.0)
    plan = Plan(name="echo-plan", description=None, stages=(s1, s2), trigger=None, tags=frozenset())
    art = tmp_path / "artifacts"
    adapter = EchoAdapter(echo, exit_code=0)

    with patch("testo_core.engine.executor.get_adapter", return_value=adapter):
        result = run_plan(plan, renderer=NoopRenderer(), artifacts_root=art, persist=True)

    assert result.exit_code == EngineExitCode.SUCCESS
    assert len(result.stages) == 2
    assert all(s.returncode == 0 for s in result.stages)
    for stage in result.stages:
        assert stage.log_path is not None
        assert stage.log_path.is_file()
        assert "hello" in stage.log_path.read_text(encoding="utf-8")


def test_ci_run_with_echo_subprocess_emits_plan_finished(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(
        cfg,
        cycle_name="echo",
        stages_yaml=f"""
      - name: echo-stage
        equipment: pytest
        target_repo: {repo}
        args: []
        timeout_s: 10
""",
    )
    echo = SCRIPTS_DIR / "echo.py"
    adapter = EchoAdapter(echo, exit_code=0)

    with patch("testo_core.engine.executor.get_adapter", return_value=adapter):
        with patch(
            "testo_core.services.report_archive.try_persist_cycle_report",
            return_value=None,
        ):
            result = runner.invoke(
                app,
                [
                    "run",
                    "--config",
                    str(cfg),
                    "--cycle",
                    "echo",
                    "--ci",
                    "--no-report-db",
                ],
            )

    assert result.exit_code == 0
    events = parse_ndjson(result.stdout)
    finished = [e for e in events if e.get("event") == "plan_finished"]
    assert len(finished) == 1
    assert finished[0]["exit_code"] == 0
