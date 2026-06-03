"""CLI tests for ``testo run`` ``--tag``, ``--dry-run``, and tag filtering."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write_cfg(path: Path) -> None:
    path.write_text(
        """
version: 1
defaults:
  target_repo: .
  artifacts_root: artifacts
cycles:
  api-only:
    tags: [api]
    stages:
      - name: s
        equipment: pytest
        args: ["--version"]
  no-tags:
    stages:
      - name: s
        equipment: pytest
        args: ["--version"]
""".strip(),
        encoding="utf-8",
    )


def test_run_rejects_tag_not_on_cycle(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    _write_cfg(cfg)
    r = runner.invoke(app, ["run", "--config", str(cfg), "--cycle", "api-only", "--tag", "smoke", "--dry-run"])
    assert r.exit_code != 0
    assert "does not include tag" in r.stdout.lower()


def test_run_all_filters_by_tag_dry_run(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "testosterone.yaml"
    _write_cfg(cfg)
    r = runner.invoke(app, ["run", "--config", str(cfg), "--cycle", "all", "--tag", "api", "--dry-run"])
    assert r.exit_code == 0, r.stdout + r.stderr
    assert "api-only" in r.stdout
    assert "no-tags" not in r.stdout
