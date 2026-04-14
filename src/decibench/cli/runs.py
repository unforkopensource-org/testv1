"""decibench runs — inspect persisted run and call-trace history."""

from __future__ import annotations

from pathlib import Path

import click

from decibench.reporters.json_reporter import JSONReporter
from decibench.store import RunStore, default_store_path


@click.group("runs")
def runs_cmd() -> None:
    """Inspect stored Decibench runs and imported calls."""


@runs_cmd.command("list")
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--limit", default=20, type=int)
def list_runs_cmd(store_path: Path | None, limit: int) -> None:
    """List stored suite runs."""
    store = RunStore(store_path or default_store_path())
    rows = store.list_runs(limit=limit)
    if not rows:
        click.echo("No stored runs found.")
        return
    for row in rows:
        click.echo(
            f"{row['id']}  score={row['score']:.1f}  "
            f"{row['passed']}/{row['total_scenarios']} passed  "
            f"suite={row['suite']} target={row['target']}"
        )


@runs_cmd.command("show")
@click.argument("run_id")
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["summary", "json"]),
    default="summary",
)
def show_run_cmd(run_id: str, store_path: Path | None, output_format: str) -> None:
    """Show a stored suite run."""
    store = RunStore(store_path or default_store_path())
    result = store.get_suite_result(run_id)
    if result is None:
        raise click.ClickException(f"Run not found: {run_id}")
    if output_format == "json":
        click.echo(JSONReporter.report(result))
        return
    click.echo(f"Run: {run_id}")
    click.echo(f"Suite: {result.suite}")
    click.echo(f"Target: {result.target}")
    click.echo(f"Score: {result.decibench_score}/100")
    click.echo(f"Passed: {result.passed}/{result.total_scenarios}")
    if result.failed:
        click.echo("Failures:")
        for scenario in result.results:
            if not scenario.passed:
                reason = "; ".join(scenario.failures[:2]) or "failed"
                click.echo(f"  - {scenario.scenario_id}: {reason}")


@runs_cmd.command("calls")
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--limit", default=20, type=int)
def list_calls_cmd(store_path: Path | None, limit: int) -> None:
    """List imported production call traces."""
    store = RunStore(store_path or default_store_path())
    rows = store.list_call_traces(limit=limit)
    if not rows:
        click.echo("No imported call traces found.")
        return
    for row in rows:
        click.echo(
            f"{row['id']}  source={row['source']}  target={row['target']}  "
            f"duration_ms={row['duration_ms']:.1f}"
        )
