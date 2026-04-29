## Running the test suite with Allure

### Standard run (stable)

```bash
python scripts/write_allure_environment.py
pytest -q --alluredir=allure-results/pytest
```

### Demo run with intentional flakiness (2–3% red failures)

```bash
python scripts/write_allure_environment.py
UQO_FLAKY_DEMO=1 UQO_FLAKY_RATE=0.025 UQO_FLAKY_SEED=123 pytest -q --alluredir=allure-results/pytest
```

Notes:
- Only tests marked `flaky_demo` are affected by the injected failures.\n+- Integration/E2E/Contract tests automatically attach the last HTTP request/response on failure.\n+- All tests are auto-labeled into Allure `feature/story/title` based on their location under `tests/`.

