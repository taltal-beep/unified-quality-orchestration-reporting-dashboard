"""``testo report`` — generate / serve / export a report from the latest run.

The run path emits raw ``allure-results/`` only; HTML rendering is done here.
By default this command writes merged HTML under ``--out`` then runs
``allure open`` so the dashboard is served over HTTP (not ``file://``).
"""

from __future__ import annotations

from pathlib import Path

import typer


def report(
    artifacts_root: Path = typer.Option(
        Path("artifacts"),
        "--artifacts",
        "-a",
        help="Artifacts root that holds the per-stage allure-results.",
    ),
    cycle: str | None = typer.Option(
        None,
        "--cycle",
        help="Restrict the report to one cycle's artifacts (YAML key under cycles:; legacy plans:).",
    ),
    plan: str | None = typer.Option(
        None,
        "--plan",
        "-p",
        help="Deprecated alias for --cycle.",
        hidden=True,
    ),
    generate_only: bool = typer.Option(
        False,
        "--generate-only",
        help="Write HTML to --out only; do not start the local HTTP dashboard.",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Host for the Allure dashboard (after allure generate).",
    ),
    port: int = typer.Option(8080, "--port", help="Port for the Allure dashboard server."),
    out: Path = typer.Option(
        Path("artifacts/report"),
        "--out",
        "-o",
        help="Where to write the generated HTML report.",
    ),
    fmt: str = typer.Option(
        "html",
        "--format",
        "-f",
        help="Output format: html (default), json, or junit.",
    ),
    summary_out: Path = typer.Option(
        None,
        "--summary-out",
        help="When --format=json|junit, file path to write the machine-readable summary to.",
    ),
) -> None:
    """Build a unified Allure report from the latest (or selected) cycle, then open it locally."""
    from testo_core.cli.ui.console import default_console
    from testo_core.reporting.entry import dispatch_report

    resolved = cycle if cycle is not None else plan

    console = default_console()
    exit_code = dispatch_report(
        console=console,
        artifacts_root=artifacts_root,
        plan_name=resolved,
        generate_only=generate_only,
        port=port,
        host=host,
        out_dir=out,
        fmt=fmt,
        summary_out=summary_out,
    )
    raise typer.Exit(code=int(exit_code))
