"""Machine-readable exporters: JSON summary + JUnit XML.

Both consume the NDJSON events written by the orchestrator under
``<artifacts>/<plan>/events.ndjson`` and the per-stage Allure result trees
located by :mod:`testo_core.reporting.collector`.

JUnit XML is intentionally minimal — enough for Jenkins / GitLab CI native
test reporters to recognise the pass/fail split.  Allure HTML stays the
authoritative human report.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from testo_core.reporting.allure_results import StageSummary, parse_collected_results
from testo_core.reporting.collector import CollectedResults


def write_json_summary(*, results: CollectedResults, out: Path) -> Path:
    """Aggregate per-stage Allure results into one JSON summary file."""
    summaries = _summarise(results)
    aggregate = {
        "schema_version": "1",
        "artifacts_root": str(results.artifacts_root),
        "stages": [asdict(s) for s in summaries],
        "total": _sum(summaries, "total"),
        "passed": _sum(summaries, "passed"),
        "failed": _sum(summaries, "failed"),
        "broken": _sum(summaries, "broken"),
        "skipped": _sum(summaries, "skipped"),
    }
    out = out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(aggregate, indent=2, sort_keys=True), encoding="utf-8")
    return out


def write_junit_xml(*, results: CollectedResults, out: Path) -> Path:
    """Emit a JUnit XML file aggregated from per-stage Allure JSON files."""
    summaries = _summarise(results)
    out = out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    suites: list[str] = []
    for s in summaries:
        name = escape(f"{s.plan}.{s.stage}")
        seconds = s.duration_ms / 1000.0
        suites.append(
            f'  <testsuite name="{name}" tests="{s.total}" '
            f'failures="{s.failed}" errors="{s.broken}" skipped="{s.skipped}" '
            f'time="{seconds:.3f}" />'
        )
    body = "\n".join(suites) if suites else ""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuites name="testo" tests="{_sum(summaries, "total")}" '
        f'failures="{_sum(summaries, "failed")}" errors="{_sum(summaries, "broken")}" '
        f'skipped="{_sum(summaries, "skipped")}">\n'
        f"{body}\n"
        "</testsuites>\n"
    )
    out.write_text(xml, encoding="utf-8")
    return out


def _summarise(results: CollectedResults) -> list[StageSummary]:
    return list(parse_collected_results(results).stages)


def _sum(items: list[StageSummary], field: str) -> int:
    return sum(int(getattr(s, field)) for s in items)


# Keep the regex around for potential reuse by tests that inspect the XML.
_SUITE_OPEN = re.compile(r"<testsuite ")
