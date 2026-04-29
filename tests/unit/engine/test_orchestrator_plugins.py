from __future__ import annotations

from pathlib import Path

import pluggy
import pytest

import engine.orchestrator as orch
from engine.specs import BaseRunnerSpec


pytestmark = [pytest.mark.unit]


def test_load_plugins_registers_python_files(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    (plugins_root / "_ignored.py").write_text("x=1\n", encoding="utf-8")
    (plugins_root / "p1.py").write_text("def get_command(config):\n    return None\n", encoding="utf-8")

    monkeypatch.setattr(orch, "_plugins_root", lambda: plugins_root)

    pm = pluggy.PluginManager("uqo")
    pm.add_hookspecs(BaseRunnerSpec)

    orch.load_plugins(pm)
    out = capsys.readouterr().out
    assert "registered p1" in out


def test_create_plugin_manager_without_dropins(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure `load_plugins` not invoked.
    monkeypatch.setattr(orch, "load_plugins", lambda _pm: (_ for _ in ()).throw(AssertionError("should not load")))  # type: ignore[misc]
    pm = orch.create_plugin_manager(load_dropins=False)
    assert isinstance(pm, pluggy.PluginManager)

