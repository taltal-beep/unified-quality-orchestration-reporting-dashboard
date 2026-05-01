"""Service layer: orchestration and use-cases (framework-agnostic where possible)."""

from .audit_service import AuditService
from .event_drain import RunLogLine, iter_drained_queue_items
from .metrics_service import MetricsService
from .multi_run import MultiRunState, advance_after_run_result, stream_multi_run
from .report_service import ReportService

__all__ = [
    "AuditService",
    "MetricsService",
    "MultiRunState",
    "ReportService",
    "RunLogLine",
    "advance_after_run_result",
    "iter_drained_queue_items",
    "stream_multi_run",
]
