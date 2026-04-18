from __future__ import annotations

import contextlib
import http.server
import os
import shutil
import socket
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ORCHESTRATOR_ROOT / "static"
STATIC_ALLURE_HTML = STATIC_DIR / "allure_report.html"
STATIC_LOCUST_HTML = STATIC_DIR / "locust_report.html"
STATIC_BEHAVE_INDEX = STATIC_DIR / "behave" / "index.html"


@dataclass(frozen=True)
class ReportPaths:
    results_dir: Path
    report_dir: Path
    zip_path: Path


def generate_allure_html(*, results_dir: Path, report_dir: Path) -> tuple[bool, str]:
    """
    Generate Allure HTML by calling the Allure CLI:
      allure generate <results_dir> --clean --single-file -o <report_dir>

    NOTE: Allure CLI is NOT the python package. Install separately:
      - macOS: `brew install allure`
      - Linux (varies): see Allure docs / package manager
    """
    results_dir = results_dir.expanduser().resolve()
    report_dir = report_dir.expanduser().resolve()

    if not results_dir.exists():
        return False, f"Results dir does not exist: {results_dir}"

    report_dir.mkdir(parents=True, exist_ok=True)

    cmd = ["allure", "generate", str(results_dir), "--clean", "--single-file", "-o", str(report_dir)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return False, "Allure CLI not found. Install it (e.g. `brew install allure`)."

    if p.returncode != 0:
        err = (p.stderr or p.stdout or "").strip()
        return False, f"Allure generation failed (exit {p.returncode}). {err[:2000]}"

    return True, f"Allure report generated at {report_dir}"


def read_single_file_html(*, report_dir: Path) -> tuple[bool, str, bytes | None]:
    """
    Read the generated single-file Allure report (index.html).
    """
    report_dir = report_dir.expanduser().resolve()
    index = report_dir / "index.html"
    if not index.exists():
        return False, f"Missing {index}. Generate the report first.", None
    try:
        return True, "OK", index.read_bytes()
    except Exception as exc:
        return False, f"Failed reading {index}: {exc}", None


def make_report_zip(*, report_dir: Path, out_dir: Path, base_name: str = "allure-report") -> Path:
    """
    Create a zip archive of the Allure HTML report directory.
    Returns the full path to the generated zip file.
    """
    report_dir = report_dir.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    zip_base = out_dir / base_name
    zip_path = Path(shutil.make_archive(str(zip_base), "zip", root_dir=str(report_dir)))
    return zip_path


@dataclass
class ReportServer:
    port: int
    root_dir: Path
    thread: threading.Thread
    httpd: http.server.ThreadingHTTPServer

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def stop(self) -> None:
        with contextlib.suppress(Exception):
            self.httpd.shutdown()
        with contextlib.suppress(Exception):
            self.httpd.server_close()


def start_report_server(*, report_dir: Path, port: int | None = None) -> ReportServer:
    """
    Start a local HTTP server rooted at the generated Allure report dir.
    This makes embedded viewing work (relative JS/CSS assets).
    """
    report_dir = report_dir.expanduser().resolve()
    if not report_dir.exists():
        raise FileNotFoundError(report_dir)

    chosen_port = port or _find_free_port()

    handler = _make_handler(report_dir)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", chosen_port), handler)

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    return ReportServer(port=chosen_port, root_dir=report_dir, thread=t, httpd=httpd)


def start_static_server(*, root_dir: Path, port: int | None = None) -> ReportServer:
    """
    Serve a broader directory tree (e.g. orchestrator root), so we can open:
      - artifacts/allure-report/index.html
      - artifacts/reports/locust_report_*.html
      - static_reports/behavex/*.html
    """
    root_dir = root_dir.expanduser().resolve()
    if not root_dir.exists():
        raise FileNotFoundError(root_dir)
    chosen_port = port or _find_free_port()
    handler = _make_handler(root_dir)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", chosen_port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return ReportServer(port=chosen_port, root_dir=root_dir, thread=t, httpd=httpd)


def _ensure_static_dirs() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "behave").mkdir(parents=True, exist_ok=True)


def publish_allure_index_to_static(*, report_dir: Path) -> Path | None:
    """
    Mirror Allure single-file output to static/allure_report.html for Streamlit static serving.
    """
    report_dir = report_dir.expanduser().resolve()
    src = report_dir / "index.html"
    if not src.exists():
        return None
    _ensure_static_dirs()
    shutil.copy2(src, STATIC_ALLURE_HTML)
    return STATIC_ALLURE_HTML


def publish_locust_html_to_static(*, artifacts_root: Path, run_id: str) -> Path | None:
    src = (artifacts_root / "reports" / f"locust_report_{run_id}.html").expanduser().resolve()
    if not src.exists():
        return None
    _ensure_static_dirs()
    shutil.copy2(src, STATIC_LOCUST_HTML)
    return STATIC_LOCUST_HTML


def collect_behavex_native_report(
    *,
    target_repo: Path,
    run_id: str,
    artifacts_root: Path | None = None,
) -> Path | None:
    """
    BehaveX writes report.html at OUTPUT/report.html (see `-o`).

    Primary: <artifacts>/behavex-output/report.html
    Legacy:   <target_repo>/output/report.html

    Copies to static/behave/index.html and to static_reports/behavex/report_<run_id>.html.
    """
    target_repo = target_repo.expanduser().resolve()
    candidates: list[Path] = []
    if artifacts_root is not None:
        ar = artifacts_root.expanduser().resolve()
        candidates.append(ar / "behavex-output" / "report.html")
    candidates.append(target_repo / "output" / "report.html")

    src: Path | None = None
    for c in candidates:
        if c.exists():
            src = c
            break
    if src is None:
        return None

    root = ORCHESTRATOR_ROOT
    _ensure_static_dirs()
    shutil.copy2(src, STATIC_BEHAVE_INDEX)

    dest_dir = (root / "static_reports" / "behavex").resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"report_{run_id}.html"
    shutil.copy2(src, dest)
    return dest


def url_for(server: ReportServer, *, relative_path: str) -> str:
    rp = relative_path.lstrip("/")
    return f"{server.url}{rp}"

def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _make_handler(root_dir: Path):
    # python < 3.13 doesn't support passing directory via partial; do it explicitly
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root_dir), **kwargs)

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            # keep Streamlit logs clean
            return

    return Handler


def default_report_paths(*, artifacts_root: Path) -> ReportPaths:
    artifacts_root = artifacts_root.expanduser().resolve()
    results_dir = artifacts_root / "allure-results"
    report_dir = artifacts_root / "allure-report"
    zip_path = artifacts_root / "allure-report.zip"
    return ReportPaths(results_dir=results_dir, report_dir=report_dir, zip_path=zip_path)

