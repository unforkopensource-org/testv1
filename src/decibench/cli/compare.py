"""decibench compare — side-by-side comparison of two agent configurations."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import click

from decibench.config import load_config
from decibench.orchestrator import Orchestrator
from decibench.reporters.json_reporter import JSONReporter
from decibench.reporters.rich_reporter import RichReporter

if TYPE_CHECKING:
    from decibench.models import SuiteResult


@click.command("compare")
@click.option("--a", "target_a", required=True, help="First agent target URI.")
@click.option("--b", "target_b", required=True, help="Second agent target URI.")
@click.option("--suite", "-s", default="quick", help="Test suite to run.")
@click.option(
    "--config", "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
)
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None)
@click.option("--parallel", default=5, type=int)
def compare_cmd(
    target_a: str,
    target_b: str,
    suite: str,
    config_path: Path | None,
    output: Path | None,
    parallel: int,
) -> None:
    """Side-by-side comparison of two voice agents."""
    config = load_config(config_path)

    async def _run_both() -> tuple[SuiteResult, SuiteResult]:
        # Separate orchestrator instances to prevent state cross-contamination
        orch_a = Orchestrator(config)
        orch_b = Orchestrator(config)
        result_a, result_b = await asyncio.gather(
            orch_a.run_suite(target=target_a, suite=suite, parallel=parallel),
            orch_b.run_suite(target=target_b, suite=suite, parallel=parallel),
        )
        return result_a, result_b

    result_a, result_b = asyncio.run(_run_both())

    # Rich comparison output
    reporter = RichReporter()
    reporter.report_compare(result_a, result_b, name_a=target_a, name_b=target_b)

    # Save JSON if output specified
    if output:
        output.mkdir(parents=True, exist_ok=True)
        JSONReporter.report(result_a, output / "result_a.json")
        JSONReporter.report(result_b, output / "result_b.json")
