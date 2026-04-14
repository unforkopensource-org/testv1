"""Edge-TTS adapter — the default TTS provider.

Microsoft neural voices, 400+ voices, 100+ languages, $0 cost.
Requires internet connection.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from decibench.models import AudioBuffer, AudioEncoding
from decibench.providers.registry import register_tts

logger = logging.getLogger(__name__)

# Default voices per accent/locale
_DEFAULT_VOICES: dict[str, str] = {
    "en-US": "en-US-JennyNeural",
    "en-GB": "en-GB-SoniaNeural",
    "en-AU": "en-AU-NatashaNeural",
    "en-IN": "en-IN-NeerjaNeural",
    "en-NG": "en-NG-AbeoNeural",
    "es-ES": "es-ES-ElviraNeural",
    "fr-FR": "fr-FR-DeniseNeural",
    "de-DE": "de-DE-KatjaNeural",
    "ja-JP": "ja-JP-NanamiNeural",
    "zh-CN": "zh-CN-XiaoxiaoNeural",
    "hi-IN": "hi-IN-SwaraNeural",
    "ko-KR": "ko-KR-SunHiNeural",
    "pt-BR": "pt-BR-FranciscaNeural",
}


@register_tts("edge-tts")
class EdgeTTSProvider:
    """TTS via Microsoft Edge neural voices.

    Uses the edge-tts library which interfaces with Microsoft's free
    Edge TTS service. Excellent quality, zero cost, needs internet.
    """

    def __init__(self, uri: str = "", config_str: str = "", **kwargs: Any) -> None:
        self._voice = kwargs.get("voice", "")

    async def synthesize(
        self,
        text: str,
        voice: str = "",
        speed: float = 1.0,
    ) -> AudioBuffer:
        try:
            import edge_tts
        except ImportError as e:
            msg = "edge-tts required: pip install decibench[tts-edge]"
            raise ImportError(msg) from e

        resolved_voice = voice or self._voice or "en-US-JennyNeural"

        # Build rate string: +0%, +50%, -20%, etc.
        rate_pct = int((speed - 1.0) * 100)
        rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"

        communicate = edge_tts.Communicate(text, resolved_voice, rate=rate_str)

        # Collect audio chunks
        audio_chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])

        if not audio_chunks:
            msg = f"Edge-TTS returned no audio for text: {text[:50]}..."
            raise RuntimeError(msg)

        # edge-tts returns MP3 by default, convert to PCM
        mp3_data = b"".join(audio_chunks)
        pcm_data = await _mp3_to_pcm(mp3_data)

        return AudioBuffer(
            data=pcm_data,
            sample_rate=16000,
            channels=1,
            bit_depth=16,
            encoding=AudioEncoding.PCM_S16LE,
        )

    async def list_voices(self) -> list[dict[str, Any]]:
        try:
            import edge_tts
        except ImportError as e:
            msg = "edge-tts required: pip install decibench[tts-edge]"
            raise ImportError(msg) from e

        voices = await edge_tts.list_voices()
        return [
            {
                "id": v["ShortName"],
                "name": v["FriendlyName"],
                "locale": v["Locale"],
                "gender": v["Gender"],
            }
            for v in voices
        ]

    async def close(self) -> None:
        pass

    @staticmethod
    def resolve_voice(accent: str) -> str:
        """Resolve an accent code to a default voice ID."""
        return _DEFAULT_VOICES.get(accent, "en-US-JennyNeural")


async def _mp3_to_pcm(mp3_data: bytes, target_sr: int = 16000) -> bytes:
    """Convert MP3 bytes to PCM 16-bit mono at target sample rate."""
    import numpy as np
    import soundfile as sf

    # soundfile can read from BytesIO
    buf = io.BytesIO(mp3_data)
    try:
        audio_array, sr = sf.read(buf, dtype="float32")
    except RuntimeError:
        # Fallback: try with librosa if soundfile can't handle MP3
        import librosa
        buf.seek(0)
        audio_array, sr = librosa.load(buf, sr=target_sr, mono=True)

    # Convert to mono if stereo
    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=1)

    # Resample if needed
    if sr != target_sr:
        import librosa
        audio_array = librosa.resample(audio_array, orig_sr=sr, target_sr=target_sr)

    # Convert to 16-bit PCM
    pcm = (audio_array * 32767).clip(-32768, 32767).astype(np.int16)
    return bytes(pcm.tobytes())
