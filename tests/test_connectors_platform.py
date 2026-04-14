import pytest

from decibench.connectors.registry import get_connector
from decibench.models import AudioBuffer, AudioEncoding


@pytest.mark.asyncio
async def test_vapi_connector_missing_key():
    connector = get_connector("vapi")
    with pytest.raises(ValueError, match="vapi_api_key"):
        await connector.connect("vapi://test-agent", {})

@pytest.mark.asyncio
async def test_retell_connector_missing_key():
    connector = get_connector("retell")
    with pytest.raises(ValueError, match="retell_api_key"):
        await connector.connect("retell://test-agent", {})

@pytest.mark.asyncio
async def test_vapi_webrtc_not_implemented():
    connector = get_connector("vapi")
    # Simulate an initialized state
    connector._web_call_url = "http://fake"
    with pytest.raises(NotImplementedError, match=r"Daily\.co"):
        await connector.send_audio(
            None,
            AudioBuffer(
                data=b"test",
                sample_rate=16000,
                encoding=AudioEncoding.PCM_S16LE,
            ),
        )

@pytest.mark.asyncio
async def test_retell_webrtc_not_implemented():
    connector = get_connector("retell")
    connector._access_token = "fake-token"  # noqa: S105
    with pytest.raises(NotImplementedError, match="LiveKit"):
        await connector.send_audio(
            None,
            AudioBuffer(
                data=b"test",
                sample_rate=16000,
                encoding=AudioEncoding.PCM_S16LE,
            ),
        )
