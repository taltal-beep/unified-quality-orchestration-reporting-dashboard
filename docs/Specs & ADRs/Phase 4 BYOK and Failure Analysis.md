# Phase 4 BYOK and Failure Analysis

<!-- source: notion https://www.notion.so/354d95cd0312800aafc1e117a94f6fca + https://www.notion.so/354d95cd03128001b96df447ecb59f2a -->

## Strategy (WHY)

- **BYOK:** Users supply their own LLM API keys (OpenAI, Anthropic, etc.) — no bundled provider billing.
- **Failure summaries:** Failed runs should surface a short, actionable explanation on Run Details without reading full logs.

## Architecture

- `testo_core` builds bounded, redacted failure context from artifacts (`failure_context_builder.py`, `failure_analysis_service.py`).
- `testo_api` orchestrates AI calls and settings (`/api/v1/ai/*`, run `ai-summary` endpoints).
- React: settings page + summary card on Run Details.

Security: opt-in default, redaction pipeline, keys never returned on read. See [[Technical Debt Tracker]] for ongoing contract gaps.

## Context-aware failure analysis

On run failure, extract failing Allure cases + log tail → `failure_context_v1` metadata → optional auto-generate summary → display via `GET /api/v1/runs/{run_id}/ai-summary`. Implementation: `testo_core/services/failure_context_builder.py`, `testo_api/execution_manager.py`.

## Release gate

[[Release Checklist - Phase 4 AI and Failure Analysis]]

---
**Context & Links:** [[Architecture Overview]], [[Command Reference]], [[Product Roadmap#Phase 4: Next-Gen Capabilities]]
