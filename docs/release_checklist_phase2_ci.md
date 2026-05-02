# Phase-2 Release Checklist (CI Integrations)

This is the go/no-go gate before assigning/re-pointing `v1` for the GitHub action and publishing the GitLab template.

## 1) Core/package integrity

- `python3 -m pip install -U pip`
- `python3 -m pip install -e '.[dev]'`
- `python3 -m build`
- `uqo run --help`

## 2) Core contract suites

- `python3 -m pytest -q --no-cov tests/unit/uqo_core/test_cli_run.py tests/unit/uqo_core/test_headless_engine.py tests/contract/uqo_core/test_cli_contract.py`
- `python3 -m pytest -q --no-cov tests/unit/uqo_core/test_repository_sqlite.py tests/unit/uqo_core/test_repository_factory.py tests/contract/uqo_core/test_repository_contract.py`

## 3) CI integration suites

- `python3 -m pytest -q --no-cov tests/unit/ci/test_github_action_wrapper.py tests/unit/ci/test_gitlab_template_contract.py tests/contract/ci/test_wrapper_contract.py`

## 4) Documentation and adoption checks

- README contains:
  - GitHub Action quickstart
  - GitLab template quickstart
  - required variables/secrets
  - troubleshooting section
- Copy snippets to a scratch project and confirm they require only documented variables.

## 5) Action versioning checks (`ariel-evn/uqo-action`)

- Confirm `action.yml` is at the action repository root.
- Create immutable tag `v1.0.0`.
- Move major tag `v1` to the same commit.
- Re-verify consumer workflow resolves `uses: ariel-evn/uqo-action@v1`.

## 6) Final pass criteria

- All commands above exit with `0`.
- No unversioned changes to `SUMMARY_SCHEMA_KEYS` or NDJSON event types.
- No CI-provider conditionals were added to repository adapters/factory/DB wiring.
