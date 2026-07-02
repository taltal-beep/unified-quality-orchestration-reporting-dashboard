from __future__ import annotations

from typer.testing import CliRunner

from testo_core.cli.app import app

runner = CliRunner()


def test_shell_completion_enabled() -> None:
    assert app._add_completion is True


def test_help_exposes_completion_options() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--install-completion" in result.output
    assert "--show-completion" in result.output
