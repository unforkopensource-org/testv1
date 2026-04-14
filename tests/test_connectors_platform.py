import pytest

from decibench.connectors.registry import get_connector


@pytest.mark.asyncio
async def test_vapi_connector_not_implemented():
    """Vapi connector fails fast at connect() before making any API calls."""
    connector = get_connector("vapi")
    with pytest.raises(NotImplementedError, match=r"Daily\.co"):
        await connector.connect("vapi://test-agent", {})


@pytest.mark.asyncio
async def test_retell_connector_not_implemented():
    """Retell connector fails fast at connect() before making any API calls."""
    connector = get_connector("retell")
    with pytest.raises(NotImplementedError, match="LiveKit"):
        await connector.connect("retell://test-agent", {})
