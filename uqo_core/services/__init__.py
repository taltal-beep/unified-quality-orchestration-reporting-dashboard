"""Service layer: orchestration and use-cases (framework-agnostic where possible)."""

from .audit_service import AuditService
from .ci_provenance import CIProvenance, detect_ci_environment, detect_ci_provenance
from .config_loader import load_run_specs_from_yaml
from .event_drain import RunLogLine, apply_completed_multi_run, iter_drained_queue_items
from .headless_engine import (
    SCHEMA_VERSION,
    ConfigValidationError,
    EngineEvent,
    EngineExitCode,
    EngineRequest,
    EngineRunSpec,
    EngineSummary,
    HeadlessEngineService,
    InfrastructureRuntimeError,
)
from .metrics_service import MetricsService
from .multi_run import MultiRunState, advance_after_run_result, stream_multi_run
from .ghost_policy import GhostModeResolution, resolve_ghost_mode
from .report_service import ReportService

__all__ = [
    "AuditService",
    "CIProvenance",
    "ConfigValidationError",
    "detect_ci_environment",
    "detect_ci_provenance",
    "EngineEvent",
    "EngineExitCode",
    "EngineRequest",
    "EngineRunSpec",
    "EngineSummary",
    "HeadlessEngineService",
    "InfrastructureRuntimeError",
    "MetricsService",
    "MultiRunState",
    "GhostModeResolution",
    "ReportService",
    "RunLogLine",
    "SCHEMA_VERSION",
    "apply_completed_multi_run",
    "advance_after_run_result",
    "iter_drained_queue_items",
    "load_run_specs_from_yaml",
    "resolve_ghost_mode",
    "stream_multi_run",
]
