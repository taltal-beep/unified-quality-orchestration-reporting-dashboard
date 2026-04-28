# Unified Quality Orchestration (UQO) — Reporting Dashboard

UQO is a **production-oriented test orchestration system** that runs plugin-driven quality checks inside **ephemeral Docker containers**, persists run state to **Postgres**, stores artifacts in **MinIO (S3)**, and renders per-run **Allure Server** reports.

This repo ships a Streamlit UI (`app.py`) for running tests, watching live logs, and browsing run history.

## What you get

- **One UI**: start runs, stream logs, browse history.
- **Resilient lifecycle**:
  - Orchestrator crash → any stuck `RUNNING` run is auto-marked `FAILED` on startup.
  - Runaway plugin (infinite loop) → container is hard-killed on timeout.
- **Production-grade reporting**:
  - Raw results uploaded to MinIO under `projects/<run_id>/results/`
  - Allure Docker Service reads those results and generates `projects/<run_id>/reports/latest`
- **Pluggable execution**: drop in new test plugins without changing the core engine.

---

## Quickstart (copy/paste)

### 1) Clone

```bash
git clone https://github.com/YOUR_ORG/unified-quality-orchestration-reporting-dashboard.git
cd unified-quality-orchestration-reporting-dashboard
```

### 2) Configure env

Create a `.env` file (example below). MinIO credentials are required because artifacts and Allure results are stored in MinIO.

```bash
cat > .env <<'EOF'
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# Optional overrides (defaults shown)
BUCKET_NAME=uqo-artifacts
POSTGRES_USER=uqo_admin
POSTGRES_PASSWORD=admin
POSTGRES_DB=uqo_history

# Safety: hard-stop runaway test containers (seconds)
UQO_CONTAINER_TIMEOUT_S=600

# Used by the UI for the per-run Allure Server link
ALLURE_SERVER_URL=http://localhost:5050
EOF
```

### 3) Start infrastructure (Postgres + MinIO + Allure)

```bash
docker compose up -d
docker compose ps
```

Useful endpoints:
- **Streamlit UI**: `http://localhost:8501` (started below)
- **MinIO Console**: `http://localhost:9001`
- **Allure Server**: `http://localhost:5050`

### 4) Start the UI

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### 5) Execute your first test

Option A (recommended): use **Sandbox mode** in the UI.
- Open Streamlit → `Execution` tab → enable **Load sandbox mode** → click **Run**

Option B: point at your own repo (must be accessible on the same machine running Docker Desktop).
- Open Streamlit → set **Target repository path** → choose **Test type** → click **Run**

### 6) View the Allure report for a completed run

Go to `History` → expand the run → click **Open Allure Server report**.

---

## Architecture (full stack)

### Runtime services (Docker Compose)

- **Streamlit (host process)**: UI and orchestration entrypoint (`app.py`)
- **Postgres** (`uqo-postgres`): canonical run lifecycle storage (`engine/run_history.py`)
- **MinIO** (`uqo-minio`): S3-compatible artifact store
  - Bucket: `BUCKET_NAME` (default `uqo-artifacts`)
  - Raw Allure results: `projects/<run_id>/results/*`
  - HTML snapshots (optional): `runs/<run_id>/artifacts/*`
- **Allure Docker Service** (`uqo-allure`): generates per-run reports by project id
  - Report URL: `ALLURE_SERVER_URL/allure-docker-service/projects/<run_id>/reports/latest/index.html`
- **Allure sync** (`uqo-allure-sync`): mirrors MinIO `projects/` into Allure’s `/app/projects/`
- **Mock API (sandbox)**: local target used for demos (managed by Streamlit via `engine/sandbox_api.py`)

### Execution flow (happy path)

1. UI creates a DB run row in Postgres: `status=RUNNING`
2. Runner starts an ephemeral container via Docker SDK (`engine/runners.py`)
3. Plugin/test framework emits Allure result files
4. On completion:
   - DB row is updated to `COMPLETED` or `FAILED`
   - raw Allure results are uploaded to MinIO under `projects/<run_id>/results/`
5. `uqo-allure-sync` mirrors MinIO → Allure volume; Allure Docker Service updates the report
6. UI shows an **Allure Server** button for the completed run

### Resilience guarantees

- **Crash recovery**: on startup, any DB runs in `RUNNING` are marked `FAILED` with `error_message="Orphaned due to system crash"`.
- **Zombie containers**: containers are killed after `UQO_CONTAINER_TIMEOUT_S` seconds.

---

## Writing a custom test plugin (step-by-step)

UQO uses a simple “drop-in” plugin pattern. Plugins live under `plugins/` and are discovered at runtime.

### 1) Create a new plugin file

Create `plugins/my_plugin.py`:

```python
def uqo_register(registry):
    """
    Called by the orchestrator at startup.
    Register one or more runnable actions (pytest/behavex/locust/custom).
    """
    registry.register(
        name="my_plugin_smoke",
        description="Example: run a fast smoke check",
        test_type="pytest",
        args=["-q", "-m", "smoke"],
    )
```

### 2) Ensure your target repo supports it

Your target repository should include:
- a `requirements.txt` compatible with the chosen framework(s)
- tests (pytest, BehaveX, Behave, Locust), depending on what you register

### 3) Run it from the UI

Start Streamlit, select the plugin/action, and click **Run**. UQO will:
- mount the orchestrator repo into the container
- install requirements inside the container
- execute the requested command
- collect/upload Allure results

### 4) Production tips for plugins

- **Always write Allure results** (for pytest use `--alluredir`; for behave/behavex use the provided Allure formatters).
- **Avoid long-lived processes** unless you truly need them; rely on `UQO_CONTAINER_TIMEOUT_S` as a safety net.
- **Log clearly**: stdout/stderr is streamed into the UI and persisted under `logs/<run_id>.log`.

---

## CI/CD (recommended)

- **Lint + unit tests**: run Python linters/tests on PRs.
- **Docker smoke**: `docker compose up -d` + run a sandbox test + verify:
  - orphan cleanup works (force-kill Streamlit mid-run; restart; run is `FAILED`)
  - timeout works (plugin that sleeps forever; container killed; run is `FAILED`)
  - Allure link works (`/projects/<run_id>/reports/latest/index.html` returns 200)

