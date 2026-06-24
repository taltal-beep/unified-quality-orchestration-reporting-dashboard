# Phase 3 Release Checklist (Delta Comparison Engine)

This checklist gates the merge of Phase 3 delta analytics across core, API, and React.

Check off each item before merging the phase gate.

## 1) Packaging and install baseline

- [ ] `python3 -m pip install -U pip`
- [ ] `python3 -m pip install -e '.[dev]'`
- [ ] `python3 -m build`

## 2) Core delta analytics tests

- [ ] `python3 -m pytest -q --no-cov tests/unit/testo_core/test_delta_service.py`
- [ ] `python3 -m pytest -q --no-cov tests/unit/testo_core/test_run_history_unit.py`

## 3) API contract and regression gate

- [ ] `python3 -m pytest -q --no-cov tests/contract/api/test_analytics_contract.py`
- [ ] `python3 -m pytest -q --no-cov tests/contract/api/test_runs_contract.py tests/contract/api/test_history_contract.py`

## 4) CLI/CI contract guard

- [ ] `python3 -m pytest -q --no-cov tests/contract/testo_core/test_cli_contract.py tests/contract/testo_core/test_ghost_summary_contract.py tests/contract/testo_core/test_ghost_ndjson_contract.py`

## 5) Frontend gate

- [ ] `npm --prefix frontend ci`
- [ ] `npm --prefix frontend run test`
- [ ] `npm --prefix frontend run test:e2e`

## 6) Policy and docs gate

Confirm these documents are updated and internally consistent:

- [ ] `docs/Release Management/Delta Comparison Policy.md`
- [ ] `README.md`
- [ ] `ARCHITECTURE.md`
- [ ] `docs/Release Management/Release Checklist - Phase 3 Delta Engine.md`

## 7) Go/No-Go criteria

- [ ] **Go**:
  - [ ] All commands exit with `0`.
  - [ ] Existing `/api/v1/runs*` endpoints remain backward-compatible.
  - [ ] `GET /api/v1/analytics/delta` returns typed metrics and status-summary payload.
  - [ ] React compare page shows loading/error/empty/success states with clear labels.
- [ ] **No-Go**:
  - [ ] Any regression in existing API or CLI/CI contract suites.
  - [ ] Any mismatch between implementation and `docs/Release Management/Delta Comparison Policy.md`.
---
**Context & Links:**
- [[Delta Comparison Policy]], [[Command Reference#`testo diff` / `testo summary`]], [[Architecture Overview]], [[Phase 3 Delta Comparison Engine Plan]]
- Previous: [[Release Checklist - Phase 3 Frontend Migration]] · Next: [[Release Checklist - Phase 3 Unified Dashboard]]
