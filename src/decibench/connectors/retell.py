"""Retell connector — connect to live Retell agents.

Note: Native Retell web calls use LiveKit WebRTC under the hood.
This connector initiates the web call via HTTP, but full audio media bridging
requires a LiveKit WebRTC stack not currently bundled in v1.0.
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

@register_connector("retell")
class RetellConnector(BaseConnector):
    """Connect to a Retell agent."""

    def __init__(self, **kwargs: Any) -> None:
        self._call_id: str | None = None
        self._access_token: str | None = None

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        # e.g. retell://agent-id-123
        agent_id = target.replace("retell://", "")

        api_key = config.get("retell_api_key")
        if not api_key:
            import os
            api_key = os.environ.get("RETELL_API_KEY")
        if not api_key:
            raise ValueError("retell_api_key is required in config or RETELL_API_KEY env var")

        logger.info(f"Initiating Retell Web Call to agent: {agent_id}")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://api.retellai.com/v2/create-web-call",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"agent_id": agent_id}
                )
                response.raise_for_status()
                data = response.json()
                self._call_id = data.get("call_id")
                self._access_token = data.get("access_token")
            except httpx.HTTPError as e:
                logger.error(f"Failed to initiate Retell call: {e}")
                raise RuntimeError(f"Retell API Error: {e}") from e

        if not self._access_token:
            raise RuntimeError("Retell API did not return an access_token")

        logger.info(f"Retell call initiated: {self._call_id}")

        return ConnectionHandle(
            connector_type="retell",
            start_time_ns=time.monotonic_ns(),
            state={"agent_id": agent_id, "call_id": self._call_id, "token": self._access_token},
        )

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        raise NotImplementedError(
            "Full WebRTC media bridging (LiveKit) for Retell is required to stream raw audio. "
            "Please use the PSTN connector or the generic WebRTC bridge module."
        )

    async def receive_events(self, handle: ConnectionHandle) -> AsyncIterator[AgentEvent]:
        raise NotImplementedError("Requires LiveKit WebRTC streaming.")
        if False:  # pragma: no cover
            yield AgentEvent(type=EventType.METADATA, timestamp_ms=0.0, data={})

    async def disconnect(self, handle: ConnectionHandle) -> CallSummary:
        return CallSummary(
            duration_ms=(time.monotonic_ns() - handle.start_time_ns) / 1_000_000,
            turn_count=0,
            agent_audio=b"",
            events=[],
            platform_metadata={"retell_call_id": self._call_id}
        )
