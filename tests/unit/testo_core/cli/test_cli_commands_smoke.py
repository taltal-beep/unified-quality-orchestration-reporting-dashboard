"""Smoke tests for ancillary CLI commands (validate, doctor, cycles, version)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app
from tests.fixtures.engine.conftest import write_minimal_config


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_version_exits_0(runner: CliRunner) -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "testo" in (result.stdout + result.stderr).lower() or result.stdout


def test_config_validate_ok(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    result = runner.invoke(
        app,
        ["config", "validate", "--config", str(cfg), "--no-check-executables"],
    )
    assert result.exit_code == 0


def test_config_validate_broken_yaml_exits_2(runner: CliRunner, tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("cycles: [not: valid: yaml", encoding="utf-8")
    result = runner.invoke(app, ["config", "validate", "--config", str(bad), "--no-check-executables"])
    assert result.exit_code == 2


def test_cycles_list_and_show(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg, cycle_name="smoke")
    list_result = runner.invoke(app, ["cycles", "list", "--config", str(cfg)])
    assert list_result.exit_code == 0
    assert "smoke" in list_result.stdout
    show_result = runner.invoke(app, ["cycles", "show", "smoke", "--config", str(cfg)])
    assert show_result.exit_code == 0
    assert "smoke" in show_result.stdout.lower() or "s1" in show_result.stdout


def test_doctor_passes_with_minimal_config(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    write_minimal_config(cfg)
    with patch("shutil.which", return_value="/usr/bin/pytest"):
        result = runner.invoke(app, ["doctor", "--config", str(cfg)])
    assert result.exit_code == 0


def test_doctor_fails_on_bad_config(runner: CliRunner, tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("not: valid", encoding="utf-8")
    result = runner.invoke(app, ["doctor", "--config", str(bad)])
    assert result.exit_code == 2
