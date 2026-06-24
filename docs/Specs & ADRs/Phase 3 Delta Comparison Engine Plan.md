# Phase 3 Delta Comparison Engine Plan

<!-- source: notion https://www.notion.so/354d95cd031280249689fa3390e43594 -->

## Strategy (WHY)

QA teams need side-by-side comparison of two runs (reliability + performance) with deterministic regression/improvement labels — especially for load and multi-stage cycles.

## Implementation (HOW — use these as source of truth)

| Layer | Detail |
|-------|--------|
| Metric semantics | [[Delta Comparison Policy]] |
| Core service | `testo_core/services/delta_service.py` |
| CLI | [[Command Reference#`testo diff` / `testo summary`]] |
| API | `GET /api/v1/analytics/delta` |
| React | `frontend/src/features/compare/` |

Do not duplicate the direction table here — it lives in [[Delta Comparison Policy]].

## Release gate

[[Release Checklist - Phase 3 Delta Engine]]

---
**Context & Links:** [[Delta Comparison Policy]], [[Architecture Overview]], [[Product Roadmap#Phase 3: Enterprise UI & Analytics]]
