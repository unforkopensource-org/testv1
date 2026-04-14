from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decibench.imports.retell import RetellImporter
from decibench.imports.vapi import VapiImporter


@pytest.fixture
def vapi_mock_response():
    return [
        {
            "id": "call-123",
            "status": "ended",
            "endedReason": "customer-ended",
            "duration": 45,
            "createdAt": "2026-04-14T12:00:00Z",
            "phoneCallProvider": "twilio",
            "messages": [
                {"role": "user", "message": "hello"},
                {"role": "assistant", "message": "hi there"}
            ]
        }
    ]

@pytest.fixture
def retell_mock_response():
    return [
        {
            "call_id": "call-456",
            "start_timestamp": "2026-04-14T12:00:00Z",
            "agent_id": "agent-xyz",
            "duration": 30,
            "transcript_object": [
                {"role": "user", "content": "hello", "words": [{"start": 0.0, "end": 0.5}]},
                {"role": "agent", "content": "hi there", "words": [{"start": 1.0, "end": 1.5}]}
            ]
        }
    ]

@pytest.mark.asyncio
async def test_vapi_importer(vapi_mock_response):
    importer = VapiImporter()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = vapi_mock_response
        mock_get.return_value = mock_resp

        traces = await importer.fetch_calls(api_key="fake-vapi", limit=1)

        assert len(traces) == 1
        trace = traces[0]
        assert trace.id == "call-123"
        assert trace.source == "vapi"
        assert trace.target == "twilio"
        assert trace.duration_ms == 45000.0

        assert len(trace.transcript) == 2
        assert trace.transcript[0].role == "caller"
        assert trace.transcript[0].text == "hello"
        assert trace.transcript[1].role == "agent"
        assert trace.transcript[1].text == "hi there"

        assert len(trace.events) == 2  # METADATA, TURN_END

@pytest.mark.asyncio
async def test_retell_importer(retell_mock_response):
    importer = RetellImporter()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = retell_mock_response
        mock_get.return_value = mock_resp

        traces = await importer.fetch_calls(api_key="fake-retell", limit=1)

        assert len(traces) == 1
        trace = traces[0]
        assert trace.id == "call-456"
        assert trace.source == "retell"
        assert trace.target == "agent-xyz"
        assert trace.duration_ms == 30000.0

        assert len(trace.transcript) == 2
        assert trace.transcript[0].role == "caller"
        assert trace.transcript[0].start_ms == 0.0
        assert trace.transcript[0].end_ms == 500.0

        assert trace.transcript[1].role == "agent"
        assert trace.transcript[1].start_ms == 1000.0
        assert trace.transcript[1].end_ms == 1500.0
