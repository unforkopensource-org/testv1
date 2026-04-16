"""Local secret handling for provider credentials."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

try:
    import keyring as _keyring
    from keyring.errors import KeyringError as _KeyringError
except ImportError:  # pragma: no cover - exercised through helper functions
    _keyring = None
    _KeyringError = Exception


from decibench.llm_catalog import get_provider_catalog

_SERVICE_NAME: Final = "decibench"
_ENV_VARS: Final = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "vapi": "VAPI_API_KEY",
    "retell": "RETELL_API_KEY",
}


@dataclass(frozen=True)
class SecretState:
    """Status summary for a provider secret."""

    provider: str
    source: str
    env_var: str


def env_var_name(provider: str) -> str:
    """Return the environment variable name for a provider."""
    normalized = _normalize_secret_provider(provider)
    return _ENV_VARS[normalized]


def keyring_available() -> bool:
    """Whether a usable keyring backend is importable."""
    return _keyring is not None


def store_secret(provider: str, secret: str, profile: str = "default") -> None:
    """Store a provider secret in the local keyring."""
    if not keyring_available():
        msg = "Python keyring is not available in this environment."
        raise RuntimeError(msg)
    _keyring.set_password(_SERVICE_NAME, _secret_name(provider, profile), secret)


def load_secret(provider: str, profile: str = "default") -> str:
    """Load a provider secret from env var or keyring, preferring env vars."""
    normalized = _normalize_secret_provider(provider)
    env_var = env_var_name(normalized)
    env_value = os.environ.get(env_var, "")
    if env_value:
        return env_value
    if not keyring_available():
        return ""
    value = _keyring.get_password(_SERVICE_NAME, _secret_name(normalized, profile))
    return value or ""


def delete_secret(provider: str, profile: str = "default") -> None:
    """Delete a provider secret from the local keyring."""
    if not keyring_available():
        return
    try:
        _keyring.delete_password(_SERVICE_NAME, _secret_name(provider, profile))
    except _KeyringError:
        return


def describe_secret(provider: str, profile: str = "default") -> SecretState:
    """Describe where a provider secret would currently come from."""
    normalized = _normalize_secret_provider(provider)
    env_var = env_var_name(normalized)
    if os.environ.get(env_var):
        return SecretState(provider=normalized, source="env", env_var=env_var)
    if keyring_available():
        value = _keyring.get_password(_SERVICE_NAME, _secret_name(normalized, profile))
        if value:
            return SecretState(provider=normalized, source="keyring", env_var=env_var)
    return SecretState(provider=normalized, source="missing", env_var=env_var)


def resolve_secret(provider: str, current_value: str = "", profile: str = "default") -> str:
    """Resolve a secret from config, env vars, or keyring in that order."""
    if current_value:
        return current_value
    return load_secret(provider, profile=profile)


def _secret_name(provider: str, profile: str) -> str:
    return f"{_normalize_secret_provider(provider)}/{profile}"


def _normalize_secret_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized in ("claude", "anthropic"):
        return "anthropic"
    if normalized in ("google", "gemini"):
        return "gemini"
    if normalized in ("openai", "vapi", "retell"):
        return normalized
    # Reuse catalog normalization for supported LLM providers.
    try:
        return get_provider_catalog(normalized).provider
    except ValueError as exc:
        available = ", ".join(sorted(_ENV_VARS))
        msg = f"Unsupported secret provider '{provider}'. Available: {available}"
        raise ValueError(msg) from exc
