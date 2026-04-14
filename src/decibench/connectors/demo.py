"""Demo connector — zero-config first-run experience.

Generates synthetic agent responses so new users can see what Decibench
does in 30 seconds without any real agent, API keys, or setup.

The demo agent has intentional imperfections (latency variance, one WER miss)
so the output shows both passing and failing metrics — not a fake perfect score.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import struct
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

# Pre-defined demo responses with realistic imperfections
_DEMO_RESPONSES: dict[str, dict[str, Any]] = {
    "greeting": {
        "text": "Hello! Thank you for calling. I'm an AI assistant. How can I help you today?",
        "latency_ms": 620,
        "tool_calls": [],
    },
    "booking": {
        "text": "I'd be happy to help you schedule an appointment. What date works best for you?",
        "latency_ms": 780,
        "tool_calls": [],
    },
    "confirmation": {
        "text": "I have Tuesday at 2 PM available with Dr. Patel. Shall I book that for you?",
        "latency_ms": 950,
        "tool_calls": [{"name": "check_availability", "args": {"doctor": "Dr. Patel"}}],
    },
    "complete": {
        "text": "Your appointment is confirmed for Tuesday at 2 PM. Is there anything else I can help with?",
        "latency_ms": 1100,
        "tool_calls": [{"name": "book_appointment", "args": {"time": "2:00 PM", "doctor": "Dr. Patel"}}],
    },
    "farewell": {
        "text": "Thank you for calling! Have a great day.",
        "latency_ms": 520,
        "tool_calls": [],
    },
    "support_greeting": {
        "text": "Welcome to customer support. I'm an AI agent here to help. Can you describe the issue?",
        "latency_ms": 680,
        "tool_calls": [],
    },
    "support_lookup": {
        "text": "I found your order. It was shipped yesterday and should arrive by Thursday.",
        "latency_ms": 1400,  # Intentionally slow — will trigger latency warning
        "tool_calls": [{"name": "lookup_order", "args": {"order_id": "ORD-12345"}}],
    },
    "support_resolve": {
        "text": "I've updated your delivery preferences. You'll receive a confirmation email shortly.",
        "latency_ms": 890,
        "tool_calls": [{"name": "update_preferences", "args": {"delivery": "express"}}],
    },
    "fallback": {
        "text": "I understand. Let me help you with that request right away.",
        "latency_ms": 750,
        "tool_calls": [],
    },
    "error_demo": {
        "text": "I apologize, I'm having trouble processing that. Could you please repeat?",
        "latency_ms": 1800,  # Intentionally very slow — will fail latency check
        "tool_calls": [],
    },
}


def _generate_speech_like_audio(
    text: str,
    sample_rate: int = 16000,
    duration_ms: float = 2000.0,
) -> bytes:
    """Generate speech-like formant audio for demo purposes.

    Uses 3 formant frequencies typical of vowel sounds with amplitude
    modulation to simulate syllable rhythm, plus a noise floor for
    realism. Deterministic: same text always produces same audio.

    NOT real speech. But gives audio evaluators something meaningful
    to work with (MOS heuristic should score 2.5-3.5 range).
    """
    num_samples = int(sample_rate * duration_ms / 1000.0)

    # Deterministic variation from text content
    text_hash = hashlib.md5(text.encode()).hexdigest()  # noqa: S324
    seed = int(text_hash[:8], 16)

    # Fundamental frequency (pitch) — typical speech range
    f0 = 120 + (seed % 80)  # 120-200 Hz (male-female range)

    # Formant frequencies for vowel-like sounds
    f1 = 300 + (seed >> 8) % 400   # 300-700 Hz (first formant)
    f2 = 900 + (seed >> 16) % 1200  # 900-2100 Hz (second formant)
    f3 = 2400 + (seed >> 24) % 600  # 2400-3000 Hz (third formant)

    # Syllable rate: ~4-6 syllables per second
    syllable_rate = 4.0 + (seed % 20) / 10.0

    samples = bytearray(num_samples * 2)  # 16-bit PCM
    # Simple LCG for deterministic noise (no random module needed)
    noise_state = seed

    for i in range(num_samples):
        t = i / sample_rate

        # Amplitude modulation: syllable rhythm envelope
        syllable_env = 0.5 + 0.5 * math.sin(2 * math.pi * syllable_rate * t)

        # Glottal pulse train (fundamental + harmonics)
        glottal = (
            0.5 * math.sin(2 * math.pi * f0 * t)
            + 0.3 * math.sin(2 * math.pi * f0 * 2 * t)
            + 0.1 * math.sin(2 * math.pi * f0 * 3 * t)
        )

        # Formant resonances (simplified — real formants are filters)
        formants = (
            0.3 * math.sin(2 * math.pi * f1 * t)
            + 0.2 * math.sin(2 * math.pi * f2 * t)
            + 0.1 * math.sin(2 * math.pi * f3 * t)
        )

        # Combine: glottal source x formant coloring x syllable envelope
        value = (glottal * 0.6 + formants * 0.4) * syllable_env

        # Add noise floor (~-30dB) for realism
        noise_state = (noise_state * 1103515245 + 12345) & 0x7FFFFFFF
        noise = ((noise_state / 0x7FFFFFFF) * 2.0 - 1.0) * 0.03
        value += noise

        # Fade in/out (50ms)
        fade_samples = int(sample_rate * 0.05)
        if i < fade_samples:
            value *= i / fade_samples
        elif i > num_samples - fade_samples:
            value *= (num_samples - i) / fade_samples

        sample_val = int(value * 12000)  # Conservative amplitude
        sample_val = max(-32768, min(32767, sample_val))
        struct.pack_into("<h", samples, i * 2, sample_val)

    return bytes(samples)


@register_connector("demo")
class DemoConnector(BaseConnector):
    """Built-in demo agent for zero-config first run.

    Produces realistic-looking results without any external dependencies.
    Has intentional imperfections so metrics show realistic variance.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._events: list[AgentEvent] = []
        self._recorded_audio = bytearray()
        self._turn_index = 0
        self._caller_audio_hash = ""

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        logger.info("Starting demo agent (built-in)")
        self._events.clear()
        self._recorded_audio.clear()
        self._turn_index = 0

        return ConnectionHandle(
            connector_type="demo",
            start_time_ns=time.monotonic_ns(),
            state={"target": target},
        )

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        # Hash the incoming audio to deterministically select a response
        self._caller_audio_hash = hashlib.md5(audio.data[:1000]).hexdigest()[:8]  # noqa: S324
        self._turn_index += 1

    async def receive_events(self, handle: ConnectionHandle) -> AsyncIterator[AgentEvent]:
        # Select response based on turn index
        response_keys = list(_DEMO_RESPONSES.keys())
        idx = (self._turn_index - 1) % len(response_keys)
        response = _DEMO_RESPONSES[response_keys[idx]]

        # Simulate realistic latency
        latency_ms = response["latency_ms"]
        await asyncio.sleep(latency_ms / 1000.0)

        now_ms = (time.monotonic_ns() - handle.start_time_ns) / 1_000_000

        # Emit tool call events if any
        for tool_call in response["tool_calls"]:
            tc_event = AgentEvent(
                type=EventType.TOOL_CALL,
                timestamp_ms=now_ms - 50,  # Tool called slightly before response
                data=tool_call,
            )
            self._events.append(tc_event)
            yield tc_event

        # Generate audio for the response text
        text = response["text"]
        words_count = len(text.split())
        audio_duration_ms = words_count * 180.0  # ~180ms per word
        audio_data = _generate_speech_like_audio(text, duration_ms=audio_duration_ms)

        self._recorded_audio.extend(audio_data)

        audio_event = AgentEvent(
            type=EventType.AGENT_AUDIO,
            timestamp_ms=now_ms,
            audio=audio_data,
        )
        self._events.append(audio_event)
        yield audio_event

        # Emit transcript
        transcript_event = AgentEvent(
            type=EventType.AGENT_TRANSCRIPT,
            timestamp_ms=now_ms + audio_duration_ms,
            data={"text": text, "confidence": 0.95},
        )
        self._events.append(transcript_event)
        yield transcript_event

        # Emit turn end
        turn_end = AgentEvent(
            type=EventType.TURN_END,
            timestamp_ms=now_ms + audio_duration_ms,
            data={"turn": self._turn_index},
        )
        self._events.append(turn_end)
        yield turn_end

    async def disconnect(self, handle: ConnectionHandle) -> CallSummary:
        duration_ms = (time.monotonic_ns() - handle.start_time_ns) / 1_000_000

        return CallSummary(
            duration_ms=duration_ms,
            turn_count=self._turn_index,
            agent_audio=bytes(self._recorded_audio),
            events=list(self._events),
            platform_metadata={"connector": "demo", "demo": True},
        )
