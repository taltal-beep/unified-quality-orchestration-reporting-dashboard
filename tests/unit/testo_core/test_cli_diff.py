"""CLI regression tests for archived report diff commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.db import get_report_archive_repository, reset_repository_cache
from testo_core.db_config import reset_engine_cache
from testo_core.repository.report_archive_repository import SQLReportArchiveRepository


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def sqlite_report_repo(monkeypatch: pytest.MonkeyPatch) -> SQLReportArchiveRepository:
    reset_repository_cache()
    reset_engine_cache()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    try:
        yield get_report_archive_repository()
    finally:
        reset_repository_cache()
        reset_engine_cache()


def test_diff_metrics_only_uses_archive_columns_without_unzipping(
    runner: CliRunner,
    tmp_path: Path,
    sqlite_report_repo: SQLReportArchiveRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    baseline = sqlite_report_repo.insert(
        cycle_name="checkout",
        exit_code=0,
        summary_json={"plan": "checkout"},
        artifact_bytes=b"not a zip",
        total_tests=3,
        passed=3,
        failed=0,
        plan_duration_ms=1200,
    )
    current = sqlite_report_repo.insert(
        cycle_name="checkout",
        exit_code=1,
        summary_json={"plan": "checkout"},
        artifact_bytes=b"still not a zip",
        total_tests=5,
        passed=4,
        failed=1,
        plan_duration_ms=1500,
    )

    result = runner.invoke(
        app,
        [
            "diff",
            "--metrics-only",
            str(baseline.id),
            str(current.id),
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Run metrics" in result.stdout
    assert "total_tests" in result.stdout
    assert "plan_duration_ms" in result.stdout
    assert "300" in result.stdout
