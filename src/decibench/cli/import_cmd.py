"""decibench import — bring production calls into Decibench."""

from __future__ import annotations

from pathlib import Path

import click

from decibench.imports import import_jsonl
from decibench.store import RunStore, default_store_path


@click.group("import")
def import_cmd() -> None:
    """Import production calls for evaluation and replay."""


@import_cmd.command("jsonl")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
def import_jsonl_cmd(path: Path, store_path: Path | None) -> None:
    """Import generic JSONL call traces."""
    store = RunStore(store_path or default_store_path())
    traces = import_jsonl(path)
    for trace in traces:
        store.save_call_trace(trace)
    click.echo(f"Imported {len(traces)} call trace(s) into {store.path}")

def _run_importer_async(importer_name: str, limit: int, since: str | None) -> None:
    import asyncio
    import os

    from decibench.imports.registry import get_importer

    importer = get_importer(importer_name)
    api_key_var_map = {"vapi": "VAPI_API_KEY", "retell": "RETELL_API_KEY"}
    api_key = os.environ.get(api_key_var_map.get(importer_name, ""))

    traces = asyncio.run(importer.fetch_calls(limit=limit, since=since, api_key=api_key))
    store = RunStore(default_store_path())
    for trace in traces:
        store.save_call_trace(trace)
    click.echo(f"Imported {len(traces)} call traces from {importer_name} into {store.path}")

@import_cmd.command("vapi")
@click.option("--limit", default=10, help="Max traces to fetch.")
@click.option("--since", default=None, help="Fetch calls since this date.")
def import_vapi_cmd(limit: int, since: str | None) -> None:
    """Import call traces from Vapi."""
    # Ensure standard Decibench config environment is loaded if needed
    _run_importer_async("vapi", limit, since)

@import_cmd.command("retell")
@click.option("--limit", default=10, help="Max traces to fetch.")
@click.option("--since", default=None, help="Fetch calls since this date.")
def import_retell_cmd(limit: int, since: str | None) -> None:
    """Import call traces from Retell."""
    _run_importer_async("retell", limit, since)

