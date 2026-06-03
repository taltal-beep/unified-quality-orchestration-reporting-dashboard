"""``testo run`` — execute a plan defined in testosterone.yaml.

This module exposes :func:`run` as a plain function so the parent Typer app
can register it under ``app.command(name="run", ...)``.  The Typer decorator
metadata (option names, help text) is attached via :func:`typer.Option`
defaults below.

The body defers every heavy import (engine, frameworks, DB) until after
argument validation so ``testo --help`` stays cheap.
"""

from __future__ import annotations

from pathlib import Path

import typer


def run(
    cycle: str = typer.Option(
        None,
        "--cycle",
        help=(
            "Name of the cycle to execute (from 'cycles:' in testosterone.yaml). "
            "Use 'all' to run every cycle in sorted order (each trigger evaluated separately)."
        ),
    ),
    plan: str = typer.Option(
        None,
        "--plan",
        "-p",
        help="Deprecated alias for --cycle.",
        hidden=True,
    ),
    config: Path = typer.Option(
        None,
        "--config",
        "-c",
        exists=False,
        dir_okay=False,
        readable=True,
        help="Path to a testosterone.yaml file (defaults to discovery).",
    ),
    stream: bool = typer.Option(
        False,
        "--stream",
        help="Tail each stage's stdout live instead of waiting for the post-mortem panel.",
    ),
    ci: bool = typer.Option(
        False,
        "--ci",
        help="Emit NDJSON events on stdout instead of Rich panels (machine-readable).",
    ),
    no_persist: bool = typer.Option(
        False,
        "--no-persist",
        help="Skip writing run records to the optional history database.",
    ),
    no_report_db: bool = typer.Option(
        False,
        "--no-report-db",
        help="Skip archiving cycle artifacts (Allure/JSON) to the report database after the run.",
    ),
    async_report_db: bool = typer.Option(
        False,
        "--async-report-db",
        help="Archive reports in a background thread with a join timeout. "
        "Ignored when --ci is set (archive runs synchronously).",
    ),
    workers: int = typer.Option(
        None,
        "--workers",
        "-w",
        help="Override the default worker count for parallel-aware frameworks (e.g. BehaveX).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Run the cycle even when a trigger would skip it (ignore selective paths).",
    ),
    tag: str | None = typer.Option(
        None,
        "--tag",
        help="When set with ``--cycle all``, run only cycles that list this tag in ``tags:``. "
        "With a single cycle, fail if that cycle does not include the tag.",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Stop after the first failing stage (within a cycle). With ``--cycle all``, also stop after the first failing cycle.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the resolved execution plan (no subprocesses). Respects triggers unless ``--force``.",
    ),
    reporter: str | None = typer.Option(
        None,
        "--reporter",
        help="Comma-separated reporter types (overrides testosterone.yaml reporters).",
    ),
) -> None:
    """Run a plan end-to-end."""
    # Deferred imports so `testo --help` and `testo plans list` stay light.
    from testo_core.cli.ui.console import default_console, make_console
    from testo_core.cli.runner import execute_plan_command

    console = make_console(plain=True) if ci else default_console()
    reporter_override: tuple[str, ...] | None = None
    if reporter:
        reporter_override = tuple(
            t.strip().lower() for t in reporter.split(",") if t.strip()
        )
    exit_code = execute_plan_command(
        console=console,
        plan_name=cycle if cycle is not None else plan,
        config_path=config,
        stream=stream,
        ci=ci,
        persist=not no_persist,
        workers_override=workers,
        force=force,
        report_db=not no_report_db,
        async_report_db=async_report_db,
        tag=tag,
        fail_fast=fail_fast,
        dry_run=dry_run,
        reporter_override=reporter_override,
    )
    if not ci:
        if exit_code == 0:
            console.print("[ok]Run finished successfully.[/]")
        else:
            console.print(f"[fail]Run exited with code {exit_code}.[/]")
    raise typer.Exit(code=int(exit_code))
