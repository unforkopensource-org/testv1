"""Tests for the demo connector."""

from __future__ import annotations

import pytest

from decibench.connectors.demo import DemoConnector
from decibench.models import AudioBuffer, EventType


@pytest.mark.asyncio
async def test_demo_connector_connect():
    connector = DemoConnector()
    handle = await connector.connect("demo", {})
    assert handle.connector_type == "demo"


@pytest.mark.asyncio
async def test_demo_connector_roundtrip():
    connector = DemoConnector()
    handle = await connector.connect("demo", {})

    # Send some audio
    audio = AudioBuffer(data=b"\x00" * 3200, sample_rate=16000)
    await connector.send_audio(handle, audio)

    # Receive events
    events = []
    async for event in connector.receive_events(handle):
        events.append(event)

    assert len(events) > 0
    # Should have audio, transcript, and turn_end events
    event_types = {e.type for e in events}
    assert EventType.AGENT_AUDIO in event_types
    assert EventType.AGENT_TRANSCRIPT in event_types
    assert EventType.TURN_END in event_types


@pytest.mark.asyncio
async def test_demo_connector_disconnect():
    connector = DemoConnector()
    handle = await connector.connect("demo", {})

    audio = AudioBuffer(data=b"\x00" * 3200, sample_rate=16000)
    await connector.send_audio(handle, audio)

    async for _ in connector.receive_events(handle):
        pass

    summary = await connector.disconnect(handle)
    assert summary.duration_ms > 0
    assert summary.turn_count >= 1
    assert len(summary.agent_audio) > 0
    assert summary.platform_metadata.get("demo") is True
