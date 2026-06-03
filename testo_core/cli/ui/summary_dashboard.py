"""Rich “dashboard” layout for ``testo summary`` / ``testo diff`` (non ``--metrics-only``)."""

from __future__ import annotations

from collections import defaultdict

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from testo_core.reporting.pyramid_viz import PyramidModel, classify_shape
from testo_core.repository.models import ReportArchive
from testo_core.services.report_archive_diff import ArchiveDiffResult, CaseChange, PerfDeltaRow

_DURATION_SLOW_MS = 100
_BAR_WIDTH = 42


def human_duration_ms(ms: int | None) -> str:
    """Human-readable duration from milliseconds."""

    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms} ms"
    sec_f = ms / 1000.0
    if sec_f < 60.0:
        return f"{sec_f:.1f}s"
    sec_i = int(round(sec_f))
    m, s = divmod(sec_i, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m2 = divmod(m, 60)
    return f"{h}h {m2}m {s:02d}s"


def pass_rate_percent(passed: int | None, total: int | None) -> float | None:
    if passed is None or total is None or total <= 0:
        return None
    return 100.0 * float(passed) / float(total)


def suite_duration_preferred(archive: ReportArchive) -> tuple[int | None, str]:
    """Return (ms, label) preferring Allure per-test sum, else plan wall time."""

    if archive.allure_duration_ms is not None:
        return archive.allure_duration_ms, "Allure Σ (per-test)"
    if archive.plan_duration_ms is not None:
        return archive.plan_duration_ms, "plan wall"
    return None, ""


def format_delta_ms_cell(delta: int | None) -> Text:
    """Color rules for per-test duration delta column."""

    if delta is None:
        return Text("—", style="dim")
    if delta == 0:
        return Text("-", style="dim")
    if delta < 0:
        return Text(f"{delta} ms", style="green")
    if delta > _DURATION_SLOW_MS:
        return Text(f"+{delta} ms", style="red bold")
    return Text(f"+{delta} ms", style="red")


def _pp_delta_text(baseline_pct: float | None, current_pct: float | None) -> Text:
    if baseline_pct is None or current_pct is None:
        return Text("—", style="dim")
    d = current_pct - baseline_pct
    if abs(d) < 0.05:
        return Text("±0.0 pp", style="dim")
    style = "green" if d > 0 else "red" if d < 0 else "dim"
    sign = "+" if d > 0 else ""
    return Text(f"{sign}{d:.1f} pp", style=style)


def _wall_delta_text(b_ms: int | None, c_ms: int | None) -> Text:
    if b_ms is None or c_ms is None:
        return Text("—", style="dim")
    d = c_ms - b_ms
    if d == 0:
        return Text("-", style="dim")
    if d < 0:
        return Text(f"−{human_duration_ms(-d)}", style="green")
    if d > _DURATION_SLOW_MS:
        return Text(f"+{human_duration_ms(d)}", style="red bold")
    return Text(f"+{human_duration_ms(d)}", style="red")


def _stacked_bar_text(
    *,
    passed: int,
    failed: int,
    broken: int,
    skipped: int,
    width: int = _BAR_WIDTH,
    muted: bool = False,
) -> Text:
    total = passed + failed + broken + skipped
    if total <= 0:
        return Text("░" * width, style="dim")

    w_p = (width * passed) // total
    w_f = (width * (failed + broken)) // total
    w_sk = width - w_p - w_f

    ps = "green dim" if muted else "green"
    fs = "red dim" if muted else "red"
    ss = "yellow dim" if muted else "yellow"

    text = Text()
    if w_p:
        text.append("█" * w_p, style=ps)
    if w_f:
        text.append("█" * w_f, style=fs)
    if w_sk:
        text.append("█" * w_sk, style=ss)
    return text


def _truncate_middle(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    if max_len < 5:
        return s[:max_len]
    left = (max_len - 3) // 2
    right = max_len - 3 - left
    return f"{s[:left]}...{s[-right:]}"


def format_test_name_cell(name: str, max_width: int) -> Text:
    """Split parametrized ``[...]`` suffix; dim italic params; middle-truncate when needed."""

    mw = max(8, int(max_width))
    idx = name.rfind("[")
    if idx >= 0 and "]" in name[idx:]:
        base, param = name[:idx], name[idx:]
    else:
        base, param = name, ""

    def fit(b: str, p: str) -> tuple[str, str]:
        if len(b) + len(p) <= mw:
            return b, p
        if p:
            reserve = min(len(p), max(6, mw * 2 // 3))
            b_budget = max(4, mw - reserve)
            b2 = _truncate_middle(b, b_budget) if len(b) > b_budget else b
            p_budget = mw - len(b2)
            p2 = _truncate_middle(p, max(4, p_budget)) if len(p) > p_budget else p
            if len(b2) + len(p2) > mw:
                p2 = _truncate_middle(p, max(4, mw - len(b2)))
            return b2, p2
        return _truncate_middle(b, mw), ""

    base, param = fit(base, param)
    out = Text()
    out.append(base)
    if param:
        out.append(param, style="italic dim")
    return out


def _tier_bar_line(*, label: str, count: int, total: int, bar_width: int, color: str) -> Text:
    row = Text()
    row.append(f"{label:<20}", style="dim")
    if total <= 0:
        row.append(" —", style="dim")
        return row
    pct = 100.0 * float(count) / float(total)
    filled = max(0, min(bar_width, (bar_width * count) // total))
    rest = bar_width - filled
    if filled:
        row.append("█" * filled, style=color)
    if rest:
        row.append("░" * rest, style="dim")
    row.append(f"  {pct:5.1f}%  ({count})", style="default")
    return row


def _counts(archive: ReportArchive) -> tuple[int, int, int, int]:
    p = int(archive.passed or 0)
    f = int(archive.failed or 0)
    br = int(archive.broken or 0)
    sk = int(archive.skipped or 0)
    return p, f, br, sk


def render_metrics_dashboard(
    console: Console,
    *,
    baseline: ReportArchive,
    current: ReportArchive,
) -> None:
    """Header + distribution bars using DB counters (no zip unpack)."""

    b_dur_ms, b_src = suite_duration_preferred(baseline)
    c_dur_ms, c_src = suite_duration_preferred(current)
    b_rate = pass_rate_percent(baseline.passed, baseline.total_tests)
    c_rate = pass_rate_percent(current.passed, current.total_tests)

    bp, bf, bbr, bsk = _counts(baseline)
    cp, cf, cbr, csk = _counts(current)

    score_block = Text.assemble(
        ("Quality score (pass / total)\n", "bold"),
        ("  Baseline ", "dim"),
        (f"{b_rate:.1f}%" if b_rate is not None else "—", "bold" if b_rate is not None else "dim"),
        ("  →  ", "dim"),
        (f"{c_rate:.1f}%" if c_rate is not None else "—", "bold" if c_rate is not None else "dim"),
        ("  Δ ", "dim"),
        _pp_delta_text(b_rate, c_rate),
        "\n",
        ("Total suite duration\n", "bold"),
        ("  Baseline ", "dim"),
        (human_duration_ms(b_dur_ms), "default"),
        (f"  ({b_src})\n" if b_src else "\n", "dim"),
        ("  Current  ", "dim"),
        (human_duration_ms(c_dur_ms), "default"),
        (f"  ({c_src})\n" if c_src else "\n", "dim"),
        ("  Δ ", "dim"),
        _wall_delta_text(b_dur_ms, c_dur_ms),
    )

    spark_w = max(12, _BAR_WIDTH // 3)
    cur_bar_w = min(_BAR_WIDTH, max(28, (console.width or 100) - 36))

    legend = Text.assemble(
        ("█ passed", "green"),
        ("  ", "dim"),
        ("█ failed/broken", "red"),
        ("  ", "dim"),
        ("█ skipped", "yellow"),
    )
    dist = Text.assemble(
        ("Outcome mix (DB totals)\n", "bold"),
        ("  Baseline  ", "dim"),
        _stacked_bar_text(passed=bp, failed=bf, broken=bbr, skipped=bsk, width=spark_w, muted=True),
        "\n",
        ("  Current   ", "dim"),
        _stacked_bar_text(passed=cp, failed=cf, broken=cbr, skipped=csk, width=cur_bar_w),
        "\n",
        legend,
    )

    left = Panel(
        score_block,
        title="[bold]Scores[/]",
        border_style="green",
        padding=(0, 1),
    )
    right = Panel(
        dist,
        title="[bold]Outcome mix[/]",
        border_style="magenta",
        padding=(0, 1),
    )
    body = Columns([left, right], expand=True, equal=True)

    console.print(
        Panel(
            body,
            title="[bold white]Quality trend[/]",
            border_style="cyan",
            padding=(1, 1),
        )
    )


def _make_change_table(
    *,
    name_max_width: int,
    include_group: bool,
) -> Table:
    t = Table(show_header=True, box=box.SIMPLE_HEAD, padding=(0, 1))
    if include_group:
        t.add_column("Group", style="cyan", overflow="ellipsis", max_width=36, no_wrap=True)
    t.add_column("Kind", style="bold", max_width=14, overflow="ellipsis", no_wrap=True)
    t.add_column("Test", overflow="ellipsis", max_width=name_max_width, no_wrap=True)
    t.add_column("Before", style="dim")
    t.add_column("After", style="dim")
    t.add_column("Δms", justify="right")
    return t


def _test_cell(c: CaseChange, name_max_width: int) -> str | Text:
    nt = format_test_name_cell(c.name, name_max_width)
    if c.is_zombie:
        return Text.assemble(("⚡ ", "yellow bold"), nt)
    return nt


def _fill_change_table(
    t: Table,
    rows: list[CaseChange],
    *,
    include_group: bool,
    name_max_width: int,
) -> None:
    for c in rows:
        row: list[object] = []
        if include_group:
            row.append(c.group)
        row.extend(
            [
                c.kind,
                _test_cell(c, name_max_width),
                c.baseline_status or "—",
                c.current_status or "—",
                format_delta_ms_cell(c.duration_delta_ms),
            ]
        )
        t.add_row(*row)


def _group_risk_rank(rows: list[CaseChange]) -> int:
    return min((c.risk_rank for c in rows), default=3)


def render_health_check_matrix(
    console: Console,
    *,
    baseline: ReportArchive,
    current: ReportArchive,
    diff_result: ArchiveDiffResult,
) -> None:
    """Top summary matrix: pass rate, duration, pyramid status, flaky count."""

    b_rate = pass_rate_percent(baseline.passed, baseline.total_tests)
    c_rate = pass_rate_percent(current.passed, current.total_tests)
    b_dur_ms, _ = suite_duration_preferred(baseline)
    c_dur_ms, _ = suite_duration_preferred(current)

    tc = diff_result.tier_counts
    model = PyramidModel(
        unit=int(tc.get("unit", 0)),
        integration=int(tc.get("integration", 0)),
        e2e=int(tc.get("e2e", 0)),
    )
    shape, pyramid_msg = classify_shape(model)
    if shape.value == "healthy":
        p_status = "[green]Healthy[/]"
    elif shape.value == "top_heavy":
        p_status = "[red bold]Top-Heavy[/]"
    elif shape.value == "mid_bulge":
        p_status = "[yellow bold]Mid-Heavy[/]"
    else:
        p_status = "[yellow]Irregular[/]"

    tbl = Table(title="[bold]Quality health check[/]", box=box.ROUNDED, show_header=True, header_style="bold")
    tbl.add_column("Metric", style="dim")
    tbl.add_column("Current", style="default")
    tbl.add_column("Delta vs baseline", justify="right")

    rate_cur = f"{c_rate:.1f}%" if c_rate is not None else "—"
    tbl.add_row("Pass rate", rate_cur, _pp_delta_text(b_rate, c_rate))
    tbl.add_row(
        "Total pipeline speed",
        human_duration_ms(c_dur_ms),
        _wall_delta_text(b_dur_ms, c_dur_ms),
    )
    tbl.add_row("Pyramid balance", Text.from_markup(p_status), Text(pyramid_msg, style="dim"))
    tbl.add_row("Flaky passes (history)", str(diff_result.flaky_pass_count), Text("—", style="dim"))
    console.print(tbl)


def render_pyramid_command_center(
    console: Console,
    *,
    diff_result: ArchiveDiffResult,
    console_width: int,
) -> None:
    """Tier mix as stacked horizontal bars (E2E top, Integration mid, Unit base)."""

    tc = diff_result.tier_counts
    u, i, e = int(tc.get("unit", 0)), int(tc.get("integration", 0)), int(tc.get("e2e", 0))
    unk = int(tc.get("unknown", 0))
    model = PyramidModel(unit=u, integration=i, e2e=e)
    shape, warn_msg = classify_shape(model)

    tiered = u + i + e
    bar_w = max(18, min(36, (console_width or 100) // 2 - 14))

    body = Text()
    if tiered > 0:
        body.append(_tier_bar_line(label="E2E", count=e, total=tiered, bar_width=bar_w, color="dark_orange"))
        body.append("\n")
        body.append(_tier_bar_line(label="Integration / Flow", count=i, total=tiered, bar_width=bar_w, color="blue"))
        body.append("\n")
        body.append(_tier_bar_line(label="Unit", count=u, total=tiered, bar_width=bar_w, color="green"))
    else:
        body.append("(no tier-tagged tests)\n", style="dim")
    if unk:
        body.append("\n")
        body.append(f"{unk} uncategorized", style="dim")

    warn = ""
    if shape.value != "healthy":
        warn = "  [yellow bold]⚠️ " + warn_msg.upper() + "[/]"

    console.print(
        Panel(
            body,
            title="[bold white]Test pyramid (tier mix)[/]" + warn,
            border_style="yellow" if shape.value != "healthy" else "green",
            padding=(1, 1),
        )
    )


def render_wall_of_shame(
    console: Console,
    *,
    rows: list[PerfDeltaRow],
    name_max_width: int,
) -> None:
    if not rows:
        return
    console.print(Rule("[bold red]Top 5 performance regressions (Wall of Shame)[/]", style="red"))
    t = Table(box=box.SIMPLE_HEAD, padding=(0, 1))
    t.add_column("Test", overflow="ellipsis", max_width=name_max_width, no_wrap=True)
    t.add_column("Before", style="dim")
    t.add_column("After", style="dim")
    t.add_column("Δ", justify="right")
    for r in rows:
        dstyle = "red bold" if r.delta_ms > _DURATION_SLOW_MS else "red"
        t.add_row(
            format_test_name_cell(r.name, name_max_width),
            human_duration_ms(r.baseline_duration_ms),
            human_duration_ms(r.current_duration_ms),
            Text(f"+{r.delta_ms} ms", style=dstyle),
        )
    console.print(t)
    console.print("")


def render_deployment_verdict(
    console: Console,
    *,
    baseline: ReportArchive,
    current: ReportArchive,
) -> None:
    """Single go / no-go paragraph from pass rate and duration delta."""

    c_rate = pass_rate_percent(current.passed, current.total_tests)
    fails = int(current.failed or 0) + int(current.broken or 0)
    no_go = fails > 0 or (c_rate is not None and c_rate < 100.0 - 1e-9)

    b_ms, _ = suite_duration_preferred(baseline)
    c_ms, _ = suite_duration_preferred(current)
    perf_bad = (
        not no_go
        and b_ms is not None
        and b_ms > 0
        and c_ms is not None
        and (c_ms - b_ms) / float(b_ms) > 0.20
    )

    if no_go:
        body = "❌ NO-GO: Functional Regressions Detected."
        border = "red"
    elif perf_bad:
        body = "⚠️ CAUTION: Passing, but Severe Performance Degradation."
        border = "yellow"
    else:
        body = "🚀 GO: Pipeline Green and Performant."
        border = "green"

    console.print(Panel(Text.from_markup(body), title="[bold]Deployment readiness[/]", border_style=border))


def _is_regression_risk_row(c: CaseChange) -> bool:
    cs = str(c.current_status or "").lower()
    if c.kind == "regression":
        return True
    if c.kind == "perf_regression":
        return True
    if c.kind == "added" and cs in {"failed", "broken"}:
        return True
    return False


def _is_state_or_improvement_row(c: CaseChange) -> bool:
    cs = str(c.current_status or "").lower()
    if c.kind == "status_change":
        return True
    if c.kind == "added" and cs == "passed":
        return True
    return False


def render_change_sections(
    console: Console,
    *,
    changes: list[CaseChange],
    name_max_width: int = 52,
) -> None:
    """Strict regressions vs state changes; fixes / removed unchanged."""

    risk_rows = sorted(
        (c for c in changes if _is_regression_risk_row(c)),
        key=lambda c: (c.risk_rank, c.group.lower(), c.name.lower()),
    )
    if risk_rows:
        console.print(Rule("[bold]Regressions & risk[/]", style="red"))
        by_g: dict[str, list[CaseChange]] = defaultdict(list)
        for c in risk_rows:
            by_g[c.group].append(c)
        for g in sorted(by_g.keys(), key=lambda gg: (_group_risk_rank(by_g[gg]), gg.lower())):
            console.print(
                f"[bold cyan]{g}[/] [dim]({len(by_g[g])} tests)[/]",
            )
            sub = _make_change_table(
                name_max_width=name_max_width,
                include_group=False,
            )
            _fill_change_table(
                sub,
                sorted(by_g[g], key=lambda x: x.name.lower()),
                include_group=False,
                name_max_width=name_max_width,
            )
            console.print(sub)
            console.print("")

    state_rows = sorted(
        (c for c in changes if _is_state_or_improvement_row(c)),
        key=lambda c: (c.risk_rank, c.group.lower(), c.name.lower()),
    )
    if state_rows:
        console.print(Rule("[bold]State changes & improvements[/]", style="cyan"))
        by_s: dict[str, list[CaseChange]] = defaultdict(list)
        for c in state_rows:
            by_s[c.group].append(c)
        for g in sorted(by_s.keys(), key=lambda gg: (_group_risk_rank(by_s[gg]), gg.lower())):
            console.print(
                f"[bold cyan]{g}[/] [dim]({len(by_s[g])} tests)[/]",
            )
            sub = _make_change_table(
                name_max_width=name_max_width,
                include_group=False,
            )
            _fill_change_table(
                sub,
                sorted(by_s[g], key=lambda x: x.name.lower()),
                include_group=False,
                name_max_width=name_max_width,
            )
            console.print(sub)
            console.print("")

    removed = sorted((c for c in changes if c.kind == "removed"), key=lambda c: c.name.lower())
    if removed:
        console.print(Rule("[bold]Removed cases[/]", style="yellow"))
        t = _make_change_table(name_max_width=name_max_width, include_group=True)
        _fill_change_table(t, removed[:200], include_group=True, name_max_width=name_max_width)
        console.print(t)

    fixes = sorted((c for c in changes if c.kind == "fix"), key=lambda c: c.name.lower())
    if fixes:
        console.print(Rule("[bold]Fixes[/]", style="green"))
        t = _make_change_table(name_max_width=name_max_width, include_group=True)
        _fill_change_table(t, fixes[:200], include_group=True, name_max_width=name_max_width)
        console.print(t)

    if not changes:
        console.print(
            "[dim]No per-test differences detected (or no *-result.json in archives).[/]",
        )


def render_metrics_only_table(console: Console, *, baseline: ReportArchive, current: ReportArchive) -> None:
    """Original flat metrics comparison (``--metrics-only``)."""

    table = Table(title="Run metrics (archive columns)", title_justify="left")
    table.add_column("metric", style="dim")
    table.add_column("baseline", justify="right")
    table.add_column("current", justify="right")
    table.add_column("delta", justify="right")
    pairs: list[tuple[str, int | None, int | None]] = [
        ("total_tests", baseline.total_tests, current.total_tests),
        ("passed", baseline.passed, current.passed),
        ("failed", baseline.failed, current.failed),
        ("broken", baseline.broken, current.broken),
        ("skipped", baseline.skipped, current.skipped),
        ("plan_duration_ms", baseline.plan_duration_ms, current.plan_duration_ms),
        ("allure_duration_ms", baseline.allure_duration_ms, current.allure_duration_ms),
    ]
    for label, bv, cv in pairs:
        d: int | None = None
        if isinstance(bv, int) and isinstance(cv, int):
            d = cv - bv
        table.add_row(
            label,
            "—" if bv is None else str(bv),
            "—" if cv is None else str(cv),
            "—" if d is None else str(d),
        )
    console.print(table)


def render_full_diff(
    console: Console,
    *,
    baseline: ReportArchive,
    current: ReportArchive,
    changes: list[CaseChange],
    metrics_only: bool,
    diff_result: ArchiveDiffResult | None = None,
) -> None:
    """Entry: dashboard + tables, or metrics-only table."""

    if metrics_only:
        render_metrics_only_table(console, baseline=baseline, current=current)
        return

    name_w = max(32, min(72, (console.width or 100) - 46))

    if diff_result is not None:
        render_health_check_matrix(console, baseline=baseline, current=current, diff_result=diff_result)
        render_pyramid_command_center(
            console,
            diff_result=diff_result,
            console_width=int(console.width or 100),
        )

    render_metrics_dashboard(console, baseline=baseline, current=current)

    if diff_result is not None:
        render_wall_of_shame(console, rows=diff_result.top_perf_regressions, name_max_width=name_w)

    render_change_sections(console, changes=changes, name_max_width=name_w)
    render_deployment_verdict(console, baseline=baseline, current=current)
