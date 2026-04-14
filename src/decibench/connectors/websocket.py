"""WebSocket connector — the universal connector for most voice agents.

Covers: Vapi, Retell, ElevenLabs, Deepgram, Pipecat, OpenAI Realtime,
and any agent with a WebSocket endpoint that accepts/returns audio frames.
"""

from __future__ import annotations

import base64
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

# Default chunk size: 100ms of 16kHz 16-bit mono audio
_DEFAULT_CHUNK_BYTES = 3200
_RECV_TIMEOUT_SECONDS = 2.0


@register_connector("ws")
class WebSocketConnector(BaseConnector):
    """Connect to any voice agent via WebSocket.

    Sends raw audio frames, receives raw audio frames or JSON events.
    Handles both binary-only and mixed (binary + JSON text) protocols,
    including agents that wrap audio as base64 in JSON (OpenAI Realtime style).
    """

    # OpenAI Realtime API requires 24kHz; auto-detected on connect
    required_sample_rate: int = 24000
    required_encoding = BaseConnector.required_encoding

    def __init__(self, **kwargs: Any) -> None:
        self._ws: Any = None
        self._recorded_audio = bytearray()
        self._events: list[AgentEvent] = []
        self._transcript_parts: list[str] = []  # Agent-provided transcripts
        self._json_audio_mode = False
        self._send_count = 0  # Track send_audio calls for turn counting

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        try:
            import websockets
        except ImportError as e:
            msg = "websockets package required: pip install decibench"
            raise ImportError(msg) from e

        # Build connection URL
        url = target
        if not url.startswith(("ws://", "wss://")):
            url = f"ws://{url}"

        # Extract optional headers from config
        headers = config.get("websocket_headers", {})

        # Allow overriding sample rate from config
        if "sample_rate" in config:
            self.required_sample_rate = int(config["sample_rate"])

        logger.info("Connecting to WebSocket: %s", url)
        self._ws = await websockets.connect(
            url,
            additional_headers=headers,
            max_size=10 * 1024 * 1024,  # 10MB max message
            ping_interval=30,
            ping_timeout=30,
            close_timeout=10,
        )

        handle = ConnectionHandle(
            connector_type="ws",
            start_time_ns=time.monotonic_ns(),
            state={"url": url},
        )
        self._recorded_audio.clear()
        self._events.clear()
        self._transcript_parts.clear()
        self._json_audio_mode = False
        self._send_count = 0
        return handle

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        if self._ws is None:
            msg = "Not connected — call connect() first"
            raise RuntimeError(msg)

        import asyncio

        self._send_count += 1

        # Send audio in chunks to simulate real-time streaming
        chunk_size = _DEFAULT_CHUNK_BYTES
        data = audio.data
        for offset in range(0, len(data), chunk_size):
            chunk = data[offset : offset + chunk_size]
            await self._ws.send(chunk)
            # Pace sending to ~real-time to avoid overwhelming the agent
            await asyncio.sleep(0.02)

    async def receive_events(self, handle: ConnectionHandle) -> AsyncIterator[AgentEvent]:
        if self._ws is None:
            msg = "Not connected — call connect() first"
            raise RuntimeError(msg)

        import asyncio
        import json

        start_ns = handle.start_time_ns
        silence_count = 0
        max_silence = 2  # Stop after 2 consecutive timeouts (4s of silence = done)

        while silence_count < max_silence:
            try:
                message = await asyncio.wait_for(
                    self._ws.recv(),
                    timeout=_RECV_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                silence_count += 1
                continue
            except Exception:
                break

            silence_count = 0
            now_ms = (time.monotonic_ns() - start_ns) / 1_000_000

            if isinstance(message, bytes):
                self._recorded_audio.extend(message)
                event = AgentEvent(
                    type=EventType.AGENT_AUDIO,
                    timestamp_ms=now_ms,
                    audio=message,
                )
            elif isinstance(message, str):
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    data = {"raw": message}

                # Check for base64-encoded audio in JSON (OpenAI Realtime style)
                audio_bytes = self._extract_json_audio(data)
                if audio_bytes:
                    self._json_audio_mode = True
                    self._recorded_audio.extend(audio_bytes)
                    event = AgentEvent(
                        type=EventType.AGENT_AUDIO,
                        timestamp_ms=now_ms,
                        audio=audio_bytes,
                    )
                else:
                    event_type = self._classify_json_event(data)
                    # Capture agent-provided transcripts
                    if event_type == EventType.AGENT_TRANSCRIPT:
                        text = (
                            data.get("text", "")
                            or data.get("transcript", "")
                            or data.get("message", "")
                            or data.get("delta", "")
                        )
                        if text:
                            self._transcript_parts.append(text)
                    event = AgentEvent(
                        type=event_type,
                        timestamp_ms=now_ms,
                        data=data,
                    )
            else:
                continue

            self._events.append(event)
            yield event

    async def disconnect(self, handle: ConnectionHandle) -> CallSummary:
        duration_ms = (time.monotonic_ns() - handle.start_time_ns) / 1_000_000

        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                logger.debug("WebSocket close error (non-fatal)", exc_info=True)
            self._ws = None

        explicit_turns = sum(
            1 for e in self._events if e.type == EventType.TURN_END
        )
        # Use explicit turn events if available, otherwise count send_audio calls
        turn_count = explicit_turns if explicit_turns > 0 else self._send_count

        return CallSummary(
            duration_ms=duration_ms,
            turn_count=max(turn_count, 1),
            agent_audio=bytes(self._recorded_audio),
            events=list(self._events),
        )

    @staticmethod
    def _extract_json_audio(data: dict[str, Any]) -> bytes | None:
        """Extract base64-encoded audio from JSON message.

        Supports multiple common formats:
        - {"event": "media", "media": {"payload": "<base64>"}}  (Twilio/generic)
        - {"audio": "<base64>"}  (simple)
        - {"type": "response.audio.delta", "delta": "<base64>"}  (OpenAI Realtime)
        """
        # Twilio / generic media event format
        if data.get("event") == "media":
            payload = data.get("media", {}).get("payload")
            if payload:
                try:
                    return base64.b64decode(payload)
                except Exception:
                    return None

        # OpenAI Realtime API format
        if data.get("type") == "response.audio.delta":
            delta = data.get("delta")
            if delta:
                try:
                    return base64.b64decode(delta)
                except Exception:
                    return None

        # Simple base64 audio field
        if "audio" in data and isinstance(data["audio"], str):
            try:
                decoded = base64.b64decode(data["audio"])
                if len(decoded) > 100:  # Sanity check — actual audio data
                    return decoded
            except Exception:
                return None

        return None

    @staticmethod
    def _classify_json_event(data: dict[str, Any]) -> EventType:
        """Classify a JSON message into an EventType."""
        # Transcript events
        if "transcript" in data or "text" in data:
            return EventType.AGENT_TRANSCRIPT
        event = data.get("event", "")
        if event == "message":
            return EventType.AGENT_TRANSCRIPT
        msg_type = data.get("type", "")
        if "transcript" in msg_type:
            return EventType.AGENT_TRANSCRIPT
        # Tool events
        if "tool_call" in data or "function_call" in data:
            return EventType.TOOL_CALL
        if "tool_result" in data or "function_result" in data:
            return EventType.TOOL_RESULT
        # Interruption
        if "interrupt" in data or "barge_in" in data:
            return EventType.INTERRUPTION
        # Error
        if "error" in data:
            return EventType.ERROR
        return EventType.METADATA
