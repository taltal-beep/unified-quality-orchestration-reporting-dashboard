"""Tests for ``engine.runners`` helpers."""

from __future__ import annotations

from pathlib import Path

from engine.command_builders import RunConfig, TestType, build_command
from engine.runners import validate_target_repo


def test_validate_target_repo_rejects_missing(tmp_path: Path) -> None:
    ok, msg = validate_target_repo(tmp_path / "missing")
    assert ok is False


def test_validate_target_repo_accepts_dir(tmp_path: Path) -> None:
    ok, msg = validate_target_repo(tmp_path)
    assert ok is True and msg == "OK"


def test_build_command_sets_allure_env(tmp_path: Path) -> None:
    cfg = RunConfig(
        test_type=TestType.PYTEST,
        target_repo=tmp_path,
        shared_allure_results_dir=tmp_path / "allure-results",
        pytest_args=("-q",),
    )
    bc = build_command(cfg, parent_env={})
    assert "pytest" in bc.argv[0] or bc.argv[0].endswith("pytest")
    assert "--alluredir" in bc.argv
    assert "UQO_SHARED_ALLURE_RESULTS_DIR" in bc.env
