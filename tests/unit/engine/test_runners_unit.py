"""Isolated tests for ``engine.runners`` with mocked subprocess / I/O."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.command_builders import RunConfig, TestType
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
