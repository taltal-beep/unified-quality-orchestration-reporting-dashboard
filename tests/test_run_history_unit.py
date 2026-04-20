"""SQLite run history — exercised with a temp DB (no Streamlit)."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.command_builders import BuiltCommand
from engine.run_history import init_schema, list_recent_runs, record_completed_run, get_run, compare_latest_two
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
