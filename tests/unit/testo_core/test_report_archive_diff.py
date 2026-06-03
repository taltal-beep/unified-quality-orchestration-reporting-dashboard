"""Tests for archived run diff (per-test Allure case map)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from testo_core.repository.models import ReportArchive
from testo_core.services.report_archive import build_cycle_zip_bytes
from testo_core.services.report_archive_diff import diff_archives, parse_archive_uuid, ArchiveDiffResult


def _plan_with_result(
    root: Path,
    plan: str,
    result_payload: dict,
    *,
    history: dict[str, Any] | None = None,
) -> bytes:
    plan_dir = root / plan
    plan_dir.mkdir(parents=True)
    (plan_dir / "events.ndjson").write_text("{}\n", encoding="utf-8")
    (plan_dir / "plan_result.json").write_text(
        json.dumps({"plan": plan, "exit_code": 0, "duration_s": 1.0}),
        encoding="utf-8",
    )
    res = plan_dir / "st" / "allure-results" / "pytest"
    res.mkdir(parents=True)
    (res / "t-result.json").write_text(json.dumps(result_payload), encoding="utf-8")
    if history is not None:
        hdir = res / "history"
        hdir.mkdir(parents=True)
        (hdir / "history.json").write_text(json.dumps(history), encoding="utf-8")
    blob, _summary, _ = build_cycle_zip_bytes(root, plan)
    return blob


def test_diff_archives_regression_and_fix(tmp_path: Path) -> None:
    plan = "same-cycle"
    base_blob = _plan_with_result(
        tmp_path / "b",
        plan,
        {"historyId": "hid1", "status": "passed", "name": "t", "start": 0, "stop": 1000},
    )
    cur_blob = _plan_with_result(
        tmp_path / "c",
        plan,
        {"historyId": "hid1", "status": "failed", "name": "t", "start": 0, "stop": 500},
    )

    bid, cid = uuid.uuid4(), uuid.uuid4()
    baseline = ReportArchive(
        id=bid,
        cycle_name=plan,
        exit_code=0,
        summary_json={},
        artifact_bytes=base_blob,
        total_tests=1,
        passed=1,
        failed=0,
    )
    current = ReportArchive(
        id=cid,
        cycle_name=plan,
        exit_code=1,
        summary_json={},
        artifact_bytes=cur_blob,
        total_tests=1,
        passed=0,
        failed=1,
    )

    td = tmp_path / "diffwork"
    td.mkdir()
    result = diff_archives(baseline=baseline, current=current, tmp=td)
    changes, metrics = result.changes, result.metrics
    kinds = {c.kind for c in changes}
    assert "regression" in kinds
    reg = next(c for c in changes if c.kind == "regression")
    assert reg.group == "(ungrouped)"
    assert isinstance(result, ArchiveDiffResult)
    assert metrics["baseline_id"] == str(bid)
    assert metrics["current_id"] == str(cid)

    fix_blob = _plan_with_result(
        tmp_path / "d",
        plan,
        {"historyId": "hid1", "status": "passed", "name": "t", "start": 0, "stop": 100},
    )
    fixed = ReportArchive(
        id=uuid.uuid4(),
        cycle_name=plan,
        exit_code=0,
        summary_json={},
        artifact_bytes=fix_blob,
    )
    td2 = tmp_path / "diffwork2"
    td2.mkdir()
    changes2 = diff_archives(baseline=current, current=fixed, tmp=td2).changes
    assert any(c.kind == "fix" for c in changes2)


def test_parse_archive_uuid() -> None:
    u = uuid.uuid4()
    assert parse_archive_uuid(str(u)) == u
    assert parse_archive_uuid("not-a-uuid") is None


def test_diff_archives_group_from_package_label(tmp_path: Path) -> None:
    plan = "pkg-cycle"
    labels = [{"name": "package", "value": "com.acme.tests"}]
    base_blob = _plan_with_result(
        tmp_path / "g1",
        plan,
        {
            "historyId": "hid2",
            "status": "passed",
            "name": "t2",
            "labels": labels,
            "start": 0,
            "stop": 100,
        },
    )
    cur_blob = _plan_with_result(
        tmp_path / "g2",
        plan,
        {
            "historyId": "hid2",
            "status": "failed",
            "name": "t2",
            "labels": labels,
            "start": 0,
            "stop": 200,
        },
    )
    baseline = ReportArchive(
        id=uuid.uuid4(),
        cycle_name=plan,
        exit_code=0,
        summary_json={},
        artifact_bytes=base_blob,
    )
    current = ReportArchive(
        id=uuid.uuid4(),
        cycle_name=plan,
        exit_code=1,
        summary_json={},
        artifact_bytes=cur_blob,
    )
    td = tmp_path / "diffpkg"
    td.mkdir()
    changes = diff_archives(baseline=baseline, current=current, tmp=td).changes
    reg = next(c for c in changes if c.kind == "regression")
    assert reg.group == "com.acme.tests"


def test_diff_archives_top_perf_passed_only(tmp_path: Path) -> None:
    plan = "perf"
    labels = [{"name": "tag", "value": "unit"}]
    base_blob = _plan_with_result(
        tmp_path / "perf1",
        plan,
        {
            "historyId": "hp1",
            "status": "passed",
            "name": "slow",
            "labels": labels,
            "start": 0,
            "stop": 100,
        },
    )
    cur_blob = _plan_with_result(
        tmp_path / "perf2",
        plan,
        {
            "historyId": "hp1",
            "status": "passed",
            "name": "slow",
            "labels": labels,
            "start": 0,
            "stop": 400,
        },
    )
    baseline = ReportArchive(
        id=uuid.uuid4(),
        cycle_name=plan,
        exit_code=0,
        summary_json={},
        artifact_bytes=base_blob,
    )
    current = ReportArchive(
        id=uuid.uuid4(),
        cycle_name=plan,
        exit_code=0,
        summary_json={},
        artifact_bytes=cur_blob,
    )
    td = tmp_path / "perf_td"
    td.mkdir()
    r = diff_archives(baseline=baseline, current=current, tmp=td)
    assert r.tier_counts.get("unit") == 1
    assert len(r.top_perf_regressions) == 1
    assert r.top_perf_regressions[0].delta_ms == 300
    assert any(c.kind == "perf_regression" for c in r.changes)


def test_diff_archives_skipped_to_passed_in_state_bucket(tmp_path: Path) -> None:
    plan = "skp"
    base_blob = _plan_with_result(
        tmp_path / "sk1",
        plan,
        {"historyId": "hs1", "status": "skipped", "name": "t", "start": 0, "stop": 0},
    )
    cur_blob = _plan_with_result(
        tmp_path / "sk2",
        plan,
        {"historyId": "hs1", "status": "passed", "name": "t", "start": 0, "stop": 10},
    )
    baseline = ReportArchive(
        id=uuid.uuid4(),
        cycle_name=plan,
        exit_code=0,
        summary_json={},
        artifact_bytes=base_blob,
    )
    current = ReportArchive(
        id=uuid.uuid4(),
        cycle_name=plan,
        exit_code=0,
        summary_json={},
        artifact_bytes=cur_blob,
    )
    td = tmp_path / "sk_td"
    td.mkdir()
    changes = diff_archives(baseline=baseline, current=current, tmp=td).changes
    sc = next(c for c in changes if c.kind == "status_change")
    from testo_core.cli.ui.summary_dashboard import _is_regression_risk_row, _is_state_or_improvement_row

    assert not _is_regression_risk_row(sc)
    assert _is_state_or_improvement_row(sc)


def test_diff_archives_flaky_pass_from_history_json(tmp_path: Path) -> None:
    plan = "flk"
    hist = {"hid_z": {"items": [{"status": "failed", "uid": "a"}]}}
    base_blob = _plan_with_result(
        tmp_path / "f1",
        plan,
        {"historyId": "hid_z", "status": "passed", "name": "x", "start": 0, "stop": 10},
    )
    cur_blob = _plan_with_result(
        tmp_path / "f2",
        plan,
        {"historyId": "hid_z", "status": "passed", "name": "x", "start": 0, "stop": 20},
        history=hist,
    )
    baseline = ReportArchive(
        id=uuid.uuid4(),
        cycle_name=plan,
        exit_code=0,
        summary_json={},
        artifact_bytes=base_blob,
    )
    current = ReportArchive(
        id=uuid.uuid4(),
        cycle_name=plan,
        exit_code=0,
        summary_json={},
        artifact_bytes=cur_blob,
    )
    td = tmp_path / "flk_td"
    td.mkdir()
    r = diff_archives(baseline=baseline, current=current, tmp=td)
    assert r.flaky_pass_count == 1


def test_diff_archives_flaky_from_prior_archive(tmp_path: Path) -> None:
    plan = "flk2"
    prior_blob = _plan_with_result(
        tmp_path / "prior",
        plan,
        {"historyId": "hid_prior", "status": "failed", "name": "p", "start": 0, "stop": 5},
    )
    base_blob = _plan_with_result(
        tmp_path / "bpr",
        plan,
        {"historyId": "hid_prior", "status": "passed", "name": "p", "start": 0, "stop": 10},
    )
    cur_blob = _plan_with_result(
        tmp_path / "cpr",
        plan,
        {"historyId": "hid_prior", "status": "passed", "name": "p", "start": 0, "stop": 12},
    )
    prior_arch = ReportArchive(
        id=uuid.uuid4(),
        cycle_name=plan,
        exit_code=1,
        summary_json={},
        artifact_bytes=prior_blob,
    )
    baseline = ReportArchive(
        id=uuid.uuid4(),
        cycle_name=plan,
        exit_code=0,
        summary_json={},
        artifact_bytes=base_blob,
    )
    current = ReportArchive(
        id=uuid.uuid4(),
        cycle_name=plan,
        exit_code=0,
        summary_json={},
        artifact_bytes=cur_blob,
    )
    td = tmp_path / "flk2_td"
    td.mkdir()
    r = diff_archives(
        baseline=baseline,
        current=current,
        tmp=td,
        flaky_prior_archives=[prior_arch],
    )
    assert r.flaky_pass_count == 1
