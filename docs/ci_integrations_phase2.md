# Phase 2 CI Integrations

Phase 2 introduces pre-packaged CI wrappers that keep orchestration logic centralized in `uqo_core` and the `uqo run` CLI contract.

## Architecture boundary

- Core execution remains in `uqo_core` and `uqo run`.
- CI wrappers are thin adapters that only prepare inputs and consume stable machine outputs.
- CI provenance is normalized in service/CLI boundaries and persisted through existing repository metadata fields, with no CI-provider logic in repository adapters.

## Canonical CI provenance fields

When running with `--ci`, persisted metadata may include:

- `trigger_source=ci`
- `ci_provider` (`github` or `gitlab`)
- `ci_pipeline_id`
- `ci_job_id`
- `ci_commit_sha`
- `ci_ref_name`

## GitHub Action

Source lives under `integrations/github-action/`.

Minimal consumer usage:

```yaml
- uses: ariel-evn/uqo-action@v1
  with:
    config-path: ./.uqo/config.yaml
```

## GitLab include template

Template lives at `ci/gitlab/uqo.gitlab-ci.yml`.

Minimal consumer include:

```yaml
include:
  - project: "ariel-evn/unified-quality-orchestration-reporting-dashboard"
    file: "/ci/gitlab/uqo.gitlab-ci.yml"

variables:
  UQO_CONFIG_PATH: ".uqo/config.yaml"
```

## Versioning policy for `ariel-evn/uqo-action`

- Publish immutable semver tags (`v1.0.0`, `v1.0.1`, ...).
- Keep moving major tag `v1` pointing to latest stable `v1.x`.
- Recommend SHA pinning for strict supply-chain environments.
