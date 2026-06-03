"""Tests for :func:`testo_core.engine.executor.run_stage`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from testo_core.config.schema import Stage
from testo_core.engine.executor import run_stage
from tests.fixtures.engine.conftest import SCRIPTS_DIR


def _pytest_version_stage(tmp_path: Path) -> Stage:
    repo = tmp_path / "repo"
    repo.mkdir()
    return Stage(
        name="pytest-check",
        framework="pytest",
        target_repo=repo,
        args=("--version",),
        timeout_s=30.0,
    )


def test_run_stage_success_writes_log_and_zero_exit(tmp_path: Path) -> None:
    stage = _pytest_version_stage(tmp_path)
    artifacts = tmp_path / "artifacts"
    result = run_stage(stage, plan_name="plan", artifacts_root=artifacts)
    assert result.returncode == 0
    assert result.log_path is not None
    assert result.log_path.is_file()
    assert result.log_path.read_text(encoding="utf-8", errors="replace")
    assert "pytest" in result.output_tail.lower() or result.log_path.read_text(encoding="utf-8", errors="replace")


def test_run_stage_injects_uqo_env_vars(tmp_path: Path) -> None:
    stage = _pytest_version_stage(tmp_path)
    artifacts = tmp_path / "artifacts"
    captured: dict = {}

    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["env"] = dict(kwargs.get("env") or {})
        return real_popen(*args, **kwargs)

    with patch("testo_core.engine.executor.subprocess.Popen", side_effect=recording_popen):
        run_stage(
            stage,
            plan_name="plan",
            artifacts_root=artifacts,
            parent_env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")},
        )

    env = captured["env"]
    assert env.get("UQO_LAST_TEST_TYPE") == "pytest"
    assert env.get("UQO_ARTIFACTS_ROOT") == str(artifacts.resolve())
    assert "UQO_SHARED_ALLURE_RESULTS_DIR" in env


def test_run_stage_missing_executable_returns_127(tmp_path: Path) -> None:
    stage = _pytest_version_stage(tmp_path)
    artifacts = tmp_path / "artifacts"

    class FakeAdapter:
        name = "pytest"

        def results_subdir(self) -> str:
            return "pytest"

        def build_argv(self, **_kwargs: object) -> list[str]:
            return ["/nonexistent/testo-missing-binary-xyz"]

    with patch("testo_core.engine.executor.get_adapter", return_value=FakeAdapter()):
        result = run_stage(stage, plan_name="plan", artifacts_root=artifacts)

    assert result.returncode == 127
    assert result.error is not None
    assert "executable not found" in result.error.lower()


def test_run_stage_timeout_sets_timed_out(tmp_path: Path) -> None:
    hang = SCRIPTS_DIR / "hang.py"
    stage = Stage(
        name="hang",
        framework="pytest",
        target_repo=tmp_path,
        args=(),
        timeout_s=0.15,
    )
    artifacts = tmp_path / "artifacts"

    class HangAdapter:
        name = "pytest"

        def results_subdir(self) -> str:
            return "pytest"

        def build_argv(self, **_kwargs: object) -> list[str]:
            return [sys.executable, str(hang), "--seconds", "30"]

    with patch("testo_core.engine.executor.get_adapter", return_value=HangAdapter()):
        result = run_stage(stage, plan_name="plan", artifacts_root=artifacts)

    assert result.timed_out is True
    assert result.returncode == 124
    assert result.error is not None
    assert "timeout_s" in result.error


def test_run_stage_wipes_allure_results_between_runs(tmp_path: Path) -> None:
    stage = _pytest_version_stage(tmp_path)
    artifacts = tmp_path / "artifacts"
    results_dir = artifacts / "plan" / stage.name / "allure-results" / "pytest"
    results_dir.mkdir(parents=True)
    marker = results_dir / "stale-marker.txt"
    marker.write_text("old", encoding="utf-8")

    run_stage(stage, plan_name="plan", artifacts_root=artifacts)
    assert not marker.exists()
    assert results_dir.is_dir()
