"""Tests for Allure HTML generation helpers (mocked ``subprocess``)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine import report_generator as rg
from engine.report_generator import generate_allure_html, generate_allure_reports


@pytest.fixture
def fake_ok_subprocess() -> MagicMock:
    p = MagicMock()
    p.returncode = 0
    p.stderr = ""
    p.stdout = "ok"
    return MagicMock(return_value=p)


def test_generate_allure_html_success(tmp_path: Path, fake_ok_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    res = tmp_path / "allure-results"
    res.mkdir()
    (res / "pytest").mkdir()
    (res / "pytest" / "a-result.json").write_text(
        '{"status":"passed","start":0,"stop":10}',
        encoding="utf-8",
    )
    out = tmp_path / "out"
    monkeypatch.setattr(rg, "publish_allure_index_to_static", lambda **_: out)
    ok, msg, health = generate_allure_html(
        results_dir=res,
        report_dir=out,
        input_dirs=[res / "pytest", res / "behave", res / "locust", res / "behave_native"],
        subprocess_run=fake_ok_subprocess,
    )
    assert ok is True
    fake_ok_subprocess.assert_called_once()
    call_cmd = fake_ok_subprocess.call_args[0][0]
    assert call_cmd[0:2] == ["allure", "generate"]
    # Unified mode passes multiple inputs (subdirs exist or are created).
    assert str(res / "pytest") in call_cmd
    assert str(res / "behave") in call_cmd
    assert str(res / "locust") in call_cmd
    assert str(res / "behave_native") in call_cmd
    assert isinstance(health, float) and health == 100.0


def test_generate_allure_html_missing_results(tmp_path: Path) -> None:
    ok, msg, health = generate_allure_html(results_dir=tmp_path / "nope", report_dir=tmp_path / "out")
    assert ok is False
    assert "does not exist" in msg


def test_invoke_allure_generate_file_not_found(tmp_path: Path) -> None:
    def boom(cmd: list[str], **_kwargs: object) -> None:
        raise FileNotFoundError()

    res = tmp_path / "allure-results"
    res.mkdir()
    ok, msg, _ = generate_allure_html(results_dir=res, report_dir=tmp_path / "rep", subprocess_run=boom)
    assert ok is False
    assert "Allure CLI not found" in msg


def test_generate_allure_reports_individual_builds_per_framework_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    res = tmp_path / "allure-results"
    res.mkdir()
    (res / "pytest").mkdir()
    (res / "pytest" / "a-result.json").write_text('{"status":"passed","start":0,"stop":1}', encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object):
        calls.append(cmd)
        p = MagicMock()
        p.returncode = 0
        p.stderr = ""
        p.stdout = "ok"
        return p

    # Avoid chmod/mirroring noise in this unit test
    monkeypatch.setattr(rg, "publish_allure_index_to_static", lambda **_: None)

    out = generate_allure_reports(
        results_dir=res,
        mode="individual",
        frameworks=["pytest", "locust"],
        subprocess_run=fake_run,
    )
    assert "pytest" in out and "locust" in out
    assert len(calls) == 2
    assert any(str(res / "pytest") in c for c in calls)
    assert any(str(res / "locust") in c for c in calls)

