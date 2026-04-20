"""Coverage for ``ReportService`` (new unified/individual entrypoints)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from engine.services.report_service import ReportService


def test_generate_unified_allure_delegates(tmp_path: Path) -> None:
    svc = ReportService(artifacts_root=tmp_path)
    (tmp_path / "allure-results").mkdir(parents=True, exist_ok=True)
    fake = MagicMock()
    fake.returncode = 0
    fake.stderr = ""
    fake.stdout = "ok"

    def run_ok(cmd: list[str], **_kw: object):
        return fake

    with patch("engine.report_generator.publish_allure_index_to_static", lambda **_: None):
        ok, _msg, _hp = svc.generate_unified_allure(subprocess_run=run_ok)
    assert ok is True


def test_generate_individual_allure_delegates(tmp_path: Path) -> None:
    svc = ReportService(artifacts_root=tmp_path)
    (tmp_path / "allure-results").mkdir(parents=True, exist_ok=True)
    fake = MagicMock()
    fake.returncode = 0
    fake.stderr = ""
    fake.stdout = "ok"

    def run_ok(cmd: list[str], **_kw: object):
        return fake

    with patch("engine.report_generator.publish_allure_index_to_static", lambda **_: None):
        out = svc.generate_individual_allure(frameworks=["pytest"], subprocess_run=run_ok)
    assert "pytest" in out
