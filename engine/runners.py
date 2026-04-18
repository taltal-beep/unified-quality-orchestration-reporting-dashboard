from __future__ import annotations

import contextlib
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Generator, Mapping, Optional

from .command_builders import BuiltCommand, RunConfig, build_command
from .report_generator import (
    collect_behavex_native_report,
    publish_locust_html_to_static,
    sync_all_reports_to_static,
)
from .result_management import prepare_allure_results_dir

# Emitted immediately before returning ``RunResult`` so the UI can stop polling
# even if the ``RunResult`` object is delayed or dropped.
UQO_DONE_MARKER = "[UQO_DONE]"


def _resolve_subprocess_argv(argv: list[str]) -> None:
    """Ensure the spawned executable is findable when PATH is incomplete (e.g. Streamlit worker)."""
    if not argv:
        return
    base_cmd = argv[0]
    # Leave explicit relative/absolute paths to the OS / subprocess cwd resolution.
    if os.path.dirname(base_cmd):
        return
    resolved_cmd = shutil.which(base_cmd)
    if resolved_cmd:
        argv[0] = resolved_cmd
    else:
        argv[:] = [sys.executable, "-m", base_cmd] + argv[1:]


@dataclass(frozen=True)
class LogEvent:
    ts: float
    stream: str  # "stdout" | "stderr" | "meta"
    line: str


@dataclass(frozen=True)
class RunResult:
    returncode: int
    started_at: float
    finished_at: float
    command: BuiltCommand


def run_streaming(
    cfg: RunConfig,
    *,
    parent_env: Optional[Mapping[str, str]] = None,
    artifacts_root: Path | None = None,
) -> Generator[LogEvent, None, RunResult]:
    """
    Run a test subprocess and yield log lines in real time.

    Uses ``subprocess.Popen`` with line-buffered text mode, merges stderr into stdout
    (single stream) so interleaved output is readable, and reads via a background thread
    into a queue so the generator can still apply heartbeat/timeout logic without
    blocking the Streamlit main thread (when consumed from a worker thread).
    """
    started_at = time.time()

    run_id = str(uuid.uuid4())
    artifacts_root = (artifacts_root or Path("artifacts")).expanduser().resolve()
    shared_allure_dir = (artifacts_root / "allure-results").resolve()
    prepared = prepare_allure_results_dir(shared_allure_dir, mode="archive", run_id=run_id)
    shared_allure_dir = prepared.shared_dir

    merged_extra = dict(cfg.extra_env or {})
    merged_extra.setdefault("UQO_RUN_ID", run_id)

    cfg = replace(
        cfg,
        shared_allure_results_dir=shared_allure_dir,
        artifacts_root=artifacts_root,
        extra_env=merged_extra,
        run_id=run_id,
    )

    cmd = build_command(cfg, parent_env=parent_env or os.environ)

    orchestrator_root = Path(__file__).resolve().parents[1]
    drop_in_root = orchestrator_root / "drop_in_hooks"

    pythonpath_parts = [str(orchestrator_root), str(drop_in_root)]
    existing_pp = cmd.env.get("PYTHONPATH")
    if existing_pp:
        pythonpath_parts.append(existing_pp)
    cmd.env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    if cfg.test_type.value == "behavex":
        site_packages = _current_site_packages()
        if site_packages:
            cmd.env["PYTHONPATH"] = os.pathsep.join([site_packages, cmd.env.get("PYTHONPATH", "")]).strip(os.pathsep)

    if cfg.test_type.value == "pytest":
        existing = cmd.env.get("PYTEST_ADDOPTS", "")
        injection = "-p drop_in_hooks.pytest_custom.conftest"
        if injection not in existing:
            cmd.env["PYTEST_ADDOPTS"] = (existing + " " + injection).strip()
        opts = cmd.env.get("PYTEST_ADDOPTS", "")
        padded = f" {opts} "
        extra = []
        if " -s " not in padded and "--capture=no" not in opts:
            extra.append("-s")
        if "--color=yes" not in opts and "--color=no" not in opts:
            extra.append("--color=yes")
        if extra:
            cmd.env["PYTEST_ADDOPTS"] = (opts + " " + " ".join(extra)).strip()

    cmd.env["PYTHONUNBUFFERED"] = "1"

    q: queue.Queue[LogEvent | None] = queue.Queue()

    def emit(stream: str, line: str) -> None:
        q.put(LogEvent(ts=time.time(), stream=stream, line=line))

    emit("meta", f"$ UQO_RUN_ID={run_id}\n")
    _resolve_subprocess_argv(cmd.argv)
    emit("meta", f"$ (cwd={cmd.cwd}) {' '.join(cmd.argv)}\n")

    proc = subprocess.Popen(
        cmd.argv,
        cwd=str(cmd.cwd),
        env=cmd.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def reader_thread() -> None:
        fh = proc.stdout
        if fh is None:
            return
        try:
            for line in iter(fh.readline, ""):
                emit("stdout", line)
        finally:
            with contextlib.suppress(Exception):
                fh.close()

    t_out = threading.Thread(target=reader_thread, daemon=True)
    t_out.start()

    last_output_ts = time.time()

    while True:
        try:
            item = q.get(timeout=0.1)
            if item is not None:
                last_output_ts = time.time()
                yield item
        except queue.Empty:
            pass

        now = time.time()
        if float(cfg.heartbeat_s) > 0 and (now - last_output_ts) >= float(cfg.heartbeat_s):
            last_output_ts = now
            yield LogEvent(ts=now, stream="meta", line="[still running...]\n")

        if cfg.timeout_s is not None and (now - started_at) >= float(cfg.timeout_s):
            yield LogEvent(ts=now, stream="meta", line=f"[timeout after {cfg.timeout_s}s] terminating...\n")
            with contextlib.suppress(Exception):
                proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except Exception:
                with contextlib.suppress(Exception):
                    proc.kill()
            with contextlib.suppress(Exception):
                proc.wait(timeout=30.0)
            rc = proc.poll()
            finished_at = time.time()
            yield LogEvent(ts=finished_at, stream="meta", line=f"\n[exit code {rc if rc is not None else 124}]\n")
            yield LogEvent(
                ts=time.time(),
                stream="meta",
                line=f"{UQO_DONE_MARKER} returncode={int(rc if rc is not None else 124)}\n",
            )
            yield LogEvent(
                ts=time.time(),
                stream="meta",
                line="[report sync] copying artifacts into ./static/ …\n",
            )
            sync_all_reports_to_static(artifacts_root=artifacts_root, run_id=run_id)
            return RunResult(
                returncode=int(rc if rc is not None else 124),
                started_at=started_at,
                finished_at=finished_at,
                command=cmd,
            )

        rc = proc.poll()
        if rc is not None:
            drain_deadline = time.time() + 2.0
            while time.time() < drain_deadline:
                try:
                    item = q.get_nowait()
                    if item is not None:
                        yield item
                except queue.Empty:
                    break

            t_out.join(timeout=2.0)
            with contextlib.suppress(Exception):
                proc.wait(timeout=30.0)

            finished_at = time.time()
            yield LogEvent(ts=finished_at, stream="meta", line=f"\n[exit code {rc}]\n")
            yield LogEvent(
                ts=time.time(),
                stream="meta",
                line=f"{UQO_DONE_MARKER} returncode={int(rc)}\n",
            )

            if cfg.test_type.value == "behavex":
                try:
                    dest = collect_behavex_native_report(
                        target_repo=cmd.cwd,
                        run_id=run_id,
                        artifacts_root=artifacts_root,
                    )
                    if dest:
                        yield LogEvent(ts=time.time(), stream="meta", line=f"[behavex native report] {dest}\n")
                except Exception:
                    pass

            if cfg.test_type.value == "locust":
                try:
                    lp = publish_locust_html_to_static(artifacts_root=artifacts_root)
                    if lp:
                        yield LogEvent(ts=time.time(), stream="meta", line=f"[locust html mirror] {lp}\n")
                except Exception:
                    pass

            try:
                yield LogEvent(
                    ts=time.time(),
                    stream="meta",
                    line="[report sync] copying artifacts into ./static/ …\n",
                )
                synced = sync_all_reports_to_static(artifacts_root=artifacts_root, run_id=run_id)
                if any(synced.values()):
                    yield LogEvent(
                        ts=time.time(),
                        stream="meta",
                        line=f"[static sync] { {k: str(v) for k, v in synced.items() if v} }\n",
                    )
            except Exception:
                pass

            return RunResult(
                returncode=int(rc),
                started_at=started_at,
                finished_at=finished_at,
                command=cmd,
            )


def _current_site_packages() -> str | None:
    try:
        import site

        for p in site.getsitepackages():
            if p and Path(p).name == "site-packages":
                return str(Path(p).resolve())
    except Exception:
        pass

    for p in sys.path:
        if not p:
            continue
        if "site-packages" in p:
            return str(Path(p).resolve())
    return None


def validate_target_repo(path: Path) -> tuple[bool, str]:
    p = path.expanduser()
    if not p.exists():
        return False, "Path does not exist."
    if not p.is_dir():
        return False, "Path is not a directory."
    return True, "OK"


def default_artifacts_root() -> Path:
    return Path("artifacts")
