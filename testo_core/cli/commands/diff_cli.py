"""``testo diff`` and ``testo summary`` — compare archived report runs."""

from __future__ import annotations

import tempfile
from pathlib import Path

import typer

from testo_core.engine.exit_codes import EngineExitCode


def _has_archive_id(value: str | None) -> bool:
    return value is not None and str(value).strip() != ""


def _render_diff(
    *,
    console,
    baseline,
    current,
    metrics_only: bool,
) -> None:
    from testo_core.cli.ui.summary_dashboard import render_full_diff
    from testo_core.db import get_report_archive_repository
    from testo_core.services.report_archive_diff import diff_archives

    if metrics_only:
        render_full_diff(
            console,
            baseline=baseline,
            current=current,
            changes=[],
            metrics_only=True,
            diff_result=None,
        )
        return

    from testo_core.repository.models import ReportArchive

    repo = get_report_archive_repository()
    seen_ids = {baseline.id, current.id}
    flaky_extras: list[ReportArchive] = []
    for row in repo.list_recent_for_cycle(cycle_name=current.cycle_name, limit=16):
        if row.id in seen_ids:
            continue
        flaky_extras.append(row)
        seen_ids.add(row.id)
        if len(flaky_extras) >= 5:
            break

    with tempfile.TemporaryDirectory(prefix="testo-diff-") as td:
        diff_res = diff_archives(
            baseline=baseline,
            current=current,
            tmp=Path(td),
            flaky_prior_archives=flaky_extras or None,
        )

    render_full_diff(
        console,
        baseline=baseline,
        current=current,
        changes=diff_res.changes,
        metrics_only=False,
        diff_result=diff_res,
    )


def diff_reports(
    baseline_id: str = typer.Argument(
        ...,
        metavar="BASELINE_ID",
        help="Older archived run UUID (``testo report list`` id column).",
    ),
    current_id: str = typer.Argument(
        ...,
        metavar="CURRENT_ID",
        help="Newer archived run UUID.",
    ),
    metrics_only: bool = typer.Option(
        False,
        "--metrics-only",
        help="Show only denormalized DB columns (no per-test Allure diff).",
    ),
) -> None:
    """Compare two ``ReportArchive`` rows (regressions, fixes, duration deltas)."""
    from testo_core.cli.ui.console import default_console
    from testo_core.db import get_report_archive_repository
    from testo_core.services.report_archive_diff import parse_archive_uuid

    console = default_console()
    bid = parse_archive_uuid(baseline_id)
    cid = parse_archive_uuid(current_id)
    if bid is None or cid is None:
        console.print("[fail]Each argument must be a valid report archive UUID.[/]")
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT))

    repo = get_report_archive_repository()
    base = repo.get(bid)
    cur = repo.get(cid)
    if base is None or cur is None:
        console.print("[fail]One or both archive ids were not found in the database.[/]")
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT))

    _render_diff(console=console, baseline=base, current=cur, metrics_only=metrics_only)
    raise typer.Exit(code=0)


def summary_reports(
    baseline_id: str | None = typer.Argument(
        None,
        metavar="[BASELINE_ID]",
        help=(
            "Optional older report archive UUID (``testo report list`` id column). "
            "Omit both UUIDs to compare the two most recent archives (newest vs previous)."
        ),
    ),
    current_id: str | None = typer.Argument(
        None,
        metavar="[CURRENT_ID]",
        help="Optional newer report archive UUID (required when baseline UUID is set).",
    ),
    cycle: str | None = typer.Option(
        None,
        "--cycle",
        help=(
            "When no archive UUIDs are given: use the two most recent rows for this cycle name. "
            "Ignored when two explicit UUIDs are provided."
        ),
    ),
) -> None:
    """Rich terminal diff of two archived runs (use ``testo report compare`` for Allure)."""
    from testo_core.cli.commands.archive_pick import ArchivePickError, resolve_archived_pair
    from testo_core.cli.ui.console import default_console
    from testo_core.db import get_report_archive_repository

    console = default_console()
    repo = get_report_archive_repository()

    if _has_archive_id(baseline_id) and _has_archive_id(current_id) and cycle and str(cycle).strip():
        console.print("[dim]Ignoring ``--cycle`` because explicit archive UUIDs were provided.[/]")

    try:
        pair = resolve_archived_pair(
            repo,
            baseline_id=baseline_id,
            current_id=current_id,
            cycle=cycle,
        )
    except ArchivePickError as exc:
        console.print(f"[fail]{exc.message}[/]")
        raise typer.Exit(code=int(exc.exit_code)) from exc

    baseline, current = pair.baseline, pair.current
    if baseline is None:
        console.print(
            "[dim]Baseline archive not found; no table diff. "
            "Use ``testo report compare`` for an Allure view of the current archive.[/]"
        )
        raise typer.Exit(code=0)

    console.print(f"[muted]Comparing[/] [bold]{baseline.id}[/] (baseline) → [bold]{current.id}[/] (current)")
    _render_diff(console=console, baseline=baseline, current=current, metrics_only=False)
    console.print("[muted]Allure comparison:[/] [bold]testo report compare[/] [dim](same archive arguments).[/]")
    raise typer.Exit(code=0)
