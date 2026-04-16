"""Provider catalog and model presets for semantic evaluation."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

_TIMEOUT = 10.0


@dataclass(frozen=True)
class ProviderCatalog:
    """Metadata for a supported semantic-evaluation provider."""

    provider: str
    display_name: str
    env_var: str
    judge_uri: str
    default_model: str
    quality_model: str
    budget_model: str
    curated_models: tuple[str, ...]


_CATALOG: dict[str, ProviderCatalog] = {
    "openai": ProviderCatalog(
        provider="openai",
        display_name="OpenAI",
        env_var="OPENAI_API_KEY",
        judge_uri="openai-compat",
        default_model="gpt-5-mini",
        quality_model="gpt-5.1",
        budget_model="gpt-5-nano",
        curated_models=("gpt-5.1", "gpt-5-mini", "gpt-5-nano"),
    ),
    "anthropic": ProviderCatalog(
        provider="anthropic",
        display_name="Anthropic",
        env_var="ANTHROPIC_API_KEY",
        judge_uri="anthropic",
        default_model="claude-sonnet-4-20250514",
        quality_model="claude-opus-4-1-20250805",
        budget_model="claude-3-5-haiku-20241022",
        curated_models=(
            "claude-opus-4-1-20250805",
            "claude-sonnet-4-20250514",
            "claude-3-5-haiku-20241022",
        ),
    ),
    "gemini": ProviderCatalog(
        provider="gemini",
        display_name="Gemini",
        env_var="GEMINI_API_KEY",
        judge_uri="gemini",
        default_model="gemini-2.5-flash",
        quality_model="gemini-2.5-pro",
        budget_model="gemini-2.5-flash-lite",
        curated_models=("gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"),
    ),
}

_ALIASES = {
    "claude": "anthropic",
    "google": "gemini",
}


def supported_providers() -> tuple[str, ...]:
    """Return the supported semantic-evaluation providers."""
    return tuple(_CATALOG.keys())


def normalize_provider(provider: str) -> str:
    """Normalize common aliases to canonical provider ids."""
    normalized = provider.strip().lower()
    normalized = _ALIASES.get(normalized, normalized)
    if normalized not in _CATALOG:
        available = ", ".join(sorted(_CATALOG))
        msg = f"Unsupported provider '{provider}'. Available: {available}"
        raise ValueError(msg)
    return normalized


def get_provider_catalog(provider: str) -> ProviderCatalog:
    """Return provider metadata for a canonical or aliased provider name."""
    return _CATALOG[normalize_provider(provider)]


def resolve_model_preset(provider: str, preset: str) -> str:
    """Resolve a preset label to a concrete model name."""
    catalog = get_provider_catalog(provider)
    normalized = preset.strip().lower()
    if normalized == "balanced":
        return catalog.default_model
    if normalized == "quality":
        return catalog.quality_model
    if normalized == "budget":
        return catalog.budget_model
    msg = f"Unknown preset '{preset}'. Use balanced, quality, or budget."
    raise ValueError(msg)


def judge_provider_from_uri(uri: str) -> str | None:
    """Infer the semantic provider from a configured judge URI."""
    if not uri or uri == "none":
        return None
    if uri.startswith("anthropic"):
        return "anthropic"
    if uri.startswith("gemini"):
        return "gemini"
    if uri.startswith("openai-compat"):
        return "openai"
    return None


def fetch_live_models(provider: str, api_key: str) -> list[str]:
    """Fetch available models from the provider's official model-list endpoint."""
    catalog = get_provider_catalog(provider)
    if not api_key:
        msg = f"{catalog.display_name} API key is required to list live models."
        raise ValueError(msg)

    if catalog.provider == "openai":
        return _fetch_openai_models(api_key)
    if catalog.provider == "anthropic":
        return _fetch_anthropic_models(api_key)
    if catalog.provider == "gemini":
        return _fetch_gemini_models(api_key)

    msg = f"Live model listing is not implemented for provider '{provider}'."
    raise ValueError(msg)


def _fetch_openai_models(api_key: str) -> list[str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    response = httpx.get(
        "https://api.openai.com/v1/models",
        headers=headers,
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    return sorted(
        item["id"]
        for item in payload.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )


def _fetch_anthropic_models(api_key: str) -> list[str]:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    response = httpx.get(
        "https://api.anthropic.com/v1/models",
        headers=headers,
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    return sorted(
        item["id"]
        for item in payload.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )


def _fetch_gemini_models(api_key: str) -> list[str]:
    response = httpx.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": api_key},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    names: list[str] = []
    for item in payload.get("models", []):
        if not isinstance(item, dict):
            continue
        raw_name = item.get("name")
        if not isinstance(raw_name, str):
            continue
        names.append(raw_name.removeprefix("models/"))
    return sorted(names)
