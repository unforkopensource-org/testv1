"""decibench init — interactive local-first project setup."""

from __future__ import annotations

from pathlib import Path

import click

from decibench.cli._config_file import build_config_text
from decibench.llm_catalog import (
    get_provider_catalog,
    normalize_provider,
    resolve_model_preset,
    supported_providers,
)
from decibench.secrets import keyring_available, store_secret

_TARGET_TEMPLATES = {
    "demo": "demo",
    "websocket": "ws://localhost:8080/ws",
    "process": 'exec:python my_agent.py',
    "http": "http://localhost:8080/invoke",
    "retell": "retell://your_agent_id",
    "vapi": "vapi://your_agent_id",
}


@click.command("init")
@click.option(
    "--force", "-f",
    is_flag=True,
    default=False,
    help="Overwrite existing decibench.toml.",
)
@click.option("--name", "project_name", default="", help="Project name to write into decibench.toml.")
@click.option("--target", default="", help="Target URI to use instead of the interactive target menu.")
@click.option(
    "--provider",
    type=click.Choice(("none", *supported_providers())),
    default="",
    help="Semantic judge provider to configure.",
)
@click.option("--model", default="", help="Semantic judge model to configure.")
@click.option(
    "--no-prompt",
    is_flag=True,
    default=False,
    help="Use defaults and provided options instead of prompting.",
)
def init_cmd(
    force: bool,
    project_name: str,
    target: str,
    provider: str,
    model: str,
    no_prompt: bool,
) -> None:
    """Create a local-first decibench.toml configuration file."""
    config_path = Path.cwd() / "decibench.toml"

    if config_path.exists() and not force:
        click.echo("decibench.toml already exists. Use --force to overwrite.")
        raise SystemExit(1)

    chosen_name = project_name or _prompt_project_name(no_prompt)
    chosen_target = target or _prompt_target(no_prompt)
    chosen_provider = _resolve_provider(provider, no_prompt)
    chosen_model = _resolve_model(chosen_provider, model, no_prompt)

    config_text = build_config_text(
        project_name=chosen_name,
        target=chosen_target,
        judge_uri=_judge_uri_for_provider(chosen_provider),
        judge_model=chosen_model,
    )
    config_path.write_text(config_text, encoding="utf-8")

    if chosen_provider != "none" and not no_prompt:
        _maybe_store_key(chosen_provider)

    click.echo(f"Created {config_path}")
    click.echo()
    click.echo("Next steps:")
    if chosen_target.startswith(("retell://", "vapi://")):
        click.echo("  1. decibench bridge install")
        click.echo("  2. decibench doctor")
        click.echo("  3. decibench run --suite quick")
    else:
        click.echo("  1. decibench doctor")
        click.echo("  2. decibench run --suite quick")
    click.echo("  3. decibench serve")

    if chosen_provider != "none":
        click.echo()
        click.echo(
            f"Semantic evaluation is configured for {get_provider_catalog(chosen_provider).display_name} "
            f"with model {chosen_model}."
        )
        click.echo(f"Manage keys with: decibench auth set {chosen_provider}")


def _prompt_project_name(no_prompt: bool) -> str:
    if no_prompt:
        return Path.cwd().name or "my-voice-agent"
    default = Path.cwd().name or "my-voice-agent"
    return str(click.prompt("Project name", default=default, show_default=True))


def _prompt_target(no_prompt: bool) -> str:
    if no_prompt:
        return _TARGET_TEMPLATES["demo"]

    click.echo("Choose a target type:")
    options = [
        ("demo", "Built-in demo agent"),
        ("websocket", "WebSocket voice agent"),
        ("process", "Local process / exec target"),
        ("http", "HTTP endpoint"),
        ("retell", "Native Retell bridge target"),
        ("vapi", "Native Vapi bridge target"),
    ]
    for index, (_, label) in enumerate(options, start=1):
        click.echo(f"  {index}. {label}")
    selection = int(click.prompt("Target", type=click.IntRange(1, len(options)), default=1))
    return _TARGET_TEMPLATES[options[selection - 1][0]]


def _resolve_provider(provider: str, no_prompt: bool) -> str:
    if provider:
        return normalize_provider(provider) if provider != "none" else "none"
    if no_prompt:
        return "none"

    if not click.confirm("Enable semantic evaluation with an LLM judge?", default=False):
        return "none"

    options = list(supported_providers())
    click.echo("Choose a semantic judge provider:")
    for index, item in enumerate(options, start=1):
        click.echo(f"  {index}. {get_provider_catalog(item).display_name}")
    selection = int(click.prompt("Provider", type=click.IntRange(1, len(options)), default=1))
    return options[selection - 1]


def _resolve_model(provider: str, model: str, no_prompt: bool) -> str:
    if provider == "none":
        return ""
    if model:
        return model
    catalog = get_provider_catalog(provider)
    if no_prompt:
        return catalog.default_model

    if click.confirm(
        f"Use the recommended default model ({catalog.default_model})?", default=True
    ):
        return catalog.default_model
    return str(click.prompt("Model name", default=resolve_model_preset(provider, "balanced")))


def _judge_uri_for_provider(provider: str) -> str:
    if provider == "none":
        return "none"
    return get_provider_catalog(provider).judge_uri


def _maybe_store_key(provider: str) -> None:
    if not click.confirm(f"Paste a {provider} API key now?", default=False):
        return
    if not keyring_available():
        env_var = get_provider_catalog(provider).env_var
        click.echo(f"System keyring is unavailable. Export {env_var}=... instead.")
        return
    secret = click.prompt("API key", hide_input=True)
    if not secret.strip():
        click.echo("Skipping empty API key.")
        return
    store_secret(provider, secret.strip())
    click.echo(f"Stored {provider} API key in the local keyring.")
