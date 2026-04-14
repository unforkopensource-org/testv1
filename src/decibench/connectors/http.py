"""HTTP connector — for batch/REST-based voice agents.

Sends audio as a file upload, receives audio + metadata in response.
Suitable for non-realtime agents that process entire utterances at once.
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

_REQUEST_TIMEOUT = 30.0


@register_connector("http")
class HTTPConnector(BaseConnector):
    """Connect to voice agents via HTTP POST.

    Sends entire audio as a request body or multipart upload.
    Receives agent audio + optional JSON metadata in response.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._response_audio: bytes = b""
        self._response_metadata: dict[str, Any] = {}
        self._events: list[AgentEvent] = []
        self._send_time_ns: int = 0

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        # Ensure httpx is available (core dependency)
        url = target
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"

        handle = ConnectionHandle(
            connector_type="http",
            start_time_ns=time.monotonic_ns(),
            state={
                "url": url,
                "headers": config.get("http_headers", {}),
                "auth_token": config.get("auth_token", ""),
            },
        )
        self._response_audio = b""
        self._response_metadata = {}
        self._events.clear()
        return handle

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        import httpx

        url = handle.state["url"]
        headers: dict[str, str] = dict(handle.state.get("headers", {}))
        auth_token = handle.state.get("auth_token", "")
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        self._send_time_ns = time.monotonic_ns()

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                url,
                content=audio.data,
                headers={
                    "Content-Type": "application/octet-stream",
                    **headers,
                },
            )
            response.raise_for_status()

            receive_time_ns = time.monotonic_ns()
            latency_ms = (receive_time_ns - self._send_time_ns) / 1_000_000

            content_type = response.headers.get("content-type", "")

            if "application/json" in content_type:
                data = response.json()
                self._response_metadata = data
                # Audio might be base64-encoded in JSON
                if "audio" in data:
                    import base64
                    self._response_audio = base64.b64decode(data["audio"])
            else:
                self._response_audio = response.content

            # Create events from response
            if self._response_audio:
                self._events.append(AgentEvent(
                    type=EventType.AGENT_AUDIO,
                    timestamp_ms=latency_ms,
                    audio=self._response_audio,
                ))

            if self._response_metadata:
                self._events.append(AgentEvent(
                    type=EventType.METADATA,
                    timestamp_ms=latency_ms,
                    data=self._response_metadata,
                ))

    async def receive_events(self, handle: ConnectionHandle) -> AsyncIterator[AgentEvent]:
        for event in self._events:
            yield event

    async def disconnect(self, handle: ConnectionHandle) -> CallSummary:
        duration_ms = (time.monotonic_ns() - handle.start_time_ns) / 1_000_000

        return CallSummary(
            duration_ms=duration_ms,
            turn_count=1,
            agent_audio=self._response_audio,
            events=list(self._events),
            platform_metadata=self._response_metadata,
        )
