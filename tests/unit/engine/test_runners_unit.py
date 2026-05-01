"""Isolated tests for ``engine.runners`` with mocked subprocess / I/O."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from engine.command_builders import BuiltCommand
from engine.runners import (
    UQO_DONE_MARKER,
    _resolve_subprocess_argv,
    _run_in_ephemeral_container_streaming,
    validate_target_repo,
)


@pytest.fixture
def minimal_target_repo(tmp_path: Path) -> Path:
    return tmp_path


def test_resolve_subprocess_uses_shutil_which(monkeypatch: pytest.MonkeyPatch, minimal_target_repo: Path) -> None:
    called: dict[str, str] = {}

    def fake_which(name: str) -> str | None:
        called["which"] = name
        return f"/mock/bin/{name}"

    monkeypatch.setattr("engine.runners.shutil.which", fake_which)
    argv = ["pytest", "-q"]
    _resolve_subprocess_argv(argv)
    assert called.get("which") == "pytest"
    assert argv[0] == "/mock/bin/pytest"


def test_validate_target_repo() -> None:
    assert validate_target_repo(Path("."))[0] is True


def test_uqo_done_marker_constant() -> None:
    assert isinstance(UQO_DONE_MARKER, str) and UQO_DONE_MARKER.startswith("[")


def test_local_subprocess_fallback_streams_output_and_writes_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("engine.runners.docker_client", None)
    events: list[tuple[str, str]] = []

    rc, started_at, finished_at = _run_in_ephemeral_container_streaming(
        run_id="rid-local",
        cmd=BuiltCommand(
            argv=[sys.executable, "-c", "print('local fallback ok')"],
            cwd=tmp_path,
            env={},
        ),
        cfg_timeout_s=5.0,
        cfg_heartbeat_s=0.0,
        emit=lambda stream, line: events.append((stream, line)),
        log_path=tmp_path / "logs" / "run.log",
    )

    assert rc == 0
    assert finished_at >= started_at
    assert ("stdout", "local fallback ok\n") in events
    assert any("docker unavailable" in line for stream, line in events if stream == "meta")
    assert (tmp_path / "logs" / "run.log").read_text(encoding="utf-8") == "local fallback ok\n"


def test_local_subprocess_fallback_times_out_and_emits_124(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("engine.runners.docker_client", None)
    events: list[tuple[str, str]] = []

    rc, _started_at, _finished_at = _run_in_ephemeral_container_streaming(
        run_id="rid-timeout",
        cmd=BuiltCommand(
            argv=[sys.executable, "-c", "import time; time.sleep(10)"],
            cwd=tmp_path,
            env={},
        ),
        cfg_timeout_s=0.2,
        cfg_heartbeat_s=0.0,
        emit=lambda stream, line: events.append((stream, line)),
        log_path=tmp_path / "logs" / "timeout.log",
    )

    assert rc == 124
    assert any("timeout after 0.2s" in line for stream, line in events if stream == "meta")


def test_local_subprocess_fallback_reports_missing_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("engine.runners.docker_client", None)
    monkeypatch.setattr("engine.runners.shutil.which", lambda _name: None)
    monkeypatch.setattr("engine.runners.sys.executable", "/missing/python")
    events: list[tuple[str, str]] = []

    rc, _started_at, _finished_at = _run_in_ephemeral_container_streaming(
        run_id="rid-missing",
        cmd=BuiltCommand(
            argv=["definitely-missing-uqo-command"],
            cwd=tmp_path,
            env={},
        ),
        cfg_timeout_s=5.0,
        cfg_heartbeat_s=0.0,
        emit=lambda stream, line: events.append((stream, line)),
        log_path=tmp_path / "logs" / "missing.log",
    )

    assert rc == 127
    assert any("[subprocess error]" in line for stream, line in events if stream == "meta")
