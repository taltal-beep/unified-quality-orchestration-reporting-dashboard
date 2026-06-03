"""Tests for delta-first Allure result mutations."""

from __future__ import annotations

import json
from pathlib import Path

from testo_core.reporting.allure_delta_transform import apply_delta_first_mutations
from testo_core.services.report_archive_diff import (
    allure_case_key,
    classify_case_change,
    case_synopsis_from_result,
    load_case_paths_by_key,
)


def _write_case(
    plan: Path,
    *,
    hid: str,
    status: str,
    start: int = 0,
    stop: int = 100,
    labels: list[dict[str, str]] | None = None,
) -> None:
    plan.mkdir(parents=True, exist_ok=True)
    body: dict = {
        "historyId": hid,
        "uuid": hid,
        "name": f"test_{hid}",
        "status": status,
        "start": start,
        "stop": stop,
    }
    if labels is not None:
        body["labels"] = labels
    (plan / f"{hid}-result.json").write_text(json.dumps(body), encoding="utf-8")


def test_classify_case_change_public_wrapper() -> None:
    b = {"name": "x", "group": "g", "status": "passed", "duration_ms": 10}
    c = {"name": "x", "group": "g", "status": "failed", "duration_ms": 20}
    assert classify_case_change(b, c) == "regression"
    assert classify_case_change(None, c) == "added"


def test_load_case_paths_by_key(tmp_path: Path) -> None:
    p = tmp_path / "plan"
    _write_case(p, hid="h1", status="passed")
    m = load_case_paths_by_key(p)
    assert len(m) == 1
    assert m["h1"] == p / "h1-result.json"


def test_apply_delta_regression_marker_severity_tag(tmp_path: Path) -> None:
    base = tmp_path / "baseline"
    cur = tmp_path / "current"
    labels = [{"name": "parentSuite", "value": "MySuite"}]
    _write_case(base, hid="r1", status="passed", start=0, stop=10, labels=labels)
    _write_case(cur, hid="r1", status="failed", start=0, stop=10, labels=labels)

    stats = apply_delta_first_mutations(baseline_plan_root=base, current_plan_root=cur)
    data = json.loads((cur / "r1-result.json").read_text(encoding="utf-8"))
    assert "[TESTO:REGRESSION]" in str(data.get("statusDetails", {}).get("message", ""))
    assert data.get("severity") == "blocker"
    tag_vals = [x.get("value") for x in (data.get("labels") or []) if x.get("name") == "tag"]
    assert "REGRESSION" in tag_vals


def test_apply_delta_suite_pass_rate_suffix(tmp_path: Path) -> None:
    base = tmp_path / "baseline"
    cur = tmp_path / "current"
    lab = [{"name": "parentSuite", "value": "S"}]
    _write_case(base, hid="a", status="passed", labels=lab)
    _write_case(base, hid="b", status="passed", labels=lab)
    _write_case(cur, hid="a", status="passed", labels=lab)
    _write_case(cur, hid="b", status="failed", labels=lab)

    apply_delta_first_mutations(baseline_plan_root=base, current_plan_root=cur)
    for hid in ("a", "b"):
        data = json.loads((cur / f"{hid}-result.json").read_text(encoding="utf-8"))
        ps = next(
            x["value"]
            for x in (data.get("labels") or [])
            if isinstance(x, dict) and x.get("name") == "parentSuite"
        )
        assert "(" in ps and "%" in ps


def test_apply_delta_performance_table(tmp_path: Path) -> None:
    base = tmp_path / "baseline"
    cur = tmp_path / "current"
    _write_case(base, hid="slow", status="passed", start=0, stop=100)
    _write_case(cur, hid="slow", status="passed", start=0, stop=500)

    stats = apply_delta_first_mutations(baseline_plan_root=base, current_plan_root=cur)
    assert "slow" in stats.performance_summary_md or "slow" in stats.performance_summary_md.lower()
    assert "+400 ms" in stats.performance_summary_md


def test_apply_delta_persistent_and_new_failure(tmp_path: Path) -> None:
    base = tmp_path / "baseline"
    cur = tmp_path / "current"
    _write_case(base, hid="p1", status="failed")
    _write_case(cur, hid="p1", status="failed")
    _write_case(cur, hid="new1", status="failed")

    apply_delta_first_mutations(baseline_plan_root=base, current_plan_root=cur)
    p1 = json.loads((cur / "p1-result.json").read_text(encoding="utf-8"))
    assert "[TESTO:PERSISTENT]" in str(p1.get("statusDetails", {}).get("message", ""))
    new1 = json.loads((cur / "new1-result.json").read_text(encoding="utf-8"))
    assert "[TESTO:NEW_FAILURE]" in str(new1.get("statusDetails", {}).get("message", ""))


def test_case_synopsis_from_result_shape(tmp_path: Path) -> None:
    p = tmp_path / "x"
    _write_case(p, hid="k1", status="passed")
    data = json.loads((p / "k1-result.json").read_text(encoding="utf-8"))
    syn = case_synopsis_from_result(data)
    assert syn["status"] == "passed"
    assert allure_case_key(data) == "k1"
