# Product Roadmap

<!-- source: notion https://www.notion.so/354d95cd031280ac9d53c6a220d4adc3 -->

Phased delivery narrative for Testo (UQO). Each phase links to operational release gates and code-derived docs.

Completed milestones below use `- [x]` as a delivery record. Open engineering debt lives in [[Technical Debt Tracker]].

## Phase 1: Decoupling & Distribution (Foundation)

Before adding features, the system must install without forcing new infrastructure.

- [x] **Database adapter pattern** — `Repository` interface with SQLite, PostgreSQL, and MySQL adapters so teams point Testo at an existing DB via config. See [[Repository Pattern - Database-Agnostic Refactor]] and [[Architecture Overview]]. Gate: [[Release Checklist - Phase 1 Foundation]].
- [x] **Python package (PyPI)** — `testo_core` via `pyproject.toml`; `pip install testo-core`. See [[uqo-core Library Packaging Plan]]. Gate: [[Release Checklist - Phase 1 Foundation]].
- [x] **Headless CLI** — `testo run` / `uqo run` with JSON/exit codes independent of UI. See [[Command Reference]], [[Deep Dive - Execution Logic]]. Gate: [[Release Checklist - Phase 1 Foundation]].

## Phase 2: Drop-In CI/CD

- [x] **Pre-packaged CI** — GitHub Action + GitLab template (`uses: …/uqo-action@v1`). See [[CI-CD Pipeline Setup]]. Gate: [[Release Checklist - Phase 2 CI Integrations]].
- [x] **Ghost mode** — CI auto-detection, machine-readable stdout, DB/S3 sync. See [[QA Strategies#CI and streaming output]], [[CI-CD Pipeline Setup#Ghost mode (CI execution policy)]]. Gate: [[Release Checklist - Phase 2 Ghost Mode]].
- [x] **Runner image** — Pre-built `uqo-runner` Docker image. Gate: [[Release Checklist - Phase 2 Runner Image]].

## Phase 3: Enterprise UI & Analytics

- [x] **React frontend** — FastAPI backend + React UI; Streamlit rollback. See [[Streamlit to React Migration Guide]], [[Architecture Overview]]. Gate: [[Release Checklist - Phase 3 Frontend Migration]].
- [x] **Delta comparison engine** — Compare two `run_id`s with deterministic classifications. See [[Delta Comparison Policy]], [[Command Reference#`testo diff` / `testo summary`]], [[Phase 3 Delta Comparison Engine Plan]]. Gate: [[Release Checklist - Phase 3 Delta Engine]].
- [x] **Unified dashboard** — Single health overview with drill-down to Allure and other reports. See [[Phase 3 Unified Dashboard Plan]]. Gate: [[Release Checklist - Phase 3 Unified Dashboard]].

## Phase 4: Next-Gen Capabilities

- [x] **BYOK AI** — User-supplied model keys; summarization in engine. See [[Phase 4 BYOK and Failure Analysis]]. Gate: [[Release Checklist - Phase 4 AI and Failure Analysis]].
- [x] **Context-aware failure analysis** — Logs/traces → short human summary on Run Details. See [[Phase 4 BYOK and Failure Analysis#Context-aware failure analysis]]. Gate: [[Release Checklist - Phase 4 AI and Failure Analysis]].

## Historical context

Pre-phase week-by-week infrastructure plan: [[Historical - General Task Forward 2.0]].

---
**Context & Links:** [[Index]], [[UQO Engineering Hub]], [[Release Management/README]], [[Specs & ADRs/README]]
