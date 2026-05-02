from __future__ import annotations

from uqo_core.services.ci_provenance import CIProvenance, detect_ci_provenance


def test_detect_ci_provenance_github() -> None:
    pv = detect_ci_provenance(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123",
            "GITHUB_JOB": "test",
            "GITHUB_SHA": "abc123",
            "GITHUB_REF_NAME": "main",
        }
    )
    assert pv == CIProvenance(
        ci_provider="github",
        ci_pipeline_id="123",
        ci_job_id="test",
        ci_commit_sha="abc123",
        ci_ref_name="main",
    )


def test_detect_ci_provenance_gitlab() -> None:
    pv = detect_ci_provenance(
        {
            "GITLAB_CI": "true",
            "CI_PIPELINE_ID": "42",
            "CI_JOB_ID": "99",
            "CI_COMMIT_SHA": "def456",
            "CI_COMMIT_REF_NAME": "release",
        }
    )
    assert pv == CIProvenance(
        ci_provider="gitlab",
        ci_pipeline_id="42",
        ci_job_id="99",
        ci_commit_sha="def456",
        ci_ref_name="release",
    )


def test_detect_ci_provenance_none_when_unknown_environment() -> None:
    assert detect_ci_provenance({"CI": "true"}) is None


def test_to_metadata_omits_missing_optional_fields() -> None:
    payload = CIProvenance(ci_provider="github", ci_pipeline_id="123").to_metadata()
    assert payload == {"ci_provider": "github", "ci_pipeline_id": "123"}
