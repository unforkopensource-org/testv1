"""OpenAI-compatible STT adapter.

Covers Deepgram, AssemblyAI, Groq Whisper, or any endpoint
that implements the OpenAI audio/transcriptions API.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from decibench.models import AudioBuffer, TranscriptResult, TranscriptSegment
from decibench.providers.registry import register_stt

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 60.0


@register_stt("openai-compat")
class OpenAICompatSTTProvider:
    """STT via any OpenAI-compatible transcription endpoint."""

    def __init__(self, uri: str = "", config_str: str = "", **kwargs: Any) -> None:
        base_url = config_str.lstrip("/")
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
        self._base_url = base_url.rstrip("/")
        self._api_key = kwargs.get("api_key", "")
        self._model = kwargs.get("model", "whisper-1")

    async def transcribe(self, audio: AudioBuffer) -> TranscriptResult:
        import io

        import numpy as np
        import soundfile as sf

        # Convert PCM to WAV in memory (API expects file upload)
        pcm_array = np.frombuffer(audio.data, dtype=np.int16)
        wav_buf = io.BytesIO()
        sf.write(wav_buf, pcm_array, audio.sample_rate, format="WAV", subtype="PCM_16")
        wav_buf.seek(0)

        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}/audio/transcriptions",
                headers=headers,
                files={"file": ("audio.wav", wav_buf, "audio/wav")},
                data={
                    "model": self._model,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word",
                },
            )
            response.raise_for_status()
            data = response.json()

        text = data.get("text", "")
        segments: list[TranscriptSegment] = []

        for seg in data.get("segments", []):
            segments.append(TranscriptSegment(
                role="agent",
                text=seg.get("text", "").strip(),
                start_ms=seg.get("start", 0) * 1000.0,
                end_ms=seg.get("end", 0) * 1000.0,
                confidence=seg.get("avg_logprob", 0.0),
            ))

        return TranscriptResult(
            text=text,
            segments=segments,
            language=data.get("language", "en"),
            duration_ms=audio.duration_ms,
        )

    async def close(self) -> None:
        pass
