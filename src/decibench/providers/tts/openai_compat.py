"""OpenAI-compatible TTS adapter.

Covers any TTS service that exposes an OpenAI-compatible API:
ElevenLabs, Azure, Google, Cartesia, or self-hosted endpoints.
"""

from __future__ import annotations

import io
import logging
from typing import Any

import httpx

from decibench.models import AudioBuffer, AudioEncoding
from decibench.providers.registry import register_tts

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 30.0


@register_tts("openai-compat")
class OpenAICompatTTSProvider:
    """TTS via any OpenAI-compatible speech API endpoint."""

    def __init__(self, uri: str = "", config_str: str = "", **kwargs: Any) -> None:
        # Parse URI: openai-compat://host:port/v1
        base_url = config_str.lstrip("/")
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
        self._base_url = base_url.rstrip("/")
        self._api_key = kwargs.get("api_key", "")
        self._model = kwargs.get("model", "tts-1")

    async def synthesize(
        self,
        text: str,
        voice: str = "",
        speed: float = 1.0,
    ) -> AudioBuffer:
        resolved_voice = voice or "alloy"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self._model,
            "input": text,
            "voice": resolved_voice,
            "speed": speed,
            "response_format": "pcm",
        }

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}/audio/speech",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            audio_data = response.content

        # If response is PCM, use directly; otherwise convert
        content_type = response.headers.get("content-type", "")
        if "pcm" in content_type or "octet-stream" in content_type:
            pcm_data = audio_data
        else:
            pcm_data = await self._convert_to_pcm(audio_data)

        return AudioBuffer(
            data=pcm_data,
            sample_rate=24000,  # OpenAI TTS default
            channels=1,
            bit_depth=16,
            encoding=AudioEncoding.PCM_S16LE,
        )

    async def list_voices(self) -> list[dict[str, Any]]:
        return [
            {"id": "alloy", "name": "Alloy"},
            {"id": "echo", "name": "Echo"},
            {"id": "fable", "name": "Fable"},
            {"id": "onyx", "name": "Onyx"},
            {"id": "nova", "name": "Nova"},
            {"id": "shimmer", "name": "Shimmer"},
        ]

    async def close(self) -> None:
        pass

    @staticmethod
    async def _convert_to_pcm(audio_data: bytes) -> bytes:
        """Convert various audio formats to PCM 16-bit mono."""
        import numpy as np
        import soundfile as sf

        buf = io.BytesIO(audio_data)
        audio_array, _sr = sf.read(buf, dtype="float32")

        if audio_array.ndim > 1:
            audio_array = audio_array.mean(axis=1)

        pcm = (audio_array * 32767).clip(-32768, 32767).astype(np.int16)
        return bytes(pcm.tobytes())
