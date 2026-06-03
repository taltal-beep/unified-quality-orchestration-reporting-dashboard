"""CLI tests for ``testo summary`` (auto-pick latest pair vs explicit archive UUIDs)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.db import get_report_archive_repository, reset_repository_cache
from testo_core.db_config import reset_engine_cache
from testo_core.services.report_archive import build_cycle_zip_bytes


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _minimal_cycle_artifacts(base: Path, plan: str = "cyc") -> bytes:
    root = base / "artifacts"
    plan_dir = root / plan
    (plan_dir / "st1" / "allure-results" / "pytest").mkdir(parents=True)
    (plan_dir / "st1" / "allure-results" / "pytest" / "a-result.json").write_text(
        '{"name":"x","status":"passed"}', encoding="utf-8"
    )
    (plan_dir / "plan_result.json").write_text(
        json.dumps({"plan": plan, "exit_code": 0, "stages": []}),
        encoding="utf-8",
    )
    (plan_dir / "events.ndjson").write_text('{"event":"plan_started"}\n', encoding="utf-8")
    blob, _, _ = build_cycle_zip_bytes(root, plan)
    return blob


def test_summary_requires_two_archives_when_auto_pick(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    reset_repository_cache()
    reset_engine_cache()
    try:
        get_report_archive_repository().insert(
            cycle_name="c",
            exit_code=0,
            summary_json={"plan": "c"},
            artifact_bytes=_minimal_cycle_artifacts(tmp_path, "c"),
        )
        r = runner.invoke(app, ["summary"])
        assert r.exit_code != 0
        assert "at least two" in r.stdout.lower()
    finally:
        reset_repository_cache()
        reset_engine_cache()


def test_summary_auto_uses_two_most_recent(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    reset_repository_cache()
    reset_engine_cache()
    calls: list[tuple] = []

    def fake_render(*, console, baseline, current, metrics_only, **kwargs) -> None:  # noqa: ANN001, ARG002
        calls.append(("render", baseline.id, current.id))

    try:
        repo = get_report_archive_repository()
        older = repo.insert(
            cycle_name="cyc",
            exit_code=0,
            summary_json={"plan": "cyc"},
            artifact_bytes=_minimal_cycle_artifacts(tmp_path / "older_root", "cyc"),
        )
        newer = repo.insert(
            cycle_name="cyc",
            exit_code=0,
            summary_json={"plan": "cyc"},
            artifact_bytes=_minimal_cycle_artifacts(tmp_path / "newer_root", "cyc"),
        )

        monkeypatch.setattr("testo_core.cli.commands.diff_cli._render_diff", fake_render)

        r = runner.invoke(app, ["summary"])
        assert r.exit_code == 0, r.stdout + r.stderr
        assert str(older.id) in r.stdout
        assert str(newer.id) in r.stdout
        assert ("render", older.id, newer.id) in calls
        assert "report compare" in r.stdout.lower()
    finally:
        reset_repository_cache()
        reset_engine_cache()


def test_summary_single_uuid_errors(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    reset_repository_cache()
    reset_engine_cache()
    try:
        rid = uuid4()
        r = runner.invoke(app, ["summary", str(rid)])
        assert r.exit_code != 0
        assert "two" in r.stdout.lower() or "zero" in r.stdout.lower()
    finally:
        reset_repository_cache()
        reset_engine_cache()


def test_report_compare_explicit_missing_baseline_still_runs_pipeline(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    reset_repository_cache()
    reset_engine_cache()
    calls: list[tuple] = []

    def fake_pipeline(*, baseline, current, console, serve=True) -> None:  # noqa: ANN001, ARG001
        calls.append((baseline, current.id, serve))

    try:
        cur = get_report_archive_repository().insert(
            cycle_name="cyc",
            exit_code=0,
            summary_json={"plan": "cyc"},
            artifact_bytes=_minimal_cycle_artifacts(tmp_path, "cyc"),
        )
        missing = uuid4()
        monkeypatch.setattr(
            "testo_core.reporting.allure_history_serve.run_summary_allure_pipeline",
            fake_pipeline,
        )
        r = runner.invoke(app, ["report", "compare", str(missing), str(cur.id)])
        assert r.exit_code == 0, r.stdout + r.stderr
        assert any(c[0] is None and c[1] == cur.id for c in calls)
        assert "baseline" in r.stdout.lower()
    finally:
        reset_repository_cache()
        reset_engine_cache()
