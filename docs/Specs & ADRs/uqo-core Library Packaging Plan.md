# uqo-core Library Packaging Plan

<!-- source: notion https://www.notion.so/354d95cd03128078a597ed4c30c273bb -->

## Decision (WHY)

Expose orchestration as an installable library (`testo-core` on PyPI, import `testo_core`) so CI, custom scripts, and adapters share one engine — not a monolithic app checkout.

## Current implementation (HOW)

| Item | Location |
|------|----------|
| Package metadata | `pyproject.toml` — `name = "testo-core"` |
| Public API | `testo_core/__init__.py` |
| CLI entry | `testo` / `uqo` console scripts |
| Dev install | `pip install -e '.[dev]'` |

Streamlit (`testo_ui`) and FastAPI (`testo_api`) are **optional consumers** — they must not be required for `testo run`. See [[Architecture Overview#Adjacent packages (same repo)]].

## Operator commands

See [[Command Reference]], [[Troubleshooting and Error Codes]]. Release gate: [[Release Checklist - Phase 1 Foundation]].

---
**Context & Links:** [[Architecture Overview]], [[Command Reference]], [[Product Roadmap#Phase 1: Decoupling & Distribution (Foundation)]]
