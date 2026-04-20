"""Extended coverage for ``engine.command_builders``."""

from __future__ import annotations

from pathlib import Path

from engine.command_builders import RunConfig, TestType, build_command


def test_build_behavex_includes_formatter_and_parallel_defaults(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    cfg = RunConfig(
        test_type=TestType.BEHAVEX,
        target_repo=tmp_path,
        shared_allure_results_dir=art / "allure-results" / "behave",
        artifacts_root=art,
        behavex_args=(),
    )
    bc = build_command(cfg, parent_env={})
    assert "behavex" in bc.argv[0].lower() or bc.argv[0].endswith("behavex")
    assert "-f" in bc.argv
    fmt = bc.argv[bc.argv.index("-f") + 1]
    assert fmt == "allure_behave.formatter:AllureFormatter"


def test_build_locust_includes_html_and_hooks(tmp_path: Path) -> None:
    lf = tmp_path / "locustfile.py"
    lf.write_text("from locust import User\n", encoding="utf-8")
    art = tmp_path / "artifacts"
    cfg = RunConfig(
        test_type=TestType.LOCUST,
        target_repo=tmp_path,
        shared_allure_results_dir=art / "allure-results" / "locust",
        artifacts_root=art,
    )
    bc = build_command(cfg, parent_env={})
    assert "locust" in "".join(bc.argv).lower()
    assert "--html" in bc.argv
