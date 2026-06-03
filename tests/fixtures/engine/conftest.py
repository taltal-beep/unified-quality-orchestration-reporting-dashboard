"""Shared helpers for Testo engine and CLI unit tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from testo_core.config.schema import Plan, Stage
from testo_core.engine.result import StageResult


FIXTURES_ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = FIXTURES_ROOT / "scripts"


def write_minimal_config(
    path: Path,
    *,
    cycle_name: str = "smoke",
    cycle_extra: str = "",
    stages_yaml: str | None = None,
    defaults_extra: str = "",
) -> Path:
    """Write a minimal version-1 testosterone.yaml under ``path``."""
    if stages_yaml is None:
        stages_yaml = """
      - name: s1
        equipment: pytest
        args: ["--version"]
"""
    body = f"""
version: 1
defaults:
  target_repo: .
  artifacts_root: artifacts
{defaults_extra}
cycles:
  {cycle_name}:
    description: test cycle
{cycle_extra}
    stages:
{stages_yaml}
""".strip()
    path.write_text(body + "\n", encoding="utf-8")
    return path


def write_two_cycle_config(path: Path) -> Path:
    """Two cycles for ``--cycle all`` tests."""
    body = """
version: 1
defaults:
  target_repo: .
  artifacts_root: artifacts
cycles:
  alpha:
    stages:
      - name: s
        equipment: pytest
        args: ["--version"]
  beta:
    stages:
      - name: s
        equipment: pytest
        args: ["--version"]
""".strip()
    path.write_text(body + "\n", encoding="utf-8")
    return path


def parse_ndjson(stdout: str) -> list[dict[str, Any]]:
    """Parse newline-delimited JSON from CI stdout."""
    out: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        out.append(json.loads(line))
    return out


def fake_stage_result(
    stage: Stage,
    *,
    returncode: int = 0,
    tmp_path: Path | None = None,
    timed_out: bool = False,
    internal_failure: bool = False,
    error: str | None = None,
) -> StageResult:
    """Build a minimal :class:`StageResult` for orchestrator mocks."""
    import time

    now = time.time()
    root = (tmp_path or Path(".")).resolve()
    log = root / "run.log"
    return StageResult(
        stage_name=stage.name,
        framework=stage.framework,
        returncode=returncode,
        started_at=now,
        finished_at=now,
        duration_s=0.0,
        log_path=log,
        artifacts_dir=root,
        command=(),
        output_tail="",
        timed_out=timed_out,
        internal_failure=internal_failure,
        error=error,
    )


def write_multi_stage_config(
    path: Path,
    *,
    cycle_name: str = "multi",
    stage_count: int = 2,
    tags: str = "",
    cycle_extra: str = "",
) -> Path:
    """Write a cycle with ``stage_count`` pytest stages."""
    stage_lines = "\n".join(
        f"""      - name: s{i}
        equipment: pytest
        args: ["--version"]"""
        for i in range(1, stage_count + 1)
    )
    tags_block = f"    tags: [{tags}]\n" if tags else ""
    body = f"""
version: 1
defaults:
  target_repo: .
  artifacts_root: artifacts
cycles:
  {cycle_name}:
    description: multi-stage test cycle
{tags_block}{cycle_extra}
    stages:
{stage_lines}
""".strip()
    path.write_text(body + "\n", encoding="utf-8")
    return path


def write_tagged_cycles_config(path: Path) -> Path:
    """Two cycles: one tagged ``smoke``, one untagged."""
    body = """
version: 1
defaults:
  target_repo: .
  artifacts_root: artifacts
cycles:
  smoke-cycle:
    tags: [smoke]
    stages:
      - name: s
        equipment: pytest
        args: ["--version"]
  full-cycle:
    stages:
      - name: s
        equipment: pytest
        args: ["--version"]
""".strip()
    path.write_text(body + "\n", encoding="utf-8")
    return path


def load_ndjson_events(path: Path) -> list[dict[str, Any]]:
    """Load all JSON objects from an ``events.ndjson`` file."""
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def assert_ndjson_events(path: Path, expected_types: list[str]) -> list[dict[str, Any]]:
    """Assert ``events.ndjson`` event types match ``expected_types`` in order."""
    events = load_ndjson_events(path)
    actual = [e["event"] for e in events]
    assert actual == expected_types, f"expected {expected_types}, got {actual}"
    return events


class EchoAdapter:
    """Minimal adapter that runs ``scripts/echo.py`` for integration tests."""

    name = "pytest"

    def __init__(self, script_path: Path, *, exit_code: int = 0) -> None:
        import sys

        self._script = script_path
        self._exit_code = exit_code
        self._python = sys.executable

    def results_subdir(self) -> str:
        return "pytest"

    def build_argv(self, **_kwargs: object) -> list[str]:
        return [self._python, str(self._script), "--exit-code", str(self._exit_code)]


class NoopRenderer:
    """Minimal renderer for ``run_plan`` tests."""

    wants_streaming = False
    events: list[Any]

    def __init__(self) -> None:
        self.events = []

    def handle(self, event: object) -> None:
        self.events.append(event)


@pytest.fixture
def engine_scripts_dir() -> Path:
    return SCRIPTS_DIR


@pytest.fixture
def noop_renderer() -> NoopRenderer:
    return NoopRenderer()
