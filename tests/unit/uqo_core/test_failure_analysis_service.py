from __future__ import annotations

from typing import Any

from uqo_core.repository.models import RunStatus
from uqo_core.run_history import CompletedRunView
from uqo_core.services.ai import AiGenerationRequest, AiGenerationResult, ProviderTimeoutError
from uqo_core.services.ai.integration_settings import InMemoryAiSettingsStore
from uqo_core.services import failure_analysis_service as failure_analysis_module
from uqo_core.services.failure_analysis_service import FailureAnalysisService


def _failed_run() -> CompletedRunView:
    return CompletedRunView(
        run_id="run-1",
        status=RunStatus.FAILED,
        created_at=1.0,
        started_at=1.0,
        finished_at=2.0,
        test_kind="pytest",
        returncode=1,
        wall_duration_ms=100.0,
        metrics_duration_ms=90,
        total_tests=10,
        passed=8,
        failed=2,
        broken=0,
        skipped=0,
        avg_case_ms=10.0,
        health_pct=80.0,
        target_repo=".",
        snapshot_dir=None,
        audit_json=None,
    )


def test_generate_summary_returns_disabled_fallback() -> None:
    store = InMemoryAiSettingsStore()
    state: dict[str, dict] = {"md": {}}
    service = FailureAnalysisService(
        settings_store=store,
        run_lookup=lambda _: _failed_run(),
        metadata_lookup=lambda _: state["md"],
        metadata_upsert=lambda _, patch: state["md"].update(patch) or True,
    )
    summary = service.generate_summary(run_id="run-1")
    assert summary.status == "no_summary_generated"
    assert summary.error_code == "ai_feature_disabled"


class _SuccessfulProvider:
    provider_name = "openai"
    model = "gpt-4o-mini"

    def __init__(self) -> None:
        self.requests: list[AiGenerationRequest] = []

    def generate(self, request: AiGenerationRequest) -> AiGenerationResult:
        self.requests.append(request)
        return AiGenerationResult(
            text="Likely root cause: an expired token caused the auth tests to fail.",
            provider="openai",
            model=self.model,
        )


class _TimeoutProvider:
    provider_name = "openai"
    model = "gpt-4o-mini"

    def generate(self, request: AiGenerationRequest) -> AiGenerationResult:  # noqa: ARG002
        raise ProviderTimeoutError("provider timed out")


def test_generate_summary_persists_available_provider_result(monkeypatch) -> None:
    provider = _SuccessfulProvider()
    monkeypatch.setattr(failure_analysis_module, "build_ai_provider", lambda **_: provider)
    store = InMemoryAiSettingsStore()
    store.update(
        enabled=True,
        api_key_source="runtime_input",
        runtime_api_key="test-key",
        max_output_tokens=123,
    )
    state: dict[str, dict[str, Any]] = {
        "md": {
            "error_message": "AuthError: token expired",
            "traceback": "Traceback details",
        }
    }
    service = FailureAnalysisService(
        settings_store=store,
        run_lookup=lambda _: _failed_run(),
        metadata_lookup=lambda _: state["md"],
        metadata_upsert=lambda _, patch: state["md"].update(patch) or True,
    )

    summary = service.generate_summary(run_id="run-1")

    assert summary.status == "available"
    assert summary.summary_text == "Likely root cause: an expired token caused the auth tests to fail."
    assert summary.provider == "openai"
    assert summary.model == "gpt-4o-mini"
    assert provider.requests[0].max_output_tokens == 123
    assert "AuthError: token expired" in provider.requests[0].prompt
    persisted = state["md"]["ai_summary_v1"]
    assert persisted["status"] == "available"
    assert persisted["summary_text"] == summary.summary_text
    assert persisted["context_stats"]["prompt_chars"] > 0


def test_generate_summary_persists_provider_timeout_fallback(monkeypatch) -> None:
    monkeypatch.setattr(failure_analysis_module, "build_ai_provider", lambda **_: _TimeoutProvider())
    store = InMemoryAiSettingsStore()
    store.update(enabled=True, api_key_source="runtime_input", runtime_api_key="test-key")
    state: dict[str, dict[str, Any]] = {"md": {"error_message": "upstream timeout"}}
    service = FailureAnalysisService(
        settings_store=store,
        run_lookup=lambda _: _failed_run(),
        metadata_lookup=lambda _: state["md"],
        metadata_upsert=lambda _, patch: state["md"].update(patch) or True,
    )

    summary = service.generate_summary(run_id="run-1")

    assert summary.status == "no_summary_generated"
    assert summary.error_code == "provider_timeout"
    assert summary.summary_text is None
    assert state["md"]["ai_summary_v1"]["error_code"] == "provider_timeout"
