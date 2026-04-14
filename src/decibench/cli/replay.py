"""decibench replay — inspect or convert imported production calls."""

from __future__ import annotations

from pathlib import Path

import click

from decibench.replay import trace_to_scenario_yaml
from decibench.store import RunStore, default_store_path


@click.command("replay")
@click.argument("call_id")
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--to-scenario", type=click.Path(path_type=Path), default=None)
def replay_cmd(call_id: str, store_path: Path | None, to_scenario: Path | None) -> None:
    """Inspect an imported call or convert it into a regression scenario."""
    store = RunStore(store_path or default_store_path())
    trace = store.get_call_trace(call_id)
    if trace is None:
        raise click.ClickException(f"Call trace not found: {call_id}")

    if to_scenario:
        scenario_yaml = trace_to_scenario_yaml(trace)
        to_scenario.parent.mkdir(parents=True, exist_ok=True)
        to_scenario.write_text(scenario_yaml)
        click.echo(f"Wrote regression scenario: {to_scenario}")
        return

    click.echo(f"Call: {trace.id}")
    click.echo(f"Source: {trace.source}")
    click.echo(f"Target: {trace.target or 'unknown'}")
    click.echo(f"Duration: {trace.duration_ms:.1f}ms")
    click.echo()
    click.echo(trace.text or "(no transcript)")
