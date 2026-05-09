from __future__ import annotations

from typing import Any

import pytest

import uqo_core.services.failure_analysis_service as service_module
from uqo_core.repository.models import RunStatus
from uqo_core.run_history import CompletedRunView
from uqo_core.services.ai import AiGenerationResult, AiProviderError
from uqo_core.services.ai.integration_settings import InMemoryAiSettingsStore
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


def test_generate_summary_persists_provider_result(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Provider:
        def generate(self, request):  # noqa: ANN001,ANN202
            captured["request"] = request
            return AiGenerationResult(
                text="Likely root cause: fixture setup failed.",
                provider="openai",
                model="gpt-4o-mini",
            )

    captured: dict[str, Any] = {}

    def _build_provider(*, config, runtime_api_key):  # noqa: ANN001,ANN202
        captured["runtime_api_key"] = runtime_api_key
        captured["max_input_chars"] = config.max_input_chars
        return _Provider()

    monkeypatch.setattr(service_module, "build_ai_provider", _build_provider)
    store = InMemoryAiSettingsStore()
    store.update(
        enabled=True,
        api_key_source="runtime_input",
        runtime_api_key="runtime-token",
        max_input_chars=500,
        max_output_tokens=123,
    )
    state: dict[str, dict] = {"md": {"error_message": "assertion failed"}}
    service = FailureAnalysisService(
        settings_store=store,
        run_lookup=lambda _: _failed_run(),
        metadata_lookup=lambda _: state["md"],
        metadata_upsert=lambda _, patch: state["md"].update(patch) or True,
    )

    summary = service.generate_summary(run_id="run-1")

    assert summary.status == "available"
    assert summary.summary_text == "Likely root cause: fixture setup failed."
    assert summary.provider == "openai"
    assert summary.model == "gpt-4o-mini"
    assert captured["runtime_api_key"] == "runtime-token"
    assert captured["max_input_chars"] == 500
    assert captured["request"].max_output_tokens == 123
    assert "assertion failed" in captured["request"].prompt
    assert state["md"]["ai_summary_v1"]["status"] == "available"
    assert state["md"]["ai_summary_v1"]["context_stats"]["prompt_chars"] > 0


def test_generate_summary_redacts_provider_error_before_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Provider:
        def generate(self, request):  # noqa: ANN001,ANN202
            raise AiProviderError("provider failed with token=PROVIDERSECRET123456")

    monkeypatch.setattr(service_module, "build_ai_provider", lambda **_: _Provider())
    store = InMemoryAiSettingsStore()
    store.update(enabled=True, api_key_source="runtime_input", runtime_api_key="runtime-token")
    state: dict[str, dict] = {"md": {"error_message": "assertion failed"}}
    service = FailureAnalysisService(
        settings_store=store,
        run_lookup=lambda _: _failed_run(),
        metadata_lookup=lambda _: state["md"],
        metadata_upsert=lambda _, patch: state["md"].update(patch) or True,
    )

    summary = service.generate_summary(run_id="run-1")

    assert summary.status == "no_summary_generated"
    assert summary.error_code == "summary_not_available"
    assert "PROVIDERSECRET123456" not in " ".join(summary.limitations)
    persisted = state["md"]["ai_summary_v1"]
    assert "PROVIDERSECRET123456" not in " ".join(persisted["limitations"])
    assert any("***REDACTED***" in limitation for limitation in persisted["limitations"])
