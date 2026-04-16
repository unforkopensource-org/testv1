"""Smoke tests for the registered native platform connectors.

These tests confirm that the Retell and Vapi connector classes are wired into
the registry and reject obviously-wrong inputs early. End-to-end tests against
the bridge sidecar live in `test_bridge.py`; real-vendor tests live in
`test_bridge_real_*.py` and are gated on environment variables.
"""

from __future__ import annotations

import pytest

from decibench.connectors.registry import get_connector


@pytest.mark.asyncio
async def test_vapi_connector_rejects_missing_key() -> None:
    """Vapi connector fails fast at connect() when no public_key is configured."""
    connector = get_connector("vapi://test-agent")
    with pytest.raises(ValueError, match="API key"):
        await connector.connect("vapi://test-agent", {})


@pytest.mark.asyncio
async def test_retell_connector_rejects_missing_key() -> None:
    """Retell connector fails fast at connect() when no api_key is configured."""
    connector = get_connector("retell://test-agent")
    with pytest.raises(ValueError, match="API key"):
        await connector.connect("retell://test-agent", {})


@pytest.mark.asyncio
async def test_retell_connector_rejects_wrong_uri_prefix() -> None:
    """Mismatched URI prefix is a programming error and surfaces early."""
    connector = get_connector("retell://x")
    with pytest.raises(ValueError, match="retell://"):
        await connector.connect("vapi://x", {"retell_api_key": "k"})
