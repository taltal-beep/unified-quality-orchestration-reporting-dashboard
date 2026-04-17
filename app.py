from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Optional

import streamlit as st

from engine.command_builders import RunConfig, TestType, coerce_path
from engine.runners import LogEvent, RunResult, default_artifacts_root, run_streaming, validate_target_repo
from engine.sandbox_api import (
    MOCK_BASE_URL,
    is_managed_process_alive,
    sample_target_repo,
    start_sandbox_if_needed,
    stop_sandbox_if_managed,
)
from engine.metrics import list_run_history, parse_allure_results_dir, push_influxdb, write_metrics_json
from engine.report_generator import default_report_paths, generate_allure_html, make_report_zip, start_report_server


def _init_state() -> None:
    st.session_state.setdefault("running", False)
    st.session_state.setdefault("log_lines", [])
    st.session_state.setdefault("log_max_lines", 2000)
    st.session_state.setdefault("events_q", None)  # type: ignore[assignment]
    st.session_state.setdefault("worker", None)  # type: ignore[assignment]
    st.session_state.setdefault("last_result", None)  # type: ignore[assignment]
    st.session_state.setdefault("sandbox_mode", False)
    st.session_state.setdefault("report_server", None)  # type: ignore[assignment]


def _append_line(line: str) -> None:
    st.session_state.log_lines.append(line)
    max_lines = int(st.session_state.log_max_lines)
    if len(st.session_state.log_lines) > max_lines:
        st.session_state.log_lines = st.session_state.log_lines[-max_lines:]


def _start_worker(cfg: RunConfig) -> None:
    events_q: queue.Queue[LogEvent | RunResult] = queue.Queue()

    def worker() -> None:
        gen = run_streaming(cfg, artifacts_root=default_artifacts_root())
        try:
            while True:
                ev = next(gen)
                events_q.put(ev)
        except StopIteration as e:
            result = e.value
            if result is not None:
                events_q.put(result)

    t = threading.Thread(target=worker, daemon=True)
    st.session_state.events_q = events_q
    st.session_state.worker = t
    st.session_state.running = True
    st.session_state.last_result = None
    t.start()


def _drain_events() -> None:
    q: Optional[queue.Queue] = st.session_state.events_q
    if not q:
        return

    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            break

        if isinstance(item, RunResult):
            st.session_state.last_result = item
            st.session_state.running = False
            continue

        prefix = ""
        if item.stream == "stderr":
            prefix = "[stderr] "
        elif item.stream == "meta":
            prefix = ""
        _append_line(prefix + item.line.rstrip("\n"))


def _on_sandbox_toggle() -> None:
    if not st.session_state.get("sandbox_mode", False):
        stop_sandbox_if_managed()


st.set_page_config(page_title="Unified Quality Orchestration", layout="wide")
_init_state()

st.title("Unified Quality Orchestration & Reporting Dashboard")
st.caption("Streamlit orchestrator — zero-touch wrapper; runs tools via subprocess in the target repo.")

sandbox_path = str(sample_target_repo().resolve())

with st.sidebar:
    st.subheader("Sandbox")

    st.checkbox(
        "🧪 Load Sandbox Mode",
        key="sandbox_mode",
        on_change=_on_sandbox_toggle,
        disabled=bool(st.session_state.running),
    )

    if st.session_state.sandbox_mode:
        st.session_state["target_repo"] = sandbox_path
        ok_api, api_msg = start_sandbox_if_needed()
        if not ok_api:
            st.error(api_msg)
        else:
            st.caption(api_msg)

        st.caption(f"Mock API base: `{MOCK_BASE_URL}`")

        col_stop, _ = st.columns([1, 1])
        with col_stop:
            if st.button("Stop Sandbox API", disabled=bool(st.session_state.running)):
                stop_sandbox_if_managed()
                st.toast("Sandbox API stopped.", icon="🛑")
                st.rerun()

        if is_managed_process_alive():
            st.caption("Orchestrator is managing the uvicorn process for this session.")

    st.subheader("Run configuration")

    target_repo_str = st.text_input(
        "Target repository path",
        value=st.session_state.get("target_repo", "") if not st.session_state.sandbox_mode else sandbox_path,
        placeholder="/abs/path/to/test-repo or ./relative/path",
        disabled=bool(st.session_state.running) or bool(st.session_state.sandbox_mode),
    )
    if st.session_state.sandbox_mode:
        target_repo_str = sandbox_path
        st.session_state["target_repo"] = sandbox_path
    else:
        st.session_state["target_repo"] = target_repo_str

    test_type = st.selectbox(
        "Test type",
        options=[t.value for t in TestType],
        index=0,
        disabled=bool(st.session_state.running),
    )

    # Locust headless controls (used by command builder)
    locust_users = 10
    locust_spawn_rate = 2
    locust_run_time = "1m"
    locust_only_summary = True
    if test_type == TestType.LOCUST.value:
        st.subheader("Locust (headless)")
        locust_users = int(
            st.slider("Users (-u)", min_value=1, max_value=500, value=int(st.session_state.get("locust_users", 10)))
        )
        locust_spawn_rate = int(
            st.slider(
                "Spawn rate (-r)",
                min_value=1,
                max_value=500,
                value=int(st.session_state.get("locust_spawn_rate", 2)),
            )
        )
        locust_run_time = st.text_input(
            "Run time (-t)",
            value=str(st.session_state.get("locust_run_time", "1m")),
            help="Examples: 10s, 1m, 5m",
        )
        locust_only_summary = bool(
            st.checkbox(
                "Only summary",
                value=bool(st.session_state.get("locust_only_summary", True)),
                help="Keeps logs cleaner in headless mode.",
            )
        )
        st.session_state["locust_users"] = locust_users
        st.session_state["locust_spawn_rate"] = locust_spawn_rate
        st.session_state["locust_run_time"] = locust_run_time
        st.session_state["locust_only_summary"] = locust_only_summary

    extra_args = st.text_input(
        "Extra CLI args (space-separated)",
        value=str(st.session_state.get("extra_args", "")),
        placeholder="e.g. -m smoke -q",
        disabled=bool(st.session_state.running),
    )
    st.session_state["extra_args"] = extra_args

    st.number_input(
        "Console buffer (lines)",
        min_value=200,
        max_value=20000,
        value=int(st.session_state.log_max_lines),
        step=200,
        key="log_max_lines",
        disabled=bool(st.session_state.running),
    )

    col_a, col_b = st.columns(2)
    with col_a:
        run_clicked = st.button("Run", type="primary", disabled=bool(st.session_state.running))
    with col_b:
        clear_clicked = st.button("Clear console", disabled=bool(st.session_state.running))

if clear_clicked:
    st.session_state.log_lines = []

target_repo = coerce_path(target_repo_str) if target_repo_str else Path(".")
ok, msg = validate_target_repo(target_repo)
if not ok:
    st.warning(f"Target repo: {msg}")

if run_clicked:
    if not ok:
        st.error(f"Cannot run: {msg}")
    else:
        argv_extra = [a for a in extra_args.split() if a.strip()]
        cfg = RunConfig(
            test_type=TestType(test_type),
            target_repo=target_repo,
            shared_allure_results_dir=Path("artifacts/allure-results"),
            pytest_args=argv_extra if test_type == TestType.PYTEST.value else (),
            behavex_args=argv_extra if test_type == TestType.BEHAVEX.value else (),
            locust_args=argv_extra if test_type == TestType.LOCUST.value else (),
            locust_headless=True,
            locust_users=int(locust_users),
            locust_spawn_rate=int(locust_spawn_rate),
            locust_run_time=str(locust_run_time),
            locust_only_summary=bool(locust_only_summary),
        )
        _append_line(f"Starting run: {cfg.test_type.value} in {cfg.target_repo}")
        _start_worker(cfg)

_drain_events()

col1, col2 = st.columns([2, 1], gap="large")

with col1:
    st.subheader("Live output")
    console_text = "\n".join(st.session_state.log_lines)
    st.code(console_text or "(no output yet)", language="text")

with col2:
    st.subheader("Run status")
    st.write(f"**Running:** {bool(st.session_state.running)}")
    st.write(f"**Artifacts:** `{default_artifacts_root()}`")

    if st.session_state.last_result is not None:
        rr: RunResult = st.session_state.last_result
        st.success(f"Finished with exit code {rr.returncode}")
        st.json(
            {
                "returncode": rr.returncode,
                "duration_s": round(rr.finished_at - rr.started_at, 3),
                "cwd": str(rr.command.cwd),
                "argv": rr.command.argv,
                "allure_results_dir": str(rr.command.env.get("UQO_SHARED_ALLURE_RESULTS_DIR", "")),
            }
        )
    elif st.session_state.running:
        st.info("Process is running. Logs will stream below.")

# -----------------------------
# Analytics & Reporting (Phase 4)
# -----------------------------
st.divider()
st.subheader("📊 Analytics & Reporting")

artifacts_root = default_artifacts_root().expanduser().resolve()
paths = default_report_paths(artifacts_root=artifacts_root)

rep_col1, rep_col2, rep_col3 = st.columns([1, 1, 2], gap="large")

with rep_col1:
    st.markdown("**Allure HTML**")
    st.caption("Requires Allure CLI installed (e.g. `brew install allure`).")

    gen_clicked = st.button("Generate Allure Report", disabled=bool(st.session_state.running))
    if gen_clicked:
        ok_gen, msg_gen = generate_allure_html(results_dir=paths.results_dir, report_dir=paths.report_dir)
        if ok_gen:
            st.success(msg_gen)
        else:
            st.error(msg_gen)

    view_clicked = st.button("View Report (embedded)", disabled=bool(st.session_state.running))
    if view_clicked:
        try:
            # Stop any old server
            srv = st.session_state.get("report_server")
            if srv is not None:
                try:
                    srv.stop()
                except Exception:
                    pass
            st.session_state["report_server"] = start_report_server(report_dir=paths.report_dir)
            st.toast("Report server started.", icon="✅")
        except Exception as exc:
            st.error(f"Unable to start report server: {exc}")

    stop_view_clicked = st.button("Stop Report Viewer", disabled=bool(st.session_state.running))
    if stop_view_clicked:
        srv = st.session_state.get("report_server")
        if srv is not None:
            try:
                srv.stop()
            except Exception:
                pass
        st.session_state["report_server"] = None
        st.toast("Report server stopped.", icon="🛑")

with rep_col2:
    st.markdown("**Export**")
    zip_clicked = st.button("Build ZIP", disabled=bool(st.session_state.running))
    if zip_clicked:
        try:
            zip_path = make_report_zip(report_dir=paths.report_dir, out_dir=artifacts_root, base_name="allure-report")
            st.session_state["report_zip_path"] = str(zip_path)
            st.success(f"ZIP created: {zip_path.name}")
        except Exception as exc:
            st.error(f"ZIP creation failed: {exc}")

    zip_path_str = st.session_state.get("report_zip_path")
    if zip_path_str:
        zp = Path(zip_path_str)
        if zp.exists():
            st.download_button(
                "Download ZIP",
                data=zp.read_bytes(),
                file_name=zp.name,
                mime="application/zip",
            )

    st.markdown("**Metrics (JSON)**")
    metrics_clicked = st.button("Generate metrics.json", disabled=bool(st.session_state.running))
    if metrics_clicked:
        try:
            m = parse_allure_results_dir(paths.results_dir)
            out = write_metrics_json(m, out_path=artifacts_root / "metrics.json")
            st.success(f"Wrote {out}")
        except Exception as exc:
            st.error(f"Metrics generation failed: {exc}")

with rep_col3:
    srv = st.session_state.get("report_server")
    if srv is not None:
        st.markdown("**Report Viewer**")
        st.caption(f"Serving: `{srv.root_dir}`")
        st.components.v1.iframe(srv.url, height=650, scrolling=True)
    else:
        st.markdown("**History**")
        archive_root = artifacts_root / "allure-results-archive"
        history = list_run_history(archive_root=archive_root, current_results_dir=paths.results_dir)
        if history:
            rows = []
            for m in history:
                rate = (m.passed / m.total_tests) if m.total_tests else 0.0
                rows.append(
                    {
                        "timestamp": m.timestamp,
                        "run_id": m.run_id or "",
                        "total": m.total_tests,
                        "passed": m.passed,
                        "failed": m.failed,
                        "broken": m.broken,
                        "skipped": m.skipped,
                        "pass_rate": round(rate * 100.0, 2),
                        "duration_ms": m.duration_ms,
                    }
                )
            st.dataframe(rows, use_container_width=True, height=320)
        else:
            st.info("No Allure results found yet.")

        st.markdown("**Grafana / InfluxDB live sync**")
        influx_url = st.text_input("InfluxDB URL", value=str(st.session_state.get("influx_url", "")))
        influx_org = st.text_input("Org", value=str(st.session_state.get("influx_org", "")))
        influx_bucket = st.text_input("Bucket", value=str(st.session_state.get("influx_bucket", "")))
        influx_token = st.text_input("Token", value=str(st.session_state.get("influx_token", "")), type="password")
        st.session_state["influx_url"] = influx_url
        st.session_state["influx_org"] = influx_org
        st.session_state["influx_bucket"] = influx_bucket
        st.session_state["influx_token"] = influx_token

        push_clicked = st.button("Push latest metrics to InfluxDB", disabled=bool(st.session_state.running))
        if push_clicked:
            if not (influx_url and influx_org and influx_bucket and influx_token):
                st.error("Please fill URL, Org, Bucket, and Token.")
            else:
                latest = parse_allure_results_dir(paths.results_dir)
                ok_push, msg_push = push_influxdb(
                    latest,
                    url=influx_url,
                    token=influx_token,
                    org=influx_org,
                    bucket=influx_bucket,
                )
                if ok_push:
                    st.success(msg_push)
                else:
                    st.error(msg_push)

if st.session_state.running:
    time.sleep(0.2)
    st.rerun()
