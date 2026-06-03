"""Local HTTP dashboard for a generated Allure HTML tree.

Preferred backend when the Allure 3 CLI is installed:

* ``allure open`` — generates (if needed) and serves result or report directories.

Fallback:

* :mod:`http.server` — static files only; used when ``allure`` is missing or a custom host is required.
"""

from __future__ import annotations

import http.server
import socket
import socketserver
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from testo_core.reporting.allure_cli import is_allure_available, run_open_blocking


def find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def resolve_serve_port(host: str, preferred: int) -> int:
    """Return ``preferred`` if it can be bound on ``host``, else an ephemeral free port."""
    if preferred == 0:
        return find_free_port(host=host)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, int(preferred)))
        return int(preferred)
    except OSError:
        return find_free_port(host=host)


def open_generated_report(*, report_dir: Path, host: str = "127.0.0.1", port: int = 8080) -> int:
    """Run ``allure open`` on a report or results directory.

    Allure 3 binds locally; when ``host`` is not loopback, fall back to stdlib static serve.
    """
    report_dir = report_dir.expanduser().resolve()
    if not report_dir.is_dir():
        raise FileNotFoundError(f"report directory not found: {report_dir}")

    chosen = resolve_serve_port(host, port)
    if host not in ("127.0.0.1", "localhost", "::1") or not is_allure_available():
        if not report_dir.is_dir():
            return 127
        return _serve_with_stdlib(report_dir=report_dir, port=chosen)

    return run_open_blocking(paths=[report_dir], port=chosen)


def serve_report(*, report_dir: Path, port: int = 8080) -> int:
    """Block on a static HTTP server for ``report_dir``."""
    report_dir = report_dir.expanduser().resolve()
    if not report_dir.is_dir():
        raise FileNotFoundError(f"report directory not found: {report_dir}")
    chosen = resolve_serve_port("127.0.0.1", port)
    if is_allure_available():
        return open_generated_report(report_dir=report_dir, host="127.0.0.1", port=chosen)
    return _serve_with_stdlib(report_dir=report_dir, port=chosen)


def _serve_with_stdlib(*, report_dir: Path, port: int) -> int:
    """Fallback: stdlib :class:`http.server.SimpleHTTPRequestHandler`."""

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(report_dir), **kwargs)  # type: ignore[arg-type]

        def log_message(self, format: str, *args: object) -> None:  # noqa: ARG002
            return

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
