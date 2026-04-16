"""Shared bridge-based connector base for native Retell / Vapi adapters.

Both connectors share the same architecture: spawn the Decibench bridge
sidecar, open the WebSocket, and translate the bridge protocol's events into
`AgentEvent` / `CallSummary` shapes the Decibench orchestrator already
understands.

Concrete subclasses only have to set `platform_name` and pull the right
credentials out of the auth config.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from decibench.bridge import (
    BridgeClient,
    BridgeError,
    BridgeFatalError,
    BridgeMessageType,
)
from decibench.connectors.base import BaseConnector
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


# Map from bridge protocol events → Decibench EventType.
_BRIDGE_TO_EVENT: dict[BridgeMessageType, EventType] = {
    BridgeMessageType.AGENT_AUDIO: EventType.AGENT_AUDIO,
    BridgeMessageType.AGENT_TRANSCRIPT: EventType.AGENT_TRANSCRIPT,
    BridgeMessageType.TOOL_CALL: EventType.TOOL_CALL,
    BridgeMessageType.TOOL_RESULT: EventType.TOOL_RESULT,
    BridgeMessageType.INTERRUPTION: EventType.INTERRUPTION,
    BridgeMessageType.TURN_END: EventType.TURN_END,
    BridgeMessageType.METADATA: EventType.METADATA,
    BridgeMessageType.ERROR: EventType.ERROR,
}


class BridgeConnector(BaseConnector):
    """Base class for all bridge-backed native connectors.

    Subclasses must set `platform_name` and override `extract_credentials()`
    to pull the right auth fields out of the Decibench config.
    """

    platform_name: str = ""
    target_uri_prefix: str = ""

    def __init__(self, **kwargs: Any) -> None:
        self._client: BridgeClient | None = None
        self._session_id: str | None = None
        self._negotiated_sample_rate: int = 16000
        self._collected_audio: bytearray = bytearray()
        self._events_buffer: list[AgentEvent] = []
        self._consumer_task: asyncio.Task[None] | None = None
        self._stop_consumer = asyncio.Event()
        self._receive_queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

    # ----------------------------------------------------------- subclass hooks

    def extract_credentials(self, target: str, config: dict[str, Any]) -> dict[str, Any]:
        """Subclasses override to pull platform-specific credentials.

        The default looks for `<platform>_api_key` and falls back to env vars.
        """
        env_key = f"{self.platform_name.upper()}_API_KEY"
        api_key = (
            config.get(f"{self.platform_name}_api_key")
            or os.environ.get(env_key, "")
        )
        return {"api_key": api_key} if api_key else {}

    def parse_agent_id(self, target: str) -> str:
        prefix = self.target_uri_prefix or f"{self.platform_name}://"
        if not target.startswith(prefix):
            raise ValueError(
                f"{self.platform_name} connector expected a {prefix}<agent_id> target, got: {target!r}"
            )
        return target[len(prefix):].strip()

    # -------------------------------------------------------------- BaseConnector

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        agent_id = self.parse_agent_id(target)
        credentials = self.extract_credentials(target, config)
        if not credentials.get("api_key") and not credentials.get("public_key"):
            raise ValueError(
                f"{self.platform_name} connector needs an API key. Set "
                f"{self.platform_name}_api_key in decibench.toml [auth] or "
                f"export {self.platform_name.upper()}_API_KEY."
            )

        self._client = BridgeClient()
        try:
            await self._client.start()
            connected = await self._client.connect(
                self.platform_name,
                agent_id,
                credentials=credentials,
                sample_rate=self.required_sample_rate,
            )
        except (BridgeError, BridgeFatalError):
            await self._client.stop()
            self._client = None
            raise

        self._session_id = connected.get("session_id", "")
        audio_meta = connected.get("audio", {})
        self._negotiated_sample_rate = int(audio_meta.get("sample_rate", self.required_sample_rate))

        # Background consumer pumps the bridge's event stream so that
        # send_audio / receive_events can stay async-friendly.
        self._stop_consumer.clear()
        self._consumer_task = asyncio.create_task(self._consume_bridge_events())

        handle = ConnectionHandle(connector_type=self.platform_name)
        handle.state["session_id"] = self._session_id
        handle.state["sample_rate"] = self._negotiated_sample_rate
        return handle

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        if self._client is None:
            raise RuntimeError(f"{self.platform_name} connector not connected")
        await self._client.send_audio_chunk(audio.data)

    async def receive_events(self, handle: ConnectionHandle) -> AsyncIterator[AgentEvent]:
        # Drain anything that has accumulated since the last send_audio() and
        # also wait briefly for `turn_end`. The orchestrator iterates this
        # generator until it's exhausted, so we exit when we either see TURN_END
        # or a short idle gap with no new events.
        if self._client is None:
            return

        # Tell the bridge that the caller turn is over so that the SDK starts
        # producing the agent's response.
        await self._client.end_turn()

        last_event_at = time.monotonic()
        idle_grace_s = 1.5
        max_wait_s = 30.0
        deadline = last_event_at + max_wait_s

        while time.monotonic() < deadline:
            try:
                remaining = max(0.05, deadline - time.monotonic())
                event = await asyncio.wait_for(
                    self._receive_queue.get(), timeout=min(idle_grace_s, remaining)
                )
            except TimeoutError:
                # No events for `idle_grace_s` — assume the agent is done.
                break
            if event is None:
                # Sentinel: the consumer has stopped (disconnect or fatal).
                break
            self._events_buffer.append(event)
            if event.audio:
                self._collected_audio.extend(event.audio)
            yield event
            last_event_at = time.monotonic()
            if event.type == EventType.TURN_END:
                break

    async def disconnect(self, handle: ConnectionHandle) -> CallSummary:
        if self._client is None:
            return CallSummary(duration_ms=0, turn_count=0)

        with suppress(Exception):
            await self._client.disconnect()

        # Signal the consumer to stop draining.
        self._stop_consumer.set()
        if self._consumer_task is not None:
            with suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(self._consumer_task, timeout=5.0)

        bridge_logs = self._client.stderr_log
        await self._client.stop()
        self._client = None

        duration_ms = (time.monotonic_ns() - handle.start_time_ns) / 1_000_000
        turn_count = sum(1 for e in self._events_buffer if e.type == EventType.TURN_END)

        summary = CallSummary(
            duration_ms=duration_ms,
            turn_count=turn_count,
            agent_audio=bytes(self._collected_audio),
            events=list(self._events_buffer),
            platform_metadata={
                f"{self.platform_name}_session_id": self._session_id,
                "bridge_sample_rate": self._negotiated_sample_rate,
                "bridge_logs": bridge_logs[-50:],  # tail only — full log is too noisy
            },
        )
        # Reset for any next call on the same connector instance.
        self._collected_audio = bytearray()
        self._events_buffer = []
        self._session_id = None
        return summary

    # ------------------------------------------------------------------ internal

    async def _consume_bridge_events(self) -> None:
        """Pump events from BridgeClient.events() into our internal queue."""
        if self._client is None:
            return
        try:
            async for ev in self._client.events():
                if self._stop_consumer.is_set():
                    break
                event_type = _BRIDGE_TO_EVENT.get(ev.type)
                if event_type is None:
                    continue
                agent_event = AgentEvent(
                    type=event_type,
                    timestamp_ms=ev.ts_ms,
                    data=ev.data,
                    audio=ev.audio,
                )
                await self._receive_queue.put(agent_event)
        except BridgeFatalError as exc:
            logger.error("Bridge fatal error: %s", exc)
            await self._receive_queue.put(
                AgentEvent(
                    type=EventType.ERROR,
                    timestamp_ms=time.monotonic() * 1000,
                    data={"code": exc.code, "message": exc.message, "fatal": True},
                )
            )
        except Exception as exc:
            logger.exception("Bridge event consumer crashed: %s", exc)
        finally:
            # Sentinel so receive_events() stops blocking.
            await self._receive_queue.put(None)
