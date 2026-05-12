"""Local HTTP dashboard for a generated Allure HTML tree.

Preferred backend when the Allure CLI is installed:

* ``allure open`` — serves a pre-generated report directory (full SPA).

Fallback:

* :mod:`http.server` — static files only; used when ``allure`` is missing.

Blocking APIs return only after the server process exits (normally Ctrl-C).
"""

from __future__ import annotations

import http.server
import shutil
import signal
import socket
import socketserver
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def open_generated_report(*, report_dir: Path, host: str = "127.0.0.1", port: int = 8080) -> int:
    """Run ``allure open`` on a directory produced by ``allure generate``.

    Inherits the parent stdout/stderr so Allure can print its own URLs.
    Blocks until the Allure process exits (Ctrl-C returns 130).

    Returns:
        Process exit code, or ``130`` after SIGINT, or ``127`` if ``allure`` is missing.
    """
    report_dir = report_dir.expanduser().resolve()
    if not report_dir.is_dir():
        raise FileNotFoundError(f"report directory not found: {report_dir}")
    if shutil.which("allure") is None:
        return 127
    proc = subprocess.Popen(  # noqa: S603 - argv is trusted
        [
            "allure",
            "open",
            str(report_dir),
            "--host",
            host,
            "--port",
            str(port),
        ],
        stdin=subprocess.DEVNULL,
        stdout=None,
        stderr=None,
    )
    try:
        return int(proc.wait())
    except KeyboardInterrupt:
        proc.send_signal(signal.SIGTERM)
        try:
            return int(proc.wait(timeout=5.0))
        except subprocess.TimeoutExpired:
            proc.kill()
            return 130


def serve_report(*, report_dir: Path, port: int = 8080) -> int:
    """Block on a static HTTP server for ``report_dir``.

    Returns the exit code (0 on graceful shutdown).
    """
    report_dir = report_dir.expanduser().resolve()
    if not report_dir.is_dir():
        raise FileNotFoundError(f"report directory not found: {report_dir}")
    if shutil.which("allure") is not None:
        return open_generated_report(report_dir=report_dir, host="127.0.0.1", port=port)
    return _serve_with_stdlib(report_dir=report_dir, port=port)


def _serve_with_stdlib(*, report_dir: Path, port: int) -> int:
    """Fallback: stdlib :class:`http.server.SimpleHTTPRequestHandler`."""

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(report_dir), **kwargs)  # type: ignore[arg-type]

        def log_message(self, format: str, *args: object) -> None:  # noqa: ARG002
            return  # stay quiet — CI logs do not need request lines.

    with socketserver.TCPServer(("127.0.0.1", port), _Handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        print(f"serving {report_dir} at http://127.0.0.1:{port}/  (Ctrl-C to stop)")
        try:
            thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.shutdown()
    return 0


@contextmanager
def background_server(*, report_dir: Path, port: int | None = None) -> Iterator[int]:
    """Run :func:`_serve_with_stdlib` in a background thread (used by tests)."""
    chosen = port or find_free_port()
    httpd = socketserver.TCPServer(
        ("127.0.0.1", chosen),
        lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(report_dir), **kw),  # type: ignore[misc]
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield chosen
    finally:
        httpd.shutdown()
