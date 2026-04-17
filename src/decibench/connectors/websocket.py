"""WebSocket connector — the universal connector for most voice agents.

Covers: Vapi, Retell, ElevenLabs, Deepgram, Pipecat, OpenAI Realtime,
Gemini Live, Twilio MediaStreams, and any agent with a WebSocket endpoint.

Protocol behavior is configurable via ``ws_protocol`` preset or individual keys:

- ``ws_protocol``       — preset name: ``"auto"``, ``"raw-pcm"``,
                          ``"openai-realtime"``, ``"twilio"``,
                          ``"gemini-live"`` (default: ``"auto"``)
- ``sample_rate``       — audio sample rate in Hz (default: 16000)
- ``websocket_headers`` — dict of extra HTTP headers for the WS handshake
- ``ws_send_format``    — ``"binary"`` (default), ``"json_base64"``, or
                          ``"json_bytes"``
- ``ws_commit_message`` — JSON string to send after each caller turn to
                          signal end-of-turn (default: none)
- ``ws_setup_message``  — JSON string to send immediately after connect
                          (default: none)
- ``ws_recv_timeout``   — per-message receive timeout in seconds (default: 2.0)
- ``ws_silence_max``    — number of consecutive recv timeouts that signal the
                          agent is done (default: 2)
"""

from __future__ import annotations

import asyncio
import base64
import json as _json
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
_DEFAULT_RECV_TIMEOUT_SECONDS = 2.0
_DEFAULT_SILENCE_MAX = 2

# ---------------------------------------------------------------------------
# Protocol presets — known configurations for popular voice agent platforms
# ---------------------------------------------------------------------------
PROTOCOL_PRESETS: dict[str, dict[str, Any]] = {
    "raw-pcm": {
        "sample_rate": 16000,
        "ws_send_format": "binary",
        "ws_recv_timeout": 2.0,
        "ws_silence_max": 2,
    },
    "openai-realtime": {
        "sample_rate": 24000,
        "ws_send_format": "json_base64",
        "ws_commit_message": '{"type": "input_audio_buffer.commit"}',
        "ws_recv_timeout": 3.0,
        "ws_silence_max": 3,
    },
    "twilio": {
        "sample_rate": 8000,
        "ws_send_format": "json_base64",
        "ws_recv_timeout": 5.0,
        "ws_silence_max": 3,
    },
    "gemini-live": {
        "sample_rate": 16000,
        "ws_send_format": "json_base64",
        "ws_recv_timeout": 5.0,
        "ws_silence_max": 3,
    },
}


def _detect_protocol_from_message(data: dict[str, Any]) -> str | None:
    """Fingerprint a JSON message to identify the agent protocol.

    Returns a preset name if recognized, or None.
    """
    msg_type = data.get("type", "")

    # OpenAI Realtime: first message is {"type": "session.created", ...}
    if msg_type == "session.created" or msg_type == "session.update":
        return "openai-realtime"

    # Twilio MediaStreams: first message is {"event": "connected", ...}
    event = data.get("event", "")
    if event in ("connected", "start"):
        stream_sid = data.get("streamSid") or data.get("start", {}).get("streamSid")
        if stream_sid or event == "connected":
            return "twilio"

    # Gemini Live: first message contains setupComplete or serverContent
    if "setupComplete" in data or msg_type == "setupComplete":
        return "gemini-live"
    if "serverContent" in data:
        return "gemini-live"

    return None


@register_connector("ws")
class WebSocketConnector(BaseConnector):
    """Connect to any voice agent via WebSocket.

    Sends raw audio frames, receives raw audio frames or JSON events.
    Handles both binary-only and mixed (binary + JSON text) protocols,
    including agents that wrap audio as base64 in JSON (OpenAI Realtime style).

    Use ``ws_protocol`` to pick a preset or ``"auto"`` to detect automatically.
    """

    required_sample_rate: int = 16000
    required_encoding = BaseConnector.required_encoding

    def __init__(self, **kwargs: Any) -> None:
        self._ws: Any = None
        self._recorded_audio = bytearray()
        self._events: list[AgentEvent] = []
        self._transcript_parts: list[str] = []
        self._json_audio_mode = False
        self._send_count = 0
        # Protocol config — set in connect()
        self._send_format: str = "binary"
        self._commit_message: dict[str, Any] | None = None
        self._recv_timeout: float = _DEFAULT_RECV_TIMEOUT_SECONDS
        self._silence_max: int = _DEFAULT_SILENCE_MAX
        # Buffered initial message captured during auto-detect
        self._initial_message: bytes | str | None = None
        self._detected_protocol: str | None = None

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        import websockets

        # Build connection URL
        url = target
        if not url.startswith(("ws://", "wss://")):
            url = f"ws://{url}"

        # Extract optional headers from config
        headers = config.get("websocket_headers", {})

        # ----- Resolve protocol preset -----
        protocol = str(config.get("ws_protocol", "auto"))

        if protocol != "auto" and protocol in PROTOCOL_PRESETS:
            # Explicit preset: apply its defaults, then let user config override
            preset = PROTOCOL_PRESETS[protocol]
            effective = {**preset}
            for key in ("sample_rate", "ws_send_format", "ws_commit_message",
                        "ws_setup_message", "ws_recv_timeout", "ws_silence_max"):
                if key in config and config[key] != "":
                    effective[key] = config[key]
        else:
            # auto or unknown: start with raw-pcm defaults, detect after connect
            effective = dict(config)

        # Apply sample rate
        if "sample_rate" in effective:
            self.required_sample_rate = int(effective["sample_rate"])

        # Apply protocol settings
        self._send_format = str(effective.get("ws_send_format", "binary"))
        self._recv_timeout = float(effective.get("ws_recv_timeout", _DEFAULT_RECV_TIMEOUT_SECONDS))
        self._silence_max = int(effective.get("ws_silence_max", _DEFAULT_SILENCE_MAX))

        # Parse optional commit / setup messages
        raw_commit = effective.get("ws_commit_message")
        if isinstance(raw_commit, str) and raw_commit:
            self._commit_message = _json.loads(raw_commit)
        elif isinstance(raw_commit, dict):
            self._commit_message = raw_commit
        else:
            self._commit_message = None

        raw_setup = effective.get("ws_setup_message")

        logger.info("Connecting to WebSocket: %s (protocol=%s, send_format=%s, sample_rate=%d)",
                     url, protocol, self._send_format, self.required_sample_rate)

        try:
            self._ws = await websockets.connect(
                url,
                additional_headers=headers,
                max_size=10 * 1024 * 1024,  # 10MB max message
                ping_interval=30,
                ping_timeout=30,
                close_timeout=10,
            )
        except Exception as exc:
            msg = (
                f"WebSocket connection to {url} failed: {exc}. "
                "Check that the target URL is correct and the agent is running."
            )
            raise ConnectionError(msg) from exc

        # Send optional setup/session-init message right after connect
        if raw_setup:
            setup_text = raw_setup if isinstance(raw_setup, str) else _json.dumps(raw_setup)
            await self._ws.send(setup_text)
            logger.debug("Sent setup message: %s", setup_text[:200])

        # ----- Auto-detect protocol if needed -----
        self._initial_message = None
        self._detected_protocol = protocol if protocol != "auto" else None

        if protocol == "auto":
            await self._auto_detect_protocol()

        handle = ConnectionHandle(
            connector_type="ws",
            start_time_ns=time.monotonic_ns(),
            state={"url": url, "protocol": self._detected_protocol or protocol},
        )
        self._recorded_audio.clear()
        self._events.clear()
        self._transcript_parts.clear()
        self._json_audio_mode = False
        self._send_count = 0
        return handle

    async def _auto_detect_protocol(self) -> None:
        """Try to read one initial message to fingerprint the agent protocol.

        If the server sends a greeting/session message within 3 seconds, we
        use it to pick a protocol preset. The message is buffered and replayed
        in ``receive_events``. If nothing arrives, we stay on raw-pcm defaults.
        """
        try:
            message = await asyncio.wait_for(self._ws.recv(), timeout=3.0)
        except (TimeoutError, Exception):
            # No greeting — agent waits for audio first. Keep raw-pcm defaults.
            logger.debug("Auto-detect: no initial message, using raw-pcm defaults")
            self._detected_protocol = "raw-pcm"
            return

        # Buffer the message so receive_events can replay it
        self._initial_message = message

        detected: str | None = None

        if isinstance(message, str):
            try:
                data = _json.loads(message)
                detected = _detect_protocol_from_message(data)
            except _json.JSONDecodeError:
                pass

            if detected:
                logger.info("Auto-detected protocol: %s", detected)
                self._detected_protocol = detected
                self._apply_preset(detected)
                return

            # Got JSON but didn't match a known pattern — try json_base64
            # sending since the server clearly speaks JSON.
            logger.info("Auto-detect: server speaks JSON, switching to json_base64 send format")
            self._send_format = "json_base64"
            self._detected_protocol = "json-detected"
            return

        if isinstance(message, bytes):
            # Server sent binary first — it speaks raw PCM
            logger.debug("Auto-detect: server sent binary, using raw-pcm")
            self._detected_protocol = "raw-pcm"

    def _apply_preset(self, preset_name: str) -> None:
        """Apply a protocol preset, updating internal state."""
        preset = PROTOCOL_PRESETS.get(preset_name)
        if not preset:
            return

        self.required_sample_rate = int(preset.get("sample_rate", self.required_sample_rate))
        self._send_format = str(preset.get("ws_send_format", self._send_format))
        self._recv_timeout = float(preset.get("ws_recv_timeout", self._recv_timeout))
        self._silence_max = int(preset.get("ws_silence_max", self._silence_max))

        raw_commit = preset.get("ws_commit_message")
        if isinstance(raw_commit, str) and raw_commit:
            self._commit_message = _json.loads(raw_commit)
        elif isinstance(raw_commit, dict):
            self._commit_message = raw_commit

        logger.info(
            "Applied preset '%s': send_format=%s, sample_rate=%d, recv_timeout=%.1f",
            preset_name, self._send_format, self.required_sample_rate, self._recv_timeout,
        )

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        if self._ws is None:
            msg = "Not connected — call connect() first"
            raise RuntimeError(msg)

        self._send_count += 1

        # Send audio in chunks to simulate real-time streaming
        chunk_size = _DEFAULT_CHUNK_BYTES
        data = audio.data
        for offset in range(0, len(data), chunk_size):
            chunk = data[offset : offset + chunk_size]
            if self._send_format == "json_base64":
                payload = _json.dumps({"audio": base64.b64encode(chunk).decode()})
                await self._ws.send(payload)
            elif self._send_format == "json_bytes":
                payload = _json.dumps({"audio": list(chunk)})
                await self._ws.send(payload)
            else:
                await self._ws.send(chunk)
            # Pace sending to ~real-time to avoid overwhelming the agent
            await asyncio.sleep(0.02)

        # Send explicit end-of-turn commit if configured
        if self._commit_message is not None:
            await self._ws.send(_json.dumps(self._commit_message))
            logger.debug("Sent commit message after caller turn")

    async def receive_events(self, handle: ConnectionHandle) -> AsyncIterator[AgentEvent]:
        if self._ws is None:
            msg = "Not connected — call connect() first"
            raise RuntimeError(msg)

        start_ns = handle.start_time_ns
        silence_count = 0

        # Replay the initial message captured during auto-detect
        if self._initial_message is not None:
            event = self._parse_message(self._initial_message, start_ns)
            if event is not None:
                self._events.append(event)
                yield event
            self._initial_message = None

        while silence_count < self._silence_max:
            try:
                message = await asyncio.wait_for(
                    self._ws.recv(),
                    timeout=self._recv_timeout,
                )
            except TimeoutError:
                silence_count += 1
                continue
            except Exception as exc:
                logger.debug("WebSocket receive ended: %s", exc)
                break

            silence_count = 0
            event = self._parse_message(message, start_ns)
            if event is None:
                continue

            self._events.append(event)
            yield event

    def _parse_message(self, message: bytes | str, start_ns: int) -> AgentEvent | None:
        """Parse a single WebSocket message into an AgentEvent."""
        now_ms = (time.monotonic_ns() - start_ns) / 1_000_000

        if isinstance(message, bytes):
            self._recorded_audio.extend(message)
            return AgentEvent(
                type=EventType.AGENT_AUDIO,
                timestamp_ms=now_ms,
                audio=message,
            )

        if isinstance(message, str):
            try:
                data = _json.loads(message)
            except _json.JSONDecodeError:
                data = {"raw": message}

            # Check for base64-encoded audio in JSON (OpenAI Realtime style)
            audio_bytes = self._extract_json_audio(data)
            if audio_bytes:
                self._json_audio_mode = True
                self._recorded_audio.extend(audio_bytes)
                return AgentEvent(
                    type=EventType.AGENT_AUDIO,
                    timestamp_ms=now_ms,
                    audio=audio_bytes,
                )

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
            return AgentEvent(
                type=event_type,
                timestamp_ms=now_ms,
                data=data,
            )

        return None

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
        - {"serverContent": {"modelTurn": {"parts": [{"inlineData": {"data": "<base64>"}}]}}} (Gemini)
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

        # Gemini Live API format
        server_content = data.get("serverContent")
        if isinstance(server_content, dict):
            model_turn = server_content.get("modelTurn", {})
            parts = model_turn.get("parts", [])
            for part in parts:
                inline = part.get("inlineData", {})
                b64 = inline.get("data")
                if b64:
                    try:
                        return base64.b64decode(b64)
                    except Exception:
                        logger.debug("Failed to decode Gemini inlineData part")
                        continue

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
