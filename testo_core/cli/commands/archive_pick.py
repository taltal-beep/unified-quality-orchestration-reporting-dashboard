"""Resolve a baseline/current :class:`ReportArchive` pair for ``summary`` / ``report compare``."""

from __future__ import annotations

from dataclasses import dataclass

from testo_core.repository.models import ReportArchive
from testo_core.services.report_archive_diff import parse_archive_uuid


class ArchivePickError(Exception):
    """Invalid archive selection (caller maps to Typer exit)."""

    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


def _has_archive_id(value: str | None) -> bool:
    return value is not None and str(value).strip() != ""


@dataclass(frozen=True)
class ResolvedArchivePair:
    """Baseline may be ``None`` when an explicit baseline UUID was missing from the DB."""

    baseline: ReportArchive | None
    current: ReportArchive


def resolve_archived_pair(
    repo,  # ReportArchiveRepository protocol
    *,
    baseline_id: str | None,
    current_id: str | None,
    cycle: str | None,
) -> ResolvedArchivePair:
    """Mirror the selection rules previously embedded in ``summary_reports``."""
    has_baseline = _has_archive_id(baseline_id)
    has_current = _has_archive_id(current_id)

    if has_baseline ^ has_current:
        raise ArchivePickError(
            "Provide zero report archive UUIDs or exactly two: use the latest pair, or pass "
            "<baseline_id> <current_id> (ids from ``testo report list``).",
            exit_code=2,
        )

    if not has_baseline:
        cycle_key = cycle.strip() if cycle else None
        rows = repo.list_recent_for_cycle(cycle_name=cycle_key, limit=2) if cycle_key else repo.list_recent(limit=2)
        if len(rows) < 2:
            raise ArchivePickError(
                "Need at least two archived runs in the database.",
                exit_code=2,
            )
        current, baseline = rows[0], rows[1]
        return ResolvedArchivePair(baseline=baseline, current=current)

    if cycle and str(cycle).strip():
        # Caller may print "Ignoring --cycle"; keep resolution pure here.
        pass

    bid = parse_archive_uuid(str(baseline_id))
    cid = parse_archive_uuid(str(current_id))
    if bid is None or cid is None:
        raise ArchivePickError(
            "Each archive id must be a valid UUID (``testo report list`` id column).",
            exit_code=2,
        )
    baseline = repo.get(bid)
    current = repo.get(cid)
    if current is None:
        raise ArchivePickError("Current archive id was not found in the database.", exit_code=2)
    if baseline is None:
        return ResolvedArchivePair(baseline=None, current=current)
    return ResolvedArchivePair(baseline=baseline, current=current)
