# Unified Quality Orchestration & Reporting Dashboard — Architecture (Phase 1)

## Goals & Constraints
- **Single Pane of Glass**: one Streamlit UI to configure and run **Pytest**, **BehaveX**, and **Locust**.
- **Zero‑touch integration (CRITICAL)**: orchestrator must work as a **plug‑and‑play wrapper**.
  - No edits required in existing `test_*.py`, feature files, or `locustfile.py`.
  - Provide **drop‑in assets** that can be copied into a target repo root.
  - UI must accept a **target repository path** (absolute or relative).
- **Unified reporting**: all test executions must emit into a single orchestrator‑managed `allure-results/` directory.
- **Air‑gapped readiness**: include offline packaging scripts (wheelhouse) and Allure report generation.

## Repository Layout
This repo is the **Orchestrator Core** plus a **Drop‑In Package** that internal teams can copy into any test repo.

```
.
├── app.py
├── ARCHITECTURE.md
├── requirements.txt
├── engine/
│   ├── __init__.py
│   ├── config.py
│   ├── paths.py
│   ├── command_builders.py
│   ├── runners.py
│   ├── log_stream.py
│   └── result_management.py
├── drop_in_hooks/
│   ├── README.md
│   ├── pytest/
│   │   └── conftest.py
│   ├── behave/
│   │   └── environment.py
│   └── locust/
│       └── locust_hooks.py
├── scripts/
│   ├── package_offline.sh
│   ├── install_offline.sh
│   ├── allure_generate.sh
│   └── run_allure_server.sh
├── artifacts/
│   ├── allure-results/         # shared raw results (managed by orchestrator)
│   └── allure-report/          # generated HTML report output
└── docs/
    ├── INTEGRATION_GUIDE.md
    └── OPERATIONS_AIRGAP.md
```

### Orchestrator Core (this repo)
- **`app.py`**: Streamlit entrypoint. Lets user choose:
  - Target repo path
  - Test type (Pytest / BehaveX / Locust)
  - Options (markers, tags, parallelism, locust users/spawn rate/duration, etc.)
  - Output window streaming stdout/stderr in real time
- **`engine/`**: all non‑UI logic.
  - **Command construction**: build deterministic CLI commands with safe quoting.
  - **Execution**: run tools via `subprocess` from the chosen target directory.
  - **Log streaming**: capture stdout/stderr incrementally (tail‑like UI feed).
  - **Result routing**: ensure a single `artifacts/allure-results/` output directory, per run.

### Drop‑In Package (copy into any target repo)
Located under `drop_in_hooks/` and designed to be **copied into the root of the target repo**.

- **Pytest drop‑in**: `drop_in_hooks/pytest/conftest.py`
  - Forces Allure raw results into the orchestrator’s shared `allure-results` directory.
  - Works without changing existing tests.
  - Uses environment variables set by the orchestrator when it spawns pytest.

- **BehaveX drop‑in**: `drop_in_hooks/behave/environment.py`
  - Behave/BehaveX hook file that routes results to the same shared directory.
  - Again controlled via environment variables from the orchestrator.

- **Locust drop‑in**: `drop_in_hooks/locust/locust_hooks.py`
  - Registers Locust event listeners to capture run metadata/summary and convert/export to an Allure‑friendly artifact in the shared `allure-results` folder.
  - Must not require edits inside `locustfile.py`. Integration pattern: orchestrator sets `PYTHONPATH` (or uses `sitecustomize`) so the hook module is imported automatically.

**Important:** The orchestrator must support two integration modes:
1. **Copy mode (manual)**: internal team copies the drop‑in file(s) into their repo root.
2. **No-copy mode (preferred)**: orchestrator injects hooks via environment:
   - `PYTHONPATH` to point to orchestrator hook modules
   - For pytest, `PYTEST_ADDOPTS` / `-p` plugin loading when feasible
   - For python, optional `PYTHONSTARTUP`/`sitecustomize` strategy for auto-import (documented in `docs/INTEGRATION_GUIDE.md`)

## Unified Reporting Contract
All runners must write to:
- **Raw results**: `./artifacts/allure-results/`
- **Generated report**: `./artifacts/allure-report/`

The orchestrator enforces this by:
- Passing `--alluredir <shared_dir>` for pytest
- Passing equivalent flags/options for BehaveX/Allure formatter
- For Locust: emitting Allure compatible result files into `<shared_dir>` (e.g., custom `*-result.json` + attachments).

Each run should be isolated (recommended):
- Create a run subfolder: `artifacts/allure-results/run_<timestamp>/...`
- Optionally merge into a “latest” view used by the dashboard.

## Execution Model
- Streamlit UI triggers one of the runner paths.
- Runner builds command + env and launches subprocess with:
  - `cwd = target_repo_path`
  - `env` augmented with:
    - `UQO_SHARED_ALLURE_RESULTS_DIR` (absolute path to orchestrator `artifacts/allure-results/...`)
    - Any tool-specific options (e.g., `PYTEST_ADDOPTS`, `BEHAVE_FORMAT`, Locust env vars)
- Logs are streamed to UI while the process runs.
- After completion, `scripts/allure_generate.sh` can generate the report.

## Offline / Air‑Gapped Preparation
- **`scripts/package_offline.sh`** downloads all Python deps into `./wheels/`:
  - `pip download -r requirements.txt -d wheels/`
- **`scripts/install_offline.sh`** installs from local wheels:
  - `pip install --no-index --find-links wheels -r requirements.txt`
- Allure CLI (if used) must also be handled for offline use (documented in `docs/OPERATIONS_AIRGAP.md`).

## Phase 2 Deliverables (after approval)
- Implement `app.py` Streamlit UI skeleton (path selector, test type selector, terminal output).
- Implement `engine/` subprocess runner + log streaming.
- Implement exact drop‑in hook code for pytest/behave/locust and document integration patterns.
- Add offline scripts and minimal docs.
