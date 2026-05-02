from __future__ import annotations

import json
import time
from pathlib import Path

from uqo_core.command_builders import BuiltCommand, TestType
from uqo_core.runners import LogEvent, RunResult
from uqo_core.services.headless_engine import (
    ConfigValidationError,
    EngineEvent,
    EngineRunSpec,
    EngineSummary,
    EngineRunRecord,
)


def _summary(*, exit_code: int = 0) -> EngineSummary:
    return EngineSummary(
        schema_version="1",
        trigger_source="cli",
        ci_mode=True,
        persist=True,
        exit_code=exit_code,
        aggregate_returncode=0 if exit_code == 0 else 1,
        started_at=time.time() - 1.0,
        finished_at=time.time(),
        runs=(
            EngineRunRecord(
                test_type=TestType.PYTEST.value,
                run_id="rid-1",
                returncode=0,
                started_at=time.time() - 1.0,
                finished_at=time.time(),
                duration_s=1.0,
                cwd="/tmp/repo",
            ),
        ),
        error=None,
    )


def test_cli_invalid_config_returns_exit_2(monkeypatch, capsys) -> None:  # noqa: ANN001
    from uqo_core import cli

    def fake_load(_path: Path):  # noqa: ANN001
        raise ConfigValidationError("bad config")

    monkeypatch.setattr(cli, "load_run_specs_from_yaml", fake_load)
    code = cli.main(["run", "--config", "missing.yaml", "--ci"])
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)

    assert code == 2
    assert payload["exit_code"] == 2
    assert "bad config" in payload["error"]


def test_cli_ci_json_summary(monkeypatch, capsys, tmp_path: Path) -> None:  # noqa: ANN001
    from uqo_core import cli

    target = tmp_path / "repo"
    target.mkdir()

    monkeypatch.setattr(
        cli,
        "load_run_specs_from_yaml",
        lambda _path: (EngineRunSpec(test_type=TestType.PYTEST, target_repo=target),),
    )

    class FakeEngine:
        def stream(self, request):  # noqa: ANN001
            del request
            if False:
                yield
            return _summary(exit_code=0)

    monkeypatch.setattr(cli, "HeadlessEngineService", FakeEngine)
    code = cli.main(["run", "--config", "ok.yaml", "--ci", "--json"])
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)

    assert code == 0
    assert payload["exit_code"] == 0
    assert payload["trigger_source"] == "cli"


def test_cli_stream_json_outputs_ndjson(monkeypatch, capsys, tmp_path: Path) -> None:  # noqa: ANN001
    from uqo_core import cli

    target = tmp_path / "repo"
    target.mkdir()

    monkeypatch.setattr(
        cli,
        "load_run_specs_from_yaml",
        lambda _path: (EngineRunSpec(test_type=TestType.PYTEST, target_repo=target),),
    )

    cmd = BuiltCommand(
        argv=["pytest", "-q"],
        cwd=target,
        env={"UQO_RUN_ID": "rid-1", "UQO_LAST_TEST_TYPE": "pytest"},
    )
    rr = RunResult(returncode=0, started_at=time.time() - 1, finished_at=time.time(), command=cmd)

    class FakeEngine:
        def stream(self, request):  # noqa: ANN001
            del request
            yield EngineEvent(kind="log", payload=LogEvent(ts=time.time(), stream="stdout", line="line\n"))
            yield EngineEvent(kind="run_result", payload=rr)
            return _summary(exit_code=0)

    monkeypatch.setattr(cli, "HeadlessEngineService", FakeEngine)
    code = cli.main(["run", "--config", "ok.yaml", "--ci", "--stream-json"])
    out_lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]

    assert code == 0
    assert len(out_lines) == 3
    first = json.loads(out_lines[0])
    last = json.loads(out_lines[-1])
    assert first["event"] == "log"
    assert last["exit_code"] == 0
