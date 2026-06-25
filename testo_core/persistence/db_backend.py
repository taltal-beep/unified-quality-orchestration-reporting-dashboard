"""Database persistence backend — upserts a RunRecord via the repository layer."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from testo_core.engine.result import PlanResult
from testo_core.repository.models import RunStatus

logger = logging.getLogger(__name__)


class DbBackend:
    """Persist a :class:`PlanResult` as a :class:`RunRecord` in the database."""

    def persist(self, result: PlanResult) -> None:
        try:
            from testo_core.db import get_repository

            repo = get_repository()
            status = RunStatus.COMPLETED if result.exit_code == 0 else RunStatus.FAILED
            repo.create_run(
                status=status,
                metadata={
                    "plan": result.plan_name,
                    "exit_code": int(result.exit_code),
                    "aggregate_returncode": result.aggregate_returncode,
                    "duration_s": result.duration_s,
                    "started_at": result.started_at,
                    "finished_at": result.finished_at,
                    "started_at_iso": datetime.fromtimestamp(result.started_at, tz=UTC).isoformat(),
                    "stage_count": len(result.stages),
                    "stages": [
                        {
                            "name": s.stage_name,
                            "framework": s.framework,
                            "returncode": s.returncode,
                            "duration_s": s.duration_s,
                        }
                        for s in result.stages
                    ],
                    "source": "engine",
                },
            )
        except Exception:
            logger.debug("db persistence failed for plan %s", result.plan_name, exc_info=True)
