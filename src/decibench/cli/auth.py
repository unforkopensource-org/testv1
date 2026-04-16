"""decibench auth — local provider credential management."""

from __future__ import annotations

import click
import httpx

from decibench.llm_catalog import fetch_live_models, get_provider_catalog
from decibench.secrets import (
    delete_secret,
    describe_secret,
    keyring_available,
    store_secret,
)

_SUPPORTED_AUTH_PROVIDERS = ("openai", "anthropic", "gemini", "vapi", "retell")


@click.group("auth")
def auth_cmd() -> None:
    """Manage local provider credentials."""


@auth_cmd.command("set")
@click.argument("provider", type=click.Choice(_SUPPORTED_AUTH_PROVIDERS))
def auth_set_cmd(provider: str) -> None:
    """Store a provider API key in the local keyring."""
    if not keyring_available():
        env_var = _env_var(provider)
        raise click.ClickException(
            f"System keyring is unavailable. Export {env_var}=... instead."
        )

    secret = click.prompt(f"Paste your {provider} API key", hide_input=True).strip()
    if not secret:
        raise click.ClickException("API key cannot be empty.")
    store_secret(provider, secret)
    click.echo(f"Stored {provider} API key in the local keyring.")
    click.echo(f"Validate it with: decibench auth test {provider}")


@auth_cmd.command("list")
def auth_list_cmd() -> None:
    """List configured provider credential sources."""
    for provider in _SUPPORTED_AUTH_PROVIDERS:
        state = describe_secret(provider)
        click.echo(f"{provider:<10} {state.source:<8} {state.env_var}")


@auth_cmd.command("test")
@click.argument("provider", type=click.Choice(_SUPPORTED_AUTH_PROVIDERS))
def auth_test_cmd(provider: str) -> None:
    """Check whether a provider key is configured and usable."""
    state = describe_secret(provider)
    if state.source == "missing":
        raise click.ClickException(
            f"No {provider} credential found. Run: decibench auth set {provider}"
        )

    if provider in ("vapi", "retell"):
        click.echo(
            f"{provider} credential found via {state.source}. Live connectivity test is not implemented yet."
        )
        return

    api_key = _load_secret_for_test(provider)
    try:
        models = fetch_live_models(provider, api_key)
    except (httpx.HTTPError, ValueError) as exc:
        raise click.ClickException(f"{provider} credential check failed: {exc}") from exc

    click.echo(
        f"{get_provider_catalog(provider).display_name} credential looks good "
        f"({len(models)} models visible)."
    )


@auth_cmd.command("remove")
@click.argument("provider", type=click.Choice(_SUPPORTED_AUTH_PROVIDERS))
def auth_remove_cmd(provider: str) -> None:
    """Delete a provider key from the local keyring."""
    delete_secret(provider)
    click.echo(f"Removed {provider} credential from the local keyring.")


def _env_var(provider: str) -> str:
    if provider in ("openai", "anthropic", "gemini"):
        return get_provider_catalog(provider).env_var
    return f"{provider.upper()}_API_KEY"


def _load_secret_for_test(provider: str) -> str:
    from decibench.secrets import load_secret

    return load_secret(provider)
