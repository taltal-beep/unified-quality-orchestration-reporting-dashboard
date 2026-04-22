"""SQLite run history — exercised with a temp DB (no Streamlit)."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.command_builders import BuiltCommand
from engine.run_history import init_schema, list_recent_runs, record_completed_run, get_run, compare_latest_two, list_run_sessions
from engine.runners import RunResult


def test_init_and_list_recent_empty(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    init_schema(db)
    assert list_recent_runs(limit=5, db_path=db) == []


def test_record_completed_run_inserts_row(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    cmd = BuiltCommand(argv=["pytest"], cwd=tmp_path, env={"UQO_RUN_ID": "rid-1"})
    rr = RunResult(returncode=0, started_at=0.0, finished_at=1.0, command=cmd)
    (tmp_path / "allure-results").mkdir(parents=True)
    monkeypatch.setattr("engine.run_history._snapshot_reports", lambda **_: None)
    record_completed_run(rr=rr, artifacts_root=tmp_path, test_kind="pytest", db_path=db)
    rows = list_recent_runs(limit=5, db_path=db)
    assert len(rows) == 1
    assert rows[0].run_id == "rid-1"
    assert get_run(run_id="rid-1", db_path=db) is not None


def test_compare_latest_two_none_when_insufficient(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    init_schema(db)
    assert compare_latest_two(db_path=db) is None


def test_list_run_sessions_maps_new_allure_reports_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Point the static history root at a temp directory so we can create fake snapshots.
    fake_static_history = tmp_path / "static" / "history"
    monkeypatch.setattr("engine.run_history.STATIC_HISTORY_ROOT", fake_static_history)

    db = tmp_path / "db.sqlite"
    cmd = BuiltCommand(argv=["pytest"], cwd=tmp_path, env={"UQO_RUN_ID": "rid-1"})
    rr = RunResult(returncode=0, started_at=0.0, finished_at=1.0, command=cmd)
    (tmp_path / "allure-results").mkdir(parents=True)
    monkeypatch.setattr("engine.run_history._snapshot_reports", lambda **_: None)
    record_completed_run(rr=rr, artifacts_root=tmp_path, test_kind="pytest", db_path=db)

    base = fake_static_history / "rid-1" / "allure_reports"
    (base / "pytest").mkdir(parents=True)
    (base / "pytest" / "index.html").write_text("ok", encoding="utf-8")
    (base / "behave_native").mkdir(parents=True)
    (base / "behave_native" / "index.html").write_text("ok", encoding="utf-8")

    sessions = list_run_sessions(limit=5, db_path=db)
    assert sessions
    links = sessions[0].links_under_static
    assert links["pytest"].endswith("history/rid-1/allure_reports/pytest/index.html")
    assert links["behave_native"].endswith("history/rid-1/allure_reports/behave_native/index.html")
