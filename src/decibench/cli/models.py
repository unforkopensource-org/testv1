"""decibench models — semantic-evaluation model selection helpers."""

from __future__ import annotations

from pathlib import Path

import click
import httpx

from decibench.cli._config_file import update_judge_settings
from decibench.config import load_config
from decibench.llm_catalog import (
    fetch_live_models,
    get_provider_catalog,
    judge_provider_from_uri,
    resolve_model_preset,
    supported_providers,
)
from decibench.secrets import describe_secret, load_secret


@click.group("models")
def models_cmd() -> None:
    """List and configure semantic-evaluation models."""


@models_cmd.command("list")
@click.argument("provider", type=click.Choice(supported_providers()))
@click.option(
    "--live/--curated",
    "live",
    default=True,
    help="Fetch live models when credentials are available, or force curated defaults.",
)
def models_list_cmd(provider: str, live: bool) -> None:
    """List models for a semantic-evaluation provider."""
    catalog = get_provider_catalog(provider)
    state = describe_secret(provider)

    if live and state.source != "missing":
        try:
            models = fetch_live_models(provider, load_secret(provider))
        except (ValueError, httpx.HTTPError) as exc:
            click.echo(f"Could not fetch live models: {exc}")
            models = list(catalog.curated_models)
            click.echo("Showing curated fallback models instead:")
        else:
            click.echo(f"Live models for {catalog.display_name}:")
    else:
        models = list(catalog.curated_models)
        click.echo(f"Curated models for {catalog.display_name}:")

    for model in models:
        click.echo(f"  - {model}")


@models_cmd.command("preset")
@click.argument("provider", type=click.Choice(supported_providers()))
@click.argument("preset", type=click.Choice(("balanced", "quality", "budget")))
def models_preset_cmd(provider: str, preset: str) -> None:
    """Set the configured judge to a provider's recommended preset."""
    model = resolve_model_preset(provider, preset)
    _write_selection(provider, model)
    click.echo(f"Configured {provider} semantic judge with preset {preset}: {model}")


@models_cmd.command("use")
@click.argument("provider", type=click.Choice(supported_providers()))
@click.argument("model")
def models_use_cmd(provider: str, model: str) -> None:
    """Set the configured judge model explicitly."""
    _write_selection(provider, model)
    click.echo(f"Configured {provider} semantic judge with model {model}")


@models_cmd.command("current")
def models_current_cmd() -> None:
    """Show the currently configured semantic judge provider and model."""
    config = load_config()
    provider = judge_provider_from_uri(config.providers.judge)
    if provider is None:
        click.echo("Semantic evaluation is currently disabled (judge = none).")
        return
    source = describe_secret(provider).source
    click.echo(f"Provider: {provider}")
    click.echo(f"Model:    {config.providers.judge_model or '(not set)'}")
    click.echo(f"Key:      {source}")


def _write_selection(provider: str, model: str) -> None:
    from decibench.config import find_config

    found = find_config()
    config_path = found if found is not None else Path.cwd() / "decibench.toml"
    update_judge_settings(config_path, provider=provider, model=model)
