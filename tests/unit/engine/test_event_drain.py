"""Tests for ``engine.services.event_drain``."""

from __future__ import annotations

import queue
from pathlib import Path

from engine.command_builders import BuiltCommand
from engine.runners import LogEvent, RunResult
from engine.services.event_drain import RunLogLine, iter_drained_queue_items


def _minimal_run_result() -> RunResult:
    cmd = BuiltCommand(argv=["x"], cwd=Path("."), env={})
    return RunResult(returncode=0, started_at=0.0, finished_at=1.0, command=cmd)


def test_iter_drained_queue_items_yields_run_result_and_logs() -> None:
    q: queue.Queue[object] = queue.Queue()
    rr = _minimal_run_result()
    q.put(LogEvent(ts=0.0, stream="meta", line="hello\n"))
    q.put(rr)

    out = list(iter_drained_queue_items(q))
    assert len(out) == 2
    assert isinstance(out[0], RunLogLine)
    assert out[0].line == "hello\n"
    assert out[1] is rr


def test_iter_drained_skips_unknown() -> None:
    q: queue.Queue[object] = queue.Queue()
    q.put(42)
    assert list(iter_drained_queue_items(q)) == []
