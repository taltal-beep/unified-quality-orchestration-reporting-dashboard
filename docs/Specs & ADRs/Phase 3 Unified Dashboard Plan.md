# Phase 3 Unified Dashboard Plan

<!-- source: notion https://www.notion.so/354d95cd0312807d821bfe7dcbe1c5ba -->

## Strategy (WHY)

Consolidate scattered Allure and framework report links into one health-first overview with drill-down to raw HTML and compare/history flows.

## Implementation (HOW)

| Layer | Detail |
|-------|--------|
| Aggregation | `testo_core/services/dashboard_service.py` |
| API | `GET /api/v1/dashboard/overview` |
| UI | `frontend/src/features/dashboard/DashboardPage.tsx` — primary `/` route |
| Delta semantics | Reuses [[Delta Comparison Policy]] classifications in rollups |

## Release gate

[[Release Checklist - Phase 3 Unified Dashboard]] — run after [[Release Checklist - Phase 3 Frontend Migration]] and [[Release Checklist - Phase 3 Delta Engine]].

---
**Context & Links:** [[Architecture Overview]], [[Streamlit to React Migration Guide]], [[QA Strategies#How results are logged and surfaced]]
