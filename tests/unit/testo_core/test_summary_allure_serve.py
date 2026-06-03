"""Tests for ``testo summary`` Allure history injection and ``serve_results``."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.db import get_report_archive_repository, reset_repository_cache
from testo_core.db_config import reset_engine_cache
from testo_core.reporting.allure import AllureCLINotFoundError, AllureGenerateResult, serve_results
from testo_core.reporting.allure_history_serve import run_summary_allure_pipeline
from testo_core.services.report_archive import build_cycle_zip_bytes


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _minimal_cycle_artifacts(base: Path, plan: str = "cyc") -> bytes:
    root = base / "artifacts"
    plan_dir = root / plan
    (plan_dir / "st1" / "allure-results" / "pytest").mkdir(parents=True)
    (plan_dir / "st1" / "allure-results" / "pytest" / "a-result.json").write_text(
        '{"name":"x","status":"passed","historyId":"h1"}', encoding="utf-8"
    )
    (plan_dir / "plan_result.json").write_text(
        json.dumps({"plan": plan, "exit_code": 0, "stages": []}),
        encoding="utf-8",
    )
    (plan_dir / "events.ndjson").write_text('{"event":"plan_started"}\n', encoding="utf-8")
    blob, _, _ = build_cycle_zip_bytes(root, plan)
    return blob


def test_serve_results_raises_when_allure_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("testo_core.reporting.allure.is_allure_available", lambda: False)
    rd = Path("/tmp/nonexistent-results")
    with pytest.raises(AllureCLINotFoundError):
        serve_results(result_dirs=[rd])


def test_run_summary_allure_pipeline_injects_history_before_serve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from testo_core.repository.models import ReportArchive

    blob = _minimal_cycle_artifacts(tmp_path, "p1")
    base_row = ReportArchive(
        id=uuid.uuid4(),
        cycle_name="p1",
        exit_code=0,
        summary_json={},
        artifact_bytes=blob,
    )
    cur_row = ReportArchive(
        id=uuid.uuid4(),
        cycle_name="p1",
        exit_code=0,
        summary_json={},
        artifact_bytes=blob,
    )

    captured: list[list[Path]] = []

    def fake_generate(*, result_dirs, out_dir, clean=True):
        out_dir.mkdir(parents=True, exist_ok=True)
        hist = out_dir / "history"
        hist.mkdir()
        (hist / "history.json").write_text("[]", encoding="utf-8")
        (out_dir / "index.html").write_text("<html/>", encoding="utf-8")
        return AllureGenerateResult(ok=True, out_dir=out_dir, message="ok")

    def fake_serve(*, result_dirs, port=8080):
        captured.append(list(result_dirs))
        for d in result_dirs:
            assert (d / "history" / "history.json").is_file()
        return 0

    monkeypatch.setattr("testo_core.reporting.allure_history_serve.generate_html", fake_generate)
    monkeypatch.setattr("testo_core.reporting.allure_history_serve.serve_results", fake_serve)

    console = MagicMock()
    run_summary_allure_pipeline(baseline=base_row, current=cur_row, console=console)
    assert len(captured) == 1
    assert captured[0]


def test_run_summary_allure_pipeline_baseline_none_skips_generate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from testo_core.repository.models import ReportArchive

    blob = _minimal_cycle_artifacts(tmp_path, "solo")
    cur_row = ReportArchive(
        id=uuid.uuid4(),
        cycle_name="solo",
        exit_code=0,
        summary_json={},
        artifact_bytes=blob,
    )
    gen = MagicMock()
    monkeypatch.setattr("testo_core.reporting.allure_history_serve.generate_html", gen)

    def fake_serve(*, result_dirs, port=8080):
        for d in result_dirs:
            assert not (d / "history").exists()
        return 0

    monkeypatch.setattr("testo_core.reporting.allure_history_serve.serve_results", fake_serve)
    console = MagicMock()
    run_summary_allure_pipeline(baseline=None, current=cur_row, console=console)
    gen.assert_not_called()


def test_summary_cli_one_id_errors(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    reset_repository_cache()
    reset_engine_cache()
    try:
        rid = uuid.uuid4()
        r = runner.invoke(app, ["summary", str(rid)])
    finally:
        reset_repository_cache()
        reset_engine_cache()
    assert r.exit_code == 2
    out = r.stdout.lower()
    assert "zero report archive" in out or "exactly two" in out


def test_summary_cli_missing_baseline_exits_zero_without_allure(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    reset_repository_cache()
    reset_engine_cache()
    try:
        blob = _minimal_cycle_artifacts(tmp_path, "cyc")
        row = get_report_archive_repository().insert(
            cycle_name="cyc",
            exit_code=0,
            summary_json={"plan": "cyc"},
            artifact_bytes=blob,
        )
        missing = uuid.uuid4()

        def boom(*_a: object, **_k: object) -> None:
            raise AssertionError("summary must not invoke Allure pipeline")

        monkeypatch.setattr(
            "testo_core.reporting.allure_history_serve.run_summary_allure_pipeline",
            boom,
        )

        r = runner.invoke(app, ["summary", str(missing), str(row.id)])
        assert r.exit_code == 0, r.stdout + r.stderr
        assert "baseline" in r.stdout.lower()
        assert "report compare" in r.stdout.lower()
    finally:
        reset_repository_cache()
        reset_engine_cache()


def test_report_compare_cli_two_rows_zero_args(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    reset_repository_cache()
    reset_engine_cache()
    try:
        repo = get_report_archive_repository()
        b1 = _minimal_cycle_artifacts(tmp_path / "run_a", "c1")
        b2 = _minimal_cycle_artifacts(tmp_path / "run_b", "c1")
        repo.insert(cycle_name="c1", exit_code=0, summary_json={}, artifact_bytes=b1)
        repo.insert(cycle_name="c1", exit_code=0, summary_json={}, artifact_bytes=b2)

        monkeypatch.setattr("testo_core.reporting.allure_history_serve.serve_results", lambda **_: 0)

        def fake_gen(**kwargs: object) -> AllureGenerateResult:
            out_dir = kwargs["out_dir"]
            assert isinstance(out_dir, Path)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "history").mkdir(exist_ok=True)
            (out_dir / "history" / "history.json").write_text("[]", encoding="utf-8")
            (out_dir / "index.html").write_text("x", encoding="utf-8")
            return AllureGenerateResult(ok=True, out_dir=out_dir, message="ok")

        monkeypatch.setattr("testo_core.reporting.allure_history_serve.generate_html", fake_gen)

        r = runner.invoke(app, ["report", "compare"])
        assert r.exit_code == 0, r.stdout + r.stderr
        assert "Generating visual comparison report" in r.stdout
    finally:
        reset_repository_cache()
        reset_engine_cache()
