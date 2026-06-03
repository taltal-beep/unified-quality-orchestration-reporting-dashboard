"""Bridge module that wires ``testo run`` to the engine.

This is the only CLI-side module that knows the renderer classes.  Engine
internals only see a :class:`testo_core.cli.ui.renderers.Renderer` protocol
instance.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from testo_core.cli.ui.renderers import (
    BufferedRenderer,
    CIRenderer,
    Renderer,
    StreamRenderer,
)
from testo_core.config.errors import ConfigDiscoveryError, ConfigError, PlanNotFoundError
from testo_core.config.loader import discover_and_load
from testo_core.config.resolver import resolve_plan, resolve_stages_for_plan
from testo_core.config.schema import Plan, Stage, TestosteroneConfig
from testo_core.engine.exit_codes import EngineExitCode
from testo_core.triggers import TriggerResult, evaluate_cycle_trigger, persist_trigger_snapshot

_ARCHIVE_JOIN_TIMEOUT_S: float = 30.0


def _normalize_tag_filter(tag: str | None) -> str | None:
    if tag is None or not str(tag).strip():
        return None
    return str(tag).strip().lower()


def _emit_dry_run_plan(
    *,
    console: Console,
    cfg: TestosteroneConfig,
    plan: Plan,
    stages: tuple[Stage, ...],
    ci: bool,
) -> None:
    from rich.table import Table

    from testo_core.frameworks import get_adapter

    root = cfg.defaults.artifacts_root.expanduser().resolve()
    if ci:
        from testo_core.cli.ui.ci_renderer import emit_ndjson

        for idx, st in enumerate(stages, start=1):
            adapter = get_adapter(st.framework)
            stage_root = (root / plan.name / st.name).resolve()
            results_dir = (stage_root / "allure-results" / adapter.results_subdir()).resolve()
            argv = adapter.build_argv(
                target_repo=st.target_repo,
                results_dir=results_dir,
                stage_args=st.args,
                workers=st.workers,
            )
            emit_ndjson(
                {
                    "event": "dry_run_stage",
                    "cycle": plan.name,
                    "index": idx,
                    "stage": st.name,
                    "framework": st.framework,
                    "cwd": str(st.target_repo.expanduser().resolve()),
                    "argv": list(argv),
                }
            )
        return

    table = Table(title=f"Dry run — {plan.name}", show_lines=False)
    table.add_column("#", justify="right", style="muted")
    table.add_column("Stage", style="title")
    table.add_column("Equipment", style="framework")
    table.add_column("cwd", overflow="fold")
    table.add_column("command", overflow="fold")
    for idx, st in enumerate(stages, start=1):
        adapter = get_adapter(st.framework)
        stage_root = (root / plan.name / st.name).resolve()
        results_dir = (stage_root / "allure-results" / adapter.results_subdir()).resolve()
        argv = adapter.build_argv(
            target_repo=st.target_repo,
            results_dir=results_dir,
            stage_args=st.args,
            workers=st.workers,
        )
        cmd = shlex.join(argv)
        cwd = str(st.target_repo.expanduser().resolve())
        table.add_row(str(idx), st.name, st.framework, cwd, cmd)
    console.print(table)
    console.print("[ok]Dry-run complete[/] — no commands were executed.")


def execute_plan_command(
    *,
    console: Console,
    plan_name: str | None,
    config_path: Path | None,
    stream: bool,
    ci: bool,
    persist: bool,
    workers_override: int | None,
    force: bool = False,
    report_db: bool = True,
    async_report_db: bool = False,
    tag: str | None = None,
    fail_fast: bool = False,
    dry_run: bool = False,
    reporter_override: Sequence[str] | None = None,
) -> int:
    """Load + resolve + execute one plan (or every cycle when ``plan_name == 'all'``)."""
    try:
        cfg = discover_and_load(config_path=config_path)
    except (ConfigError, ConfigDiscoveryError) as exc:
        _emit_config_error(console=console, exc=exc, ci=ci)
        return int(EngineExitCode.INVALID_INPUT)

    tag_key = _normalize_tag_filter(tag)

    if plan_name == "all":
        if not cfg.cycles:
            _emit_config_error(
                console=console,
                exc=ConfigError("no cycles defined in configuration."),
                ci=ci,
            )
            return int(EngineExitCode.INVALID_INPUT)
        candidates = sorted(cfg.cycles.keys())
        if tag_key:
            candidates = [n for n in candidates if tag_key in cfg.cycles[n].tags]
        if not candidates:
            _emit_config_error(
                console=console,
                exc=ConfigError(f"No cycles match --tag {tag_key!r}."),
                ci=ci,
            )
            return int(EngineExitCode.INVALID_INPUT)
        worst = 0
        for name in candidates:
            ec = _execute_one_cycle(
                cfg=cfg,
                plan=cfg.cycles[name],
                console=console,
                stream=stream,
                ci=ci,
                persist=persist,
                workers_override=workers_override,
                force=force,
                report_db=report_db,
                async_report_db=async_report_db,
                fail_fast=fail_fast,
                dry_run=dry_run,
                reporter_override=reporter_override,
            )
            worst = max(worst, ec)
            if fail_fast and ec != 0:
                return ec
        return worst

    try:
        plan = resolve_plan(cfg, plan_name=plan_name)
    except PlanNotFoundError as exc:
        _emit_config_error(console=console, exc=exc, ci=ci)
        return int(EngineExitCode.INVALID_INPUT)

    if tag_key and tag_key not in plan.tags:
        _emit_config_error(
            console=console,
            exc=ConfigError(f"cycle {plan.name!r} does not include tag {tag_key!r}."),
            ci=ci,
        )
        return int(EngineExitCode.INVALID_INPUT)

    return _execute_one_cycle(
        cfg=cfg,
        plan=plan,
        console=console,
        stream=stream,
        ci=ci,
        persist=persist,
        workers_override=workers_override,
        force=force,
        report_db=report_db,
        async_report_db=async_report_db,
        fail_fast=fail_fast,
        dry_run=dry_run,
        reporter_override=reporter_override,
    )


def _execute_one_cycle(
    *,
    cfg: TestosteroneConfig,
    plan: Plan,
    console: Console,
    stream: bool,
    ci: bool,
    persist: bool,
    workers_override: int | None,
    force: bool,
    report_db: bool = True,
    async_report_db: bool = False,
    fail_fast: bool = False,
    dry_run: bool = False,
    reporter_override: Sequence[str] | None = None,
) -> int:
    resolved_stages = resolve_stages_for_plan(plan)
    if not resolved_stages:
        _emit_config_error(
            console=console,
            exc=ConfigError(f"plan {plan.name!r} has no stages enabled in this environment."),
            ci=ci,
        )
        return int(EngineExitCode.INVALID_INPUT)

    if dry_run:
        if plan.trigger is not None and not force:
            tr_probe = evaluate_cycle_trigger(plan=plan, cfg=cfg)
            if not tr_probe.stimulus:
                if ci:
                    from testo_core.cli.ui.ci_renderer import emit_ndjson

                    emit_ndjson(
                        {
                            "event": "dry_run",
                            "cycle": plan.name,
                            "status": "skipped",
                            "reason": "trigger",
                        }
                    )
                else:
                    console.print(
                        f"[muted]Dry-run:[/] cycle [bold]{plan.name}[/] would be skipped "
                        f"(no trigger stimulus — {tr_probe.reason})."
                    )
                return int(EngineExitCode.SUCCESS)
        _emit_dry_run_plan(console=console, cfg=cfg, plan=plan, stages=resolved_stages, ci=ci)
        return int(EngineExitCode.SUCCESS)

    tr_result: TriggerResult | None = None
    if plan.trigger is not None and not force:
        tr_result = evaluate_cycle_trigger(plan=plan, cfg=cfg)
        _emit_cycle_trigger_event(ci=ci, plan=plan, tr=tr_result)
        if not tr_result.stimulus:
            _emit_cycle_resting(console=console, ci=ci, plan=plan)
            return int(EngineExitCode.SUCCESS)
        _emit_cycle_activating(console=console, ci=ci, plan=plan, tr=tr_result)
    elif plan.trigger is not None and force and not ci:
        console.print("[muted]Trigger bypassed (--force).[/]")

    renderer = _pick_renderer(console=console, stream=stream, ci=ci)
    effective_plan = _apply_workers_override(plan, resolved_stages, workers_override)

    from testo_core.engine.orchestrator import run_plan

    result = run_plan(
        plan=effective_plan,
        renderer=renderer,
        artifacts_root=cfg.defaults.artifacts_root,
        persist=persist,
        fail_fast=fail_fast,
    )
    exit_int = int(result.exit_code)
    if cfg.reporters or reporter_override:
        from testo_core.reporting.reporters.orchestrate import run_configured_reporters

        run_configured_reporters(
            cfg=cfg,
            artifacts_root=cfg.defaults.artifacts_root,
            plan_name=effective_plan.name,
            reporter_override=reporter_override,
            console=console,
            ci=ci,
            generate_only=True,
        )
    archive_ec = _maybe_archive_cycle_report(
        cfg=cfg,
        plan=effective_plan,
        console=console,
        ci=ci,
        persist=persist,
        report_db=report_db,
        async_report_db=async_report_db,
        plan_exit_code=exit_int,
    )
    exit_int = max(exit_int, archive_ec)
    if (
        tr_result is not None
        and tr_result.persist_snapshot_after_run
        and exit_int == 0
        and cfg.source_path is not None
        and plan.trigger is not None
    ):
        persist_trigger_snapshot(
            cfg=cfg,
            plan_name=plan.name,
            anchor=cfg.source_path.parent.expanduser().resolve(),
            patterns=plan.trigger.paths,
        )
    return exit_int


def _maybe_archive_cycle_report(
    *,
    cfg: TestosteroneConfig,
    plan: Plan,
    console: Console,
    ci: bool,
    persist: bool,
    report_db: bool,
    async_report_db: bool,
    plan_exit_code: int,
) -> int:
    """Archive cycle artifacts to the report DB; return an exit-code bump on failure."""
    if not persist or not report_db:
        return 0

    if ci:
        async_report_db = False

    from testo_core.services.report_archive import try_persist_cycle_report

    artifacts_root = cfg.defaults.artifacts_root
    infra_exit = int(EngineExitCode.INFRA_FAILURE)

    if async_report_db:
        import threading

        archive_result: list[object | None] = [None]

        def _job() -> None:
            archive_result[0] = try_persist_cycle_report(
                artifacts_root=artifacts_root,
                plan_name=plan.name,
                exit_code_override=plan_exit_code,
            )

        thread = threading.Thread(
            target=_job,
            name="testo-report-archive",
            daemon=False,
        )
        thread.start()
        thread.join(timeout=_ARCHIVE_JOIN_TIMEOUT_S)
        if thread.is_alive():
            console.print(
                "[fail]Report database archive did not finish within "
                f"{_ARCHIVE_JOIN_TIMEOUT_S:.0f}s.[/]"
            )
            return infra_exit
        if archive_result[0] is None:
            console.print("[fail]Report database archive failed.[/]")
            return infra_exit
        if not ci:
            console.print(f"[muted]Archived cycle report[/] [bold]{archive_result[0]}[/]")
        return 0

    rid = try_persist_cycle_report(
        artifacts_root=artifacts_root,
        plan_name=plan.name,
        exit_code_override=plan_exit_code,
    )
    if rid is None:
        if not ci:
            console.print("[fail]Report database archive failed.[/]")
        return infra_exit
    if not ci:
        console.print(f"[muted]Archived cycle report[/] [bold]{rid}[/]")
    return 0


def _emit_cycle_trigger_event(*, ci: bool, plan: Plan, tr: TriggerResult) -> None:
    if not ci:
        return
    from testo_core.cli.ui.ci_renderer import emit_ndjson

    emit_ndjson(
        {
            "event": "cycle_trigger",
            "cycle": plan.name,
            "status": "activated" if tr.stimulus else "resting",
            "reason": tr.reason,
            "matched": list(tr.matched_paths),
            "mode": tr.mode,
        }
    )


def _emit_cycle_resting(*, console: Console, ci: bool, plan: Plan) -> None:
    if ci:
        return
    msg = f"Cycle {plan.name} skipped: No stimulus detected in targeted muscle groups."
    console.print(Panel(msg, title="Resting", border_style="dim"))


def _emit_cycle_activating(*, console: Console, ci: bool, plan: Plan, tr: TriggerResult) -> None:
    if ci:
        return
    hint = tr.matched_paths[0] if tr.matched_paths else ""
    if not hint and plan.trigger is not None and plan.trigger.paths:
        hint = plan.trigger.paths[0]
    body = f"[ok]Stimulus detected[/] in [bold]{hint}[/]. [bold]Activating Cycle:[/] {plan.name}."
    console.print(Panel(body, title="Trigger", border_style="green"))


def _pick_renderer(*, console: Console, stream: bool, ci: bool) -> Renderer:
    if ci:
        return CIRenderer()
    if stream:
        return StreamRenderer(console)
    return BufferedRenderer(console)


def _apply_workers_override(plan, stages, workers_override):  # type: ignore[no-untyped-def]
    """Return a new Plan with the workers override applied to every stage."""
    if workers_override is None:
        from testo_core.config.schema import Plan

        return Plan(
            name=plan.name,
            description=plan.description,
            stages=tuple(stages),
            trigger=plan.trigger,
            tags=plan.tags,
        )

    from testo_core.config.schema import Plan, Stage

    new_stages = tuple(
        Stage(
            name=s.name,
            framework=s.framework,
            target_repo=s.target_repo,
            args=s.args,
            workers=int(workers_override),
            timeout_s=s.timeout_s,
            if_expr=None,
            extra_env=s.extra_env,
        )
        for s in stages
    )
    return Plan(
        name=plan.name,
        description=plan.description,
        stages=new_stages,
        trigger=plan.trigger,
        tags=plan.tags,
    )


def _emit_config_error(*, console: Console, exc: Exception, ci: bool) -> None:
    if ci:
        from testo_core.cli.ui.ci_renderer import emit_ndjson

        emit_ndjson({"event": "error", "code": "invalid_input", "message": str(exc)})
    else:
        console.print(f"[fail]error:[/] {exc}")
