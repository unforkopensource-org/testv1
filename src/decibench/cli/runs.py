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
@click.option("--source", default=None)
@click.option("--since", default=None)
def list_calls_cmd(store_path: Path | None, limit: int, source: str | None, since: str | None) -> None:
    """List imported production call traces."""
    store = RunStore(store_path or default_store_path())
    rows = store.list_call_traces(limit=limit, source=source, since=since)
    if not rows:
        click.echo("No imported call traces found.")
        return
    for row in rows:
        click.echo(
            f"{row['id']}  source={row['source']}  target={row['target']}  "
            f"duration_ms={row['duration_ms']:.1f}"
        )


@runs_cmd.command("evaluations")
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--limit", default=20, type=int)
@click.option("--source", default=None)
@click.option("--failed-only", is_flag=True, default=False)
@click.option("--category", default=None)
@click.option("--call-id", default=None)
@click.option("--since", default=None)
def list_evaluations_cmd(
    store_path: Path | None,
    limit: int,
    source: str | None,
    failed_only: bool,
    category: str | None,
    call_id: str | None,
    since: str | None,
) -> None:
    """List stored imported-call evaluations."""
    store = RunStore(store_path or default_store_path())
    rows = store.list_call_evaluations(
        limit=limit,
        source=source,
        failed_only=failed_only,
        category=category,
        call_id=call_id,
        since=since,
    )
    if not rows:
        click.echo("No stored imported-call evaluations found.")
        return
    for row in rows:
        status = "PASS" if row["passed"] else "FAIL"
        failures = ",".join(row["failure_summary"]) if row["failure_summary"] else "-"
        click.echo(
            f"{row['id']}  call={row['call_id']}  source={row['source']}  "
            f"score={row['score']:.1f}  status={status}  failures={failures}"
        )


@runs_cmd.command("evaluation-show")
@click.argument("evaluation_id")
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["summary", "json"]),
    default="summary",
)
def show_evaluation_cmd(evaluation_id: str, store_path: Path | None, output_format: str) -> None:
    """Show a stored imported-call evaluation."""
    store = RunStore(store_path or default_store_path())
    result = store.get_call_evaluation(evaluation_id)
    if result is None:
        raise click.ClickException(f"Call evaluation not found: {evaluation_id}")
    if output_format == "json":
        click.echo(result.model_dump_json(indent=2))
        return
    click.echo(f"Evaluation: {evaluation_id}")
    click.echo(f"Scenario: {result.scenario_id}")
    click.echo(f"Score: {result.score:.1f}/100")
    click.echo(f"Passed: {'yes' if result.passed else 'no'}")
    if result.failure_summary:
        click.echo(f"Failure categories: {', '.join(result.failure_summary)}")
    if result.failures:
        click.echo("Failures:")
        for failure in result.failures[:5]:
            click.echo(f"  - {failure}")
