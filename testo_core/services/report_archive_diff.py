"""Compare two archived Allure cycles (per-test and aggregate metrics)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testo_core.repository.models import ReportArchive

# Match ``_DURATION_SLOW_MS`` in ``testo_core.cli.ui.summary_dashboard`` for perf risk rows.
PERF_REGRESSION_MS = 100


def _case_key(data: dict[str, Any]) -> str:
    for k in ("historyId", "fullName", "uuid"):
        v = data.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    name = data.get("name")
    return str(name) if name is not None else json.dumps(data, sort_keys=True, default=str)[:200]


def _raw_history_id(data: dict[str, Any]) -> str | None:
    hid = data.get("historyId")
    if hid is None:
        return None
    s = str(hid).strip()
    return s or None


def _case_duration_ms(data: dict[str, Any]) -> int | None:
    start, stop = data.get("start"), data.get("stop")
    if isinstance(start, int) and isinstance(stop, int) and stop >= start:
        return int(stop - start)
    return None


def _label_value(labels: Any, name: str) -> str:
    if not isinstance(labels, list):
        return ""
    for lab in labels:
        if isinstance(lab, dict) and str(lab.get("name")) == name:
            v = lab.get("value")
            return str(v).strip() if v is not None else ""
    return ""


def _path_blob(data: dict[str, Any]) -> str:
    labels = data.get("labels") or []
    parts = [
        _label_value(labels, "package"),
        _label_value(labels, "parentSuite"),
        _label_value(labels, "suite"),
        str(data.get("fullName") or ""),
    ]
    return " ".join(p.lower() for p in parts if p)


def _infer_tier(data: dict[str, Any]) -> str:
    """Map Allure labels / paths to unit | integration | e2e | unknown."""

    labels = data.get("labels") or []
    tag = _label_value(labels, "tag").strip().lower()
    if tag == "unit":
        return "unit"
    if tag == "flow":
        return "integration"
    if tag == "e2e":
        return "e2e"

    blob = _path_blob(data)
    if "tests.e2e" in blob or "tests/e2e" in blob or "tests_e2e" in blob:
        return "e2e"
    if "tests.flow" in blob or "tests/flow" in blob or "tests_flow" in blob:
        return "integration"
    if "tests.unit" in blob or "tests/unit" in blob or "tests_unit" in blob:
        return "unit"

    if "e2e" in blob:
        return "e2e"
    if "flow" in blob or "features" in blob:
        return "integration"

    return "unknown"


def _risk_rank_for_tier(tier: str) -> int:
    if tier == "e2e":
        return 0
    if tier == "integration":
        return 1
    if tier == "unit":
        return 2
    return 3


def _case_group(data: dict[str, Any]) -> str:
    """Stable grouping key (module / suite) for dashboard tables."""

    labels = data.get("labels") or []
    pkg = _label_value(labels, "package")
    if pkg:
        base = pkg[:100]
    else:
        ps, su = _label_value(labels, "parentSuite"), _label_value(labels, "suite")
        if ps and su:
            base = f"{ps} › {su}"[:100]
        elif ps:
            base = ps[:100]
        else:
            base = ""

    if not base:
        tp = data.get("titlePath")
        if isinstance(tp, list) and tp:
            base = ".".join(str(x) for x in tp if str(x).strip())[:100]
    if not base:
        fn = str(data.get("fullName") or data.get("name") or "")
        if "#" in fn:
            base = fn.split("#", 1)[0].strip()[:100]
        elif "::" in fn:
            base = fn.split("::", 1)[0].strip()[:100]
        else:
            parts = fn.rsplit(".", 1)
            if len(parts) == 2 and parts[0] and "." in parts[0]:
                base = parts[0][:100]

    return base if base else "(ungrouped)"


def _failed_history_ids_from_allure_history(plan_root: Path) -> set[str]:
    """historyId values that have any failed/broken entry in ``history/history.json``."""

    bad: set[str] = set()
    for path in plan_root.rglob("history/history.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        for hid, block in payload.items():
            if not isinstance(block, dict):
                continue
            items = block.get("items")
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                st = str(it.get("status") or "").lower()
                if st in {"failed", "broken"}:
                    bad.add(str(hid))
                    break
    return bad


def _failed_history_ids_from_prior_plans(plan_roots: list[Path]) -> set[str]:
    """historyId (or case key) that ever failed/broken in given plan trees."""

    bad: set[str] = set()
    for root in plan_roots:
        cases = _load_cases(root)
        for key, syn in cases.items():
            if str(syn.get("status") or "").lower() in {"failed", "broken"}:
                hid = syn.get("history_id")
                if isinstance(hid, str) and hid.strip():
                    bad.add(hid.strip())
                else:
                    bad.add(key)
    return bad


def _load_cases(plan_root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not plan_root.is_dir():
        return out
    for path in plan_root.rglob("*-result.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        key = _case_key(data)
        st = str(data.get("status") or "unknown").lower()
        tier = _infer_tier(data)
        hid = _raw_history_id(data)
        out[key] = {
            "name": str(data.get("name") or data.get("fullName") or key)[:120],
            "group": _case_group(data),
            "status": st,
            "duration_ms": _case_duration_ms(data),
            "tier": tier,
            "risk_rank": _risk_rank_for_tier(tier),
            "history_id": hid,
        }
    return out


@dataclass(frozen=True)
class PerfDeltaRow:
    key: str
    name: str
    baseline_duration_ms: int
    current_duration_ms: int
    delta_ms: int


@dataclass(frozen=True)
class CaseChange:
    key: str
    name: str
    group: str
    baseline_status: str | None
    current_status: str | None
    kind: str
    duration_delta_ms: int | None
    risk_rank: int = 3
    is_zombie: bool = False


@dataclass
class ArchiveDiffResult:
    """Output of :func:`diff_archives` (changes + command-center aggregates)."""

    changes: list[CaseChange]
    metrics: dict[str, Any]
    tier_counts: dict[str, int]
    top_perf_regressions: list[PerfDeltaRow]
    zombie_history_ids: frozenset[str]
    flaky_pass_count: int


def _case_change_kind(b: dict[str, Any] | None, c: dict[str, Any] | None) -> str:
    """Classify a single test identity pair (same as :func:`diff_archives` logic)."""
    if b is None and c is not None:
        return "added"
    if b is not None and c is None:
        return "removed"
    assert b is not None and c is not None
    bs = b["status"]
    cs = c["status"]
    if bs == cs:
        return "unchanged"
    if bs in {"passed"} and cs in {"failed", "broken"}:
        return "regression"
    if bs in {"failed", "broken"} and cs in {"passed"}:
        return "fix"
    return "status_change"


def classify_case_change(
    baseline: dict[str, Any] | None, current: dict[str, Any] | None
) -> str:
    """Public wrapper for :func:`_case_change_kind` (delta / Allure tooling)."""

    return _case_change_kind(baseline, current)


def allure_case_key(data: dict[str, Any]) -> str:
    """Stable identity for an Allure test result payload (``historyId`` / ``fullName`` / ``uuid``)."""

    return _case_key(data)


def case_synopsis_from_result(data: dict[str, Any]) -> dict[str, Any]:
    """Shape expected by :func:`classify_case_change` for one side of a comparison."""

    key = _case_key(data)
    st = str(data.get("status") or "unknown").lower()
    tier = _infer_tier(data)
    return {
        "name": str(data.get("name") or data.get("fullName") or key)[:120],
        "group": _case_group(data),
        "status": st,
        "duration_ms": _case_duration_ms(data),
        "tier": tier,
        "risk_rank": _risk_rank_for_tier(tier),
        "history_id": _raw_history_id(data),
    }


def load_case_paths_by_key(plan_root: Path) -> dict[str, Path]:
    """Map Allure case key -> path to ``*-result.json`` (last path wins, same as :func:`_load_cases`)."""

    out: dict[str, Path] = {}
    if not plan_root.is_dir():
        return out
    for path in sorted(plan_root.rglob("*-result.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        out[_case_key(data)] = path
    return out


def count_regression_and_fix_between_plans(
    baseline_plan_root: Path,
    current_plan_root: Path,
) -> tuple[int, int]:
    """Count ``regression`` and ``fix`` kinds between two on-disk plan trees (no zip I/O)."""
    base_cases = _load_cases(baseline_plan_root)
    cur_cases = _load_cases(current_plan_root)
    regressions = 0
    fixes = 0
    for key in sorted(set(base_cases) | set(cur_cases)):
        kind = classify_case_change(base_cases.get(key), cur_cases.get(key))
        if kind == "regression":
            regressions += 1
        elif kind == "fix":
            fixes += 1
    return regressions, fixes


def diff_archives(
    *,
    baseline: ReportArchive,
    current: ReportArchive,
    tmp: Path,
    flaky_prior_archives: list[ReportArchive] | None = None,
) -> ArchiveDiffResult:
    """Extract both zips under ``tmp`` and return case-level changes plus aggregates."""

    from testo_core.services.report_archive import extract_archive_to_plan_dir

    extract_archive_to_plan_dir(
        zip_bytes=baseline.artifact_bytes,
        dest_artifacts_root=tmp / "a",
        plan_name=baseline.cycle_name,
    )
    extract_archive_to_plan_dir(
        zip_bytes=current.artifact_bytes,
        dest_artifacts_root=tmp / "b",
        plan_name=current.cycle_name,
    )
    base_root = tmp / "a" / baseline.cycle_name
    cur_root = tmp / "b" / current.cycle_name
    base_cases = _load_cases(base_root)
    cur_cases = _load_cases(cur_root)

    tier_counts: dict[str, int] = {"unit": 0, "integration": 0, "e2e": 0, "unknown": 0}
    for syn in cur_cases.values():
        t = str(syn.get("tier") or "unknown")
        if t not in tier_counts:
            t = "unknown"
        tier_counts[t] = int(tier_counts.get(t, 0)) + 1

    zombie_sources = _failed_history_ids_from_allure_history(cur_root)

    prior_roots: list[Path] = []
    if flaky_prior_archives:
        for idx, arch in enumerate(flaky_prior_archives[:5]):
            sub = tmp / f"flk_{idx}"
            extract_archive_to_plan_dir(
                zip_bytes=arch.artifact_bytes,
                dest_artifacts_root=sub,
                plan_name=arch.cycle_name,
            )
            prior_roots.append(sub / arch.cycle_name)
    zombie_sources |= _failed_history_ids_from_prior_plans(prior_roots)

    flaky_pass_count = 0
    for key, syn in cur_cases.items():
        if str(syn.get("status") or "").lower() != "passed":
            continue
        hid = syn.get("history_id")
        if isinstance(hid, str) and hid.strip() and hid.strip() in zombie_sources:
            flaky_pass_count += 1
        elif key in zombie_sources:
            flaky_pass_count += 1

    changes: list[CaseChange] = []
    perf_candidates: list[PerfDeltaRow] = []
    all_keys = sorted(set(base_cases) | set(cur_cases))
    for key in all_keys:
        b = base_cases.get(key)
        c = cur_cases.get(key)
        bs = b["status"] if b else None
        cs = c["status"] if c else None
        name = (c or b or {}).get("name", key) if (c or b) else key
        group = str((c or b or {}).get("group") or "(ungrouped)")
        bd = (b or {}).get("duration_ms") if b else None
        cd = (c or {}).get("duration_ms") if c else None
        delta = None
        if isinstance(bd, int) and isinstance(cd, int):
            delta = cd - bd

        kind = classify_case_change(b, c)

        risk_src = c or b
        risk_rank = int(risk_src.get("risk_rank", 3)) if risk_src else 3

        hid = (c or b or {}).get("history_id") if (c or b) else None
        hid_s = hid.strip() if isinstance(hid, str) else None
        check_ids = [x for x in (hid_s, key) if x]
        is_zombie = (
            str(cs or "").lower() == "passed"
            and kind in {"status_change", "added"}
            and any(x in zombie_sources for x in check_ids)
        )

        if kind not in {"unchanged"}:
            changes.append(
                CaseChange(
                    key=key[:80],
                    name=str(name)[:120],
                    group=group[:100],
                    baseline_status=bs,
                    current_status=cs,
                    kind=kind,
                    duration_delta_ms=delta,
                    risk_rank=risk_rank,
                    is_zombie=is_zombie,
                )
            )
        elif (
            kind == "unchanged"
            and bs == "passed"
            and cs == "passed"
            and isinstance(delta, int)
            and delta > PERF_REGRESSION_MS
        ):
            changes.append(
                CaseChange(
                    key=key[:80],
                    name=str(name)[:120],
                    group=group[:100],
                    baseline_status=bs,
                    current_status=cs,
                    kind="perf_regression",
                    duration_delta_ms=delta,
                    risk_rank=risk_rank,
                    is_zombie=False,
                )
            )

        if (
            bs == "passed"
            and cs == "passed"
            and isinstance(bd, int)
            and isinstance(cd, int)
            and cd - bd > 0
        ):
            perf_candidates.append(
                PerfDeltaRow(
                    key=key[:80],
                    name=str(name)[:120],
                    baseline_duration_ms=bd,
                    current_duration_ms=cd,
                    delta_ms=cd - bd,
                )
            )

    perf_candidates.sort(key=lambda r: r.delta_ms, reverse=True)
    top_perf = perf_candidates[:5]

    metrics = {
        "baseline_id": str(baseline.id),
        "current_id": str(current.id),
        "baseline_total_tests": baseline.total_tests,
        "current_total_tests": current.total_tests,
        "baseline_passed": baseline.passed,
        "current_passed": current.passed,
        "baseline_failed": baseline.failed,
        "current_failed": current.failed,
        "baseline_plan_duration_ms": baseline.plan_duration_ms,
        "current_plan_duration_ms": current.plan_duration_ms,
    }
    return ArchiveDiffResult(
        changes=changes,
        metrics=metrics,
        tier_counts=tier_counts,
        top_perf_regressions=top_perf,
        zombie_history_ids=frozenset(zombie_sources),
        flaky_pass_count=flaky_pass_count,
    )


def parse_archive_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value).strip())
    except (ValueError, TypeError):
        return None
