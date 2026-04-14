"""Audio recorder — capture and persist agent audio output.

Handles assembly of audio chunks from events, WAV file writing,
and audio fingerprinting for reproducibility.
"""

from __future__ import annotations

import hashlib
import io
import logging
from typing import TYPE_CHECKING

import numpy as np
import soundfile as sf

from decibench.models import AgentEvent, AudioBuffer, EventType

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Assemble audio chunks from agent events and persist to files."""

    @staticmethod
    def assemble_from_events(events: list[AgentEvent], sample_rate: int = 16000) -> AudioBuffer:
        """Assemble complete audio from AGENT_AUDIO events."""
        audio_chunks: list[bytes] = []
        for event in events:
            if event.type == EventType.AGENT_AUDIO and event.audio:
                audio_chunks.append(event.audio)

        if not audio_chunks:
            return AudioBuffer(data=b"", sample_rate=sample_rate)

        return AudioBuffer(
            data=b"".join(audio_chunks),
            sample_rate=sample_rate,
        )

    @staticmethod
    def save_wav(
        audio: AudioBuffer,
        path: Path,
    ) -> Path:
        """Save audio buffer as WAV file."""
        path.parent.mkdir(parents=True, exist_ok=True)

        pcm_array = np.frombuffer(audio.data, dtype=np.int16)
        sf.write(str(path), pcm_array, audio.sample_rate, subtype="PCM_16")

        logger.debug("Saved WAV: %s (%.1f ms)", path, audio.duration_ms)
        return path

    @staticmethod
    def save_wav_bytes(audio: AudioBuffer) -> bytes:
        """Convert audio buffer to WAV bytes in memory."""
        pcm_array = np.frombuffer(audio.data, dtype=np.int16)
        buf = io.BytesIO()
        sf.write(buf, pcm_array, audio.sample_rate, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    @staticmethod
    def audio_fingerprint(audio: AudioBuffer) -> str:
        """Generate a short hash of audio content for reproducibility tracking."""
        return hashlib.sha256(audio.data).hexdigest()[:12]
