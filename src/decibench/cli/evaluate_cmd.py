"""decibench evaluate-calls — Grade imported production calls."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from decibench.config import load_config
from decibench.evaluators.compliance import ComplianceEvaluator
from decibench.evaluators.hallucination import HallucinationEvaluator
from decibench.evaluators.task import TaskCompletionEvaluator
from decibench.providers.registry import get_judge
from decibench.replay.evaluate import ImportedCallEvaluator
from decibench.store.sqlite import RunStore


@click.command("evaluate-calls")
@click.option("--limit", default=10, help="Number of traces to evaluate.")
@click.option("--failed-only", is_flag=True, help="Only show traces that failed evaluation.")
@click.option("--source", default=None, help="Only evaluate traces from a given source.")
@click.option("--since", default=None, help="Only evaluate traces imported since this ISO timestamp.")
@click.option(
    "--category",
    "failure_category",
    default=None,
    help="Only show results matching a failure category.",
)
@click.option("--store/--no-store", "persist_results", default=True, help="Persist evaluation results.")
def evaluate_calls_cmd(
    limit: int,
    failed_only: bool,
    source: str | None,
    since: str | None,
    failure_category: str | None,
    persist_results: bool,
) -> None:
    """Evaluate imported production calls and grade them."""
    console = Console()
    store = RunStore()
    config = load_config(Path("decibench.toml"))

    traces_meta = store.list_call_traces(limit=limit, source=source, since=since)
    if not traces_meta:
        console.print("[yellow]No imported call traces found.[/yellow]")
        return

    console.print(f"[bold cyan]Evaluating {len(traces_meta)} imported traces...[/bold cyan]")

    judge = get_judge(config.providers.judge_model) if config.has_judge else None

    # We load transcript-only compatible evaluators for now.
    evaluators = [
        ComplianceEvaluator(),
        HallucinationEvaluator(),
        TaskCompletionEvaluator(),
    ]

    eval_service = ImportedCallEvaluator(evaluators, config, judge=judge)

    # Run evaluations
    async def _run() -> None:
        table = Table(title="Imported Call Evaluations", title_style="bold magenta")
        table.add_column("Call ID", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Pass/Fail", justify="center")
        table.add_column("Failures", style="red")
        table.add_column("Stored", justify="center")

        for meta in traces_meta:
            trace = store.get_call_trace(meta["id"])
            if not trace:
                continue

            eval_result = await eval_service.evaluate_trace(trace)
            evaluation_id = store.save_call_evaluation(trace, eval_result) if persist_results else None

            if failed_only and eval_result.passed:
                continue

            if failure_category and failure_category not in eval_result.failure_summary:
                continue

            status = "[green]PASS[/green]" if eval_result.passed else "[red]FAIL[/red]"
            color = "green" if eval_result.passed else "red"
            stored_str = evaluation_id[:12] if evaluation_id else "-"

            # Format failures string
            fail_str = ", ".join(eval_result.failure_summary) if eval_result.failure_summary else ""
            if not fail_str and eval_result.failures:
                fail_str = "other"

            table.add_row(
                trace.id[:12],
                f"[{color}]{eval_result.score:.1f}[/{color}]",
                status,
                fail_str,
                stored_str,
            )

        console.print(table)

    asyncio.run(_run())
