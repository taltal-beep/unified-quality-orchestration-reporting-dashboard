"""Isolated tests for ``engine.runners`` with mocked subprocess / I/O."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.command_builders import RunConfig, TestType
from engine.runners import UQO_DONE_MARKER, run_streaming, validate_target_repo


@pytest.fixture
def minimal_target_repo(tmp_path: Path) -> Path:
    return tmp_path


def test_resolve_subprocess_uses_shutil_which(monkeypatch: pytest.MonkeyPatch, minimal_target_repo: Path) -> None:
    called: dict[str, str] = {}

    def fake_which(name: str) -> str | None:
        called["which"] = name
        return f"/mock/bin/{name}"

    monkeypatch.setattr("engine.runners.shutil.which", fake_which)

    cfg = RunConfig(
        test_type=TestType.PYTEST,
        target_repo=minimal_target_repo,
        shared_allure_results_dir=minimal_target_repo / "allure",
        pytest_args=("-q",),
    )

    class _Stdout:
        _lines = ["one line of output\n"]

        def readline(self) -> str:
            return self._lines.pop(0) if self._lines else ""

    with patch("engine.runners.subprocess.Popen") as popen:
        proc = MagicMock()
        proc.stdout = _Stdout()
        proc.poll.side_effect = [None, 0]
        proc.wait.return_value = 0
        popen.return_value = proc

        events: list[object] = []
        gen = run_streaming(cfg, prepare_allure=False, emit_done_marker=False, sync_static=False)
        for item in gen:
            events.append(item)

    assert called.get("which") == "pytest"
    assert events


def test_validate_target_repo() -> None:
    assert validate_target_repo(Path("."))[0] is True


def test_uqo_done_marker_constant() -> None:
    assert isinstance(UQO_DONE_MARKER, str) and UQO_DONE_MARKER.startswith("[")
