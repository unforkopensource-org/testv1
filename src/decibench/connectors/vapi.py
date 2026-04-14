"""Vapi connector — connect to live Vapi agents.

Note: Native Vapi web calls use Daily.co WebRTC under the hood.
This connector initiates the web call via HTTP, but full audio media bridging
requires a WebRTC stack wrapper not currently bundled in v1.0.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

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
        # e.g. vapi://agent-id-123
        agent_id = target.replace("vapi://", "")

        api_key = config.get("vapi_api_key")
        if not api_key:
            import os
            api_key = os.environ.get("VAPI_API_KEY")
        if not api_key:
            raise ValueError("vapi_api_key is required in config or VAPI_API_KEY env var")

        logger.info(f"Initiating Vapi Web Call to agent: {agent_id}")

        # Initiate the call
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://api.vapi.ai/call/web",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"assistantId": agent_id}
                )
                response.raise_for_status()
                data = response.json()
                self._call_id = data.get("id")
                self._web_call_url = data.get("webCallUrl")
            except httpx.HTTPError as e:
                logger.error(f"Failed to initiate Vapi call: {e}")
                raise RuntimeError(f"Vapi API Error: {e}") from e

        if not self._web_call_url:
            raise RuntimeError("Vapi API did not return a webCallUrl")

        logger.info(f"Vapi call initiated: {self._call_id}")

        return ConnectionHandle(
            connector_type="vapi",
            start_time_ns=time.monotonic_ns(),
            state={"agent_id": agent_id, "call_id": self._call_id, "url": self._web_call_url},
        )

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
