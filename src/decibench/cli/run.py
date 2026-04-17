"""decibench run — the primary command. Run test scenarios against a voice agent."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from decibench.config import load_config
from decibench.orchestrator import Orchestrator
from decibench.reporters.ci_reporter import CIReporter
from decibench.reporters.json_reporter import JSONReporter
from decibench.reporters.markdown_reporter import MarkdownReporter
from decibench.reporters.rich_reporter import RichReporter
from decibench.store import RunStore, default_store_path


@click.command("run")
@click.option(
    "--target", "-t",
    default=None,
    help="Target agent URI (ws://, exec:, http://, demo). Default: from config.",
)
@click.option(
    "--suite", "-s",
    default="quick",
    help="Test suite to run (quick, standard, full).",
)
@click.option(
    "--scenario",
    default=None,
    help="Run a single scenario by ID (e.g., quick-greeting-001).",
)
@click.option(
    "--config", "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to decibench.toml.",
)
@click.option(
    "--profile", "-p",
    default=None,
    help="Config profile to use (dev, ci, benchmark).",
)
@click.option(
    "--noise",
    default=None,
    help="Comma-separated noise levels (clean,cafe,street).",
)
@click.option(
    "--accents",
    default=None,
    help="Comma-separated accent codes (en-US,en-IN,en-GB).",
)
@click.option(
    "--parallel",
    default=5,
    type=int,
    help="Max concurrent scenario runs.",
)
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory for results.",
)
@click.option(
    "--store",
    "store_path",
    type=click.Path(path_type=Path),
    default=None,
    help="SQLite store path. Defaults to .decibench/decibench.sqlite.",
)
@click.option(
    "--no-store",
    is_flag=True,
    default=False,
    help="Do not persist this run in the local Decibench store.",
)
@click.option(
    "--min-score",
    type=float,
    default=None,
    help="Minimum score threshold (overrides config).",
)
@click.option(
    "--exit-code-on-fail",
    is_flag=True,
    default=False,
    help="Exit with code 1 if score < min-score.",
)
@click.option(
    "--fail-under",
    type=float,
    default=None,
    help="Exit with code 1 if score is less than this value.",
)
@click.option(
    "--fail-on",
    default=None,
    help="Comma-separated categories to fail on (e.g. compliance,latency).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["rich", "json", "markdown", "ci", "junit"]),
    default="rich",
    help="Output format.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Enable verbose logging.",
)
def run_cmd(
    target: str | None,
    suite: str,
    scenario: str | None,
    config_path: Path | None,
    profile: str | None,
    noise: str | None,
    accents: str | None,
    parallel: int,
    output: Path | None,
    store_path: Path | None,
    no_store: bool,
    min_score: float | None,
    exit_code_on_fail: bool,
    fail_under: float | None,
    fail_on: str | None,
    output_format: str,
    verbose: bool,
) -> None:
    """Run test scenarios against a voice agent."""
    import logging

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load config
    config = load_config(config_path, profile)

    # Resolve target
    resolved_target = target or config.target.default

    # Parse comma-separated options
    noise_levels = noise.split(",") if noise else None
    accent_list = accents.split(",") if accents else None
    fail_categories = fail_on.split(",") if fail_on else []

    # Resolve min score (fail_under overrides min_score property)
    effective_min_score = (
        fail_under
        if fail_under is not None
        else (min_score if min_score is not None else config.ci.min_score)
    )
    # Enable failure gate if either old flag or new flag is used
    fail_gate_active = exit_code_on_fail or (fail_under is not None) or fail_categories

    # Create output directory
    if output:
        output.mkdir(parents=True, exist_ok=True)

    # Set up progress bar for rich format
    progress = None
    task_id = None

    if output_format == "rich" and not scenario:
        try:
            from rich.progress import (
                BarColumn,
                Progress,
                SpinnerColumn,
                TextColumn,
                TimeElapsedColumn,
            )
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total})"),
                TimeElapsedColumn(),
                transient=True,
            )
        except ImportError:
            pass

    def on_progress(scenario_id: str, passed: bool, score: float, current: int, total: int) -> None:
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        if progress and task_id is not None:
            progress.update(task_id, completed=current, description=f"  {scenario_id} {status}")

    # Run
    orchestrator = Orchestrator(config)

    if progress:
        progress.start()
        # We don't know total yet, will be set by orchestrator
        task_id = progress.add_task("Starting...", total=100)

    try:
        result = asyncio.run(orchestrator.run_suite(
            target=resolved_target,
            suite=suite,
            noise_levels=noise_levels,
            accents=accent_list,
            parallel=parallel,
            scenario_filter=scenario,
            on_progress=on_progress if progress else None,
        ))
    finally:
        if progress:
            progress.stop()

    if not no_store:
        store = RunStore(store_path or default_store_path())
        run_id = store.save_suite_result(result)
        if verbose:
            click.echo(f"Stored run: {run_id} ({store.path})")

    # Update progress total after we know it
    if progress and task_id is not None:
        progress.update(task_id, total=result.total_scenarios, completed=result.total_scenarios)

    # Output results
    if output_format == "json" or output:
        json_path = (output / "results.json") if output else None
        json_str = JSONReporter.report(result, json_path)
        if output_format == "json" and not output:
            click.echo(json_str)

    if output_format == "rich":
        RichReporter().report_suite(result)

    if output_format == "markdown":
        md_path = (output / "report.md") if output else None
        md = MarkdownReporter.report(result, md_path)
        if not output:
            click.echo(md)

    if output_format == "ci":
        CIReporter.report(result, effective_min_score)

    if output_format == "junit":
        from decibench.reporters.junit import format_junit_xml
        junit_xml = format_junit_xml(result)
        if not output:
            click.echo(junit_xml)
        else:
            (output / "junit.xml").write_text(junit_xml, encoding="utf-8")

    # Automatic failure: exit nonzero when every single scenario failed due
    # to execution or configuration errors — regardless of --fail-under flags.
    # This catches "RETELL_API_KEY missing" and similar total-failure cases
    # that would otherwise silently return 0.
    all_execution_failures = (
        result.total_scenarios > 0
        and result.failed == result.total_scenarios
        and all(
            any("Execution error" in f or "error" in f.lower() for f in er.failures)
            for er in result.results
            if er.failures
        )
    )
    if all_execution_failures:
        click.echo(
            f"All {result.total_scenarios} scenario(s) failed with execution errors. "
            "Check your target, credentials, and configuration.",
            err=True,
        )
        sys.exit(1)

    # Evaluate Threshold Failures
    if fail_gate_active:
        failed = False

        # Check overall score
        if result.decibench_score < effective_min_score:
            click.echo(
                f"  [Error] Score {result.decibench_score:.1f} "
                f"is lower than --fail-under {effective_min_score}",
                err=True,
            )
            failed = True

        # Check specific failure categories
        if fail_categories:
            for er in result.results:
                matched_fails = [c for c in er.failure_summary if c in fail_categories]
                if matched_fails:
                    click.echo(
                        f"  [Error] Scenario {er.scenario_id} triggered "
                        f"--fail-on for categories: {matched_fails}",
                        err=True,
                    )
                    failed = True

        if failed:
            sys.exit(1)

    # Write JSON + markdown output even for non-JSON formats if output dir specified
    if output and output_format != "json":
        JSONReporter.report(result, output / "results.json")
        MarkdownReporter.report(result, output / "report.md")

    # Generate HTML dashboard report
    if output:
        from decibench.reporters.html_reporter import HTMLReporter
        HTMLReporter.report(result, output / "dashboard.html")
        click.echo(f"\nDashboard: {output / 'dashboard.html'}")
