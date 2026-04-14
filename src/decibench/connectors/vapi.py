"""Vapi connector — connect to live Vapi agents.

Note: Native Vapi web calls use Daily.co WebRTC under the hood.
This connector initiates the web call via HTTP, but full audio media bridging
requires a WebRTC stack wrapper not currently bundled in v1.0.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from decibench.connectors.base import BaseConnector
from decibench.connectors.registry import register_connector
from decibench.models import (
    AgentEvent,
    AudioBuffer,
    CallSummary,
    ConnectionHandle,
    EventType,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

@register_connector("vapi")
class VapiConnector(BaseConnector):
    """Connect to a Vapi agent."""

    def __init__(self, **kwargs: Any) -> None:
        self._call_id: str | None = None
        self._web_call_url: str | None = None

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        # Fail fast: audio streaming is not yet implemented.
        # Raising here prevents initiating a billable API call that would
        # immediately crash on send_audio/receive_events anyway.
        msg = (
            "Vapi connector requires WebRTC media bridging (Daily.co) which is not yet "
            "implemented in Decibench v1.0. Use the generic WebSocket connector with your "
            "Vapi agent's WebSocket endpoint, or the demo connector for testing.\n"
            "Track progress: https://github.com/decibench/decibench/issues"
        )
        raise NotImplementedError(msg)

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        raise NotImplementedError(
            "Full WebRTC media bridging (Daily.co) for Vapi is required to stream raw audio. "
            "Please use the PSTN connector or the generic WebRTC bridge module."
        )

    async def receive_events(self, handle: ConnectionHandle) -> AsyncIterator[AgentEvent]:
        raise NotImplementedError("Requires WebRTC streaming.")
        if False:  # pragma: no cover
            yield AgentEvent(type=EventType.METADATA, timestamp_ms=0.0, data={})

    async def disconnect(self, handle: ConnectionHandle) -> CallSummary:
        return CallSummary(
            duration_ms=(time.monotonic_ns() - handle.start_time_ns) / 1_000_000,
            turn_count=0,
            agent_audio=b"",
            events=[],
            platform_metadata={"vapi_call_id": self._call_id}
        )
