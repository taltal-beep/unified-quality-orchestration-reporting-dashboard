"""Isolated tests for ``engine.runners`` with mocked subprocess / I/O."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from engine import runners
from engine.command_builders import BuiltCommand
from engine.runners import UQO_DONE_MARKER, _resolve_subprocess_argv, validate_target_repo


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


def test_docker_unavailable_fallback_streams_stdout_and_writes_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runners, "docker_client", None)
    log_path = tmp_path / "logs" / "run.log"
    emitted: list[tuple[str, str]] = []
    cmd = BuiltCommand(
        argv=[
            sys.executable,
            "-c",
            "import sys; print('hello fallback'); print('stderr merged', file=sys.stderr)",
        ],
        cwd=tmp_path,
        env={},
    )

    rc, started_at, finished_at = runners._run_in_ephemeral_container_streaming(
        run_id="local-ok",
        cmd=cmd,
        cfg_timeout_s=5.0,
        cfg_heartbeat_s=0.0,
        emit=lambda stream, line: emitted.append((stream, line)),
        log_path=log_path,
    )

    assert rc == 0
    assert finished_at >= started_at
    assert ("stdout", "hello fallback\n") in emitted
    assert ("stdout", "stderr merged\n") in emitted
    assert any("docker unavailable; falling back to local subprocess" in line for _, line in emitted)
    assert set(log_path.read_text(encoding="utf-8").splitlines()) == {"hello fallback", "stderr merged"}


def test_docker_unavailable_fallback_times_out_and_kills_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runners, "docker_client", None)
    log_path = tmp_path / "logs" / "run.log"
    emitted: list[tuple[str, str]] = []
    cmd = BuiltCommand(
        argv=[
            sys.executable,
            "-c",
            "import time; print('started', flush=True); time.sleep(10)",
        ],
        cwd=tmp_path,
        env={},
    )

    rc, _started_at, _finished_at = runners._run_in_ephemeral_container_streaming(
        run_id="local-timeout",
        cmd=cmd,
        cfg_timeout_s=0.2,
        cfg_heartbeat_s=0.0,
        emit=lambda stream, line: emitted.append((stream, line)),
        log_path=log_path,
    )

    assert rc == 124
    assert ("stdout", "started\n") in emitted
    assert any("[timeout after 0.2s] terminating subprocess" in line for _, line in emitted)
