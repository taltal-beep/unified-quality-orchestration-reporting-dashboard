from __future__ import annotations

from pathlib import Path

from uqo_api.execution_manager import ExecutionState, ExecutionManager
from uqo_api.models import CreateExecutionRequest, RunSpecRequest
from uqo_core.command_builders import BuiltCommand
from uqo_core.runners import RunResult
from uqo_core.services.headless_engine import EngineEvent, EngineSummary


def test_execution_manager_emits_failed_run_id_for_ai_summary_lookup() -> None:
    manager = ExecutionManager()
    state = ExecutionState(execution_id="exec-1")
    req = CreateExecutionRequest(
        runs=[RunSpecRequest(test_type="pytest", target_repo=".")],
        persist=True,
        trigger_source="ui",
        ci_mode=False,
    )
    run_result = RunResult(
        returncode=1,
        started_at=1.0,
        finished_at=2.0,
        command=BuiltCommand(
            argv=["pytest"],
            cwd=Path("."),
            env={"UQO_RUN_ID": "run-1", "UQO_LAST_TEST_TYPE": "pytest"},
        ),
    )

    def _stream(_request):  # noqa: ANN001, ANN202
        yield EngineEvent(kind="run_result", payload=run_result)
        return EngineSummary(
            schema_version="1",
            trigger_source="ui",
            ci_mode=False,
            persist=True,
            exit_code=1,
            aggregate_returncode=1,
            started_at=1.0,
            finished_at=2.0,
            runs=(),
            error=None,
            execution_mode="headless",
            failure_type="test_failure",
            sync={"status": "success", "runs": []},
        )

    manager._engine.stream = _stream  # type: ignore[assignment]
    manager._run_execution(state, req)

    assert state.status == "failed"
    assert state.done is True
    assert state.event_history[0] == {
        "event": "run_result",
        "data": {
            "run_id": "run-1",
            "test_type": "pytest",
            "returncode": 1,
            "started_at": 1.0,
            "finished_at": 2.0,
            "cwd": ".",
        },
    }
