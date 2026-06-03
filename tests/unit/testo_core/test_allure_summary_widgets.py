"""Tests for Allure comparison sidecars and diff counters used by ``testo summary``."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from testo_core.reporting.allure_summary_widgets import (
    comparison_delta_categories,
    pass_rate_delta_display,
    write_summary_comparison_sidecars,
)
from testo_core.repository.models import ReportArchive
from testo_core.services.report_archive_diff import count_regression_and_fix_between_plans


def _write_result(plan: Path, name: str, status: str) -> None:
    plan.mkdir(parents=True, exist_ok=True)
    body = {"uuid": name, "name": name, "status": status, "start": 0, "stop": 1}
    (plan / f"{name}-result.json").write_text(json.dumps(body), encoding="utf-8")


def test_count_regression_and_fix_between_plans(tmp_path: Path) -> None:
    base = tmp_path / "base"
    cur = tmp_path / "cur"
    _write_result(base, "t1", "passed")
    _write_result(base, "t2", "passed")
    _write_result(cur, "t1", "failed")
    _write_result(cur, "t2", "passed")
    _write_result(cur, "t3", "passed")
    r, f = count_regression_and_fix_between_plans(base, cur)
    assert r == 1
    assert f == 0


def test_pass_rate_delta_display() -> None:
    b = ReportArchive(
        cycle_name="c",
        exit_code=0,
        summary_json={},
        artifact_bytes=b"x",
        total_tests=100,
        passed=90,
    )
    c = ReportArchive(
        cycle_name="c",
        exit_code=0,
        summary_json={},
        artifact_bytes=b"y",
        total_tests=100,
        passed=76,
    )
    assert pass_rate_delta_display(baseline=b, current=c) == "-14.0%"


def test_comparison_delta_categories_order() -> None:
    cats = comparison_delta_categories()
    assert cats[0]["name"] == "Regressions (Critical)"
    assert "messageRegex" in cats[0]


def test_write_summary_comparison_sidecars_with_baseline_delta(tmp_path: Path) -> None:
    rd = tmp_path / "allure-results" / "pytest"
    rd.mkdir(parents=True)
    bid = uuid.uuid4()
    cid = uuid.uuid4()
    baseline = ReportArchive(
        id=bid,
        cycle_name="c",
        exit_code=0,
        summary_json={},
        artifact_bytes=b"b",
        total_tests=10,
        passed=8,
    )
    current = ReportArchive(
        id=cid,
        cycle_name="c",
        exit_code=0,
        summary_json={},
        artifact_bytes=b"c",
        total_tests=10,
        passed=9,
    )
    write_summary_comparison_sidecars(
        result_dirs=[rd],
        baseline=baseline,
        current=current,
        regressions_found=3,
        fixes_verified=2,
        performance_summary_md="| a | +10 ms |\n| b | +5 ms |",
    )
    env = (rd / "environment.properties").read_text(encoding="utf-8")
    assert "Report_Type=Delta Comparison" in env
    assert "Regressions_Found=3" in env
    assert "Fixes_Verified=2" in env
    assert "Performance_Regressions_MD=" in env
    assert "\\n" in env or "Performance_Regressions_MD=" in env
    exe = json.loads((rd / "executor.json").read_text(encoding="utf-8"))
    assert exe["name"] == "Testosterone CLI"
    assert exe["type"] == "cli"
    assert "Testosterone Comparison" in exe["reportName"]
    assert exe["buildName"] == f"Diff: {str(bid)[:8]} -> {str(cid)[:8]}"
    cats = json.loads((rd / "categories.json").read_text(encoding="utf-8"))
    assert cats[0]["name"] == "Regressions (Critical)"
    assert cats[0]["matchedStatuses"] == ["failed", "broken"]


def test_write_summary_comparison_sidecars_no_baseline(tmp_path: Path) -> None:
    rd = tmp_path / "allure-results" / "pytest"
    rd.mkdir(parents=True)
    current = ReportArchive(
        id=uuid.uuid4(),
        cycle_name="c",
        exit_code=0,
        summary_json={},
        artifact_bytes=b"c",
        total_tests=10,
        passed=9,
    )
    write_summary_comparison_sidecars(
        result_dirs=[rd],
        baseline=None,
        current=current,
        regressions_found=0,
        fixes_verified=0,
    )
    cats = json.loads((rd / "categories.json").read_text(encoding="utf-8"))
    assert cats[0]["name"] == "Product Defects"
    exe = json.loads((rd / "executor.json").read_text(encoding="utf-8"))
    assert "Quarterly" in exe["buildName"]


def test_write_summary_comparison_sidecars_baseline_two_dirs_executor_only_first(
    tmp_path: Path,
) -> None:
    rd1 = tmp_path / "allure-results" / "pytest"
    rd2 = tmp_path / "allure-results" / "behavex"
    rd1.mkdir(parents=True)
    rd2.mkdir(parents=True)
    baseline = ReportArchive(
        id=uuid.uuid4(),
        cycle_name="c",
        exit_code=0,
        summary_json={},
        artifact_bytes=b"b",
        total_tests=2,
        passed=2,
    )
    current = ReportArchive(
        id=uuid.uuid4(),
        cycle_name="c",
        exit_code=0,
        summary_json={},
        artifact_bytes=b"c",
        total_tests=2,
        passed=2,
    )
    (rd2 / "executor.json").write_text('{"legacy": true}\n', encoding="utf-8")
    write_summary_comparison_sidecars(
        result_dirs=[rd1, rd2],
        baseline=baseline,
        current=current,
        regressions_found=0,
        fixes_verified=0,
    )
    assert (rd1 / "executor.json").is_file()
    assert not (rd2 / "executor.json").exists()
