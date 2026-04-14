"""Faster-Whisper STT adapter — the default STT provider.

CTranslate2 backend, 4x faster than OpenAI Whisper, MIT licensed.
Runs on CPU with good performance. Models: tiny/base/small/medium/large-v3.
"""

from __future__ import annotations

import logging
from typing import Any

from decibench.models import AudioBuffer, TranscriptResult, TranscriptSegment
from decibench.providers.registry import register_stt

logger = logging.getLogger(__name__)


@register_stt("faster-whisper")
class FasterWhisperSTTProvider:
    """STT via faster-whisper (CTranslate2 backend)."""

    def __init__(self, uri: str = "", config_str: str = "", **kwargs: Any) -> None:
        # config_str is the model size: base, small, medium, large-v3
        self._model_size = config_str or "base"
        self._model: Any = None
        self._device = kwargs.get("device", "cpu")
        self._compute_type = kwargs.get("compute_type", "int8")

    def _ensure_model(self) -> Any:
        """Lazy-load model on first use."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                msg = "faster-whisper required: pip install decibench[stt-whisper]"
                raise ImportError(msg) from e

            logger.info(
                "Loading faster-whisper model: %s (device=%s, compute=%s)",
                self._model_size,
                self._device,
                self._compute_type,
            )
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
        return self._model

    async def transcribe(self, audio: AudioBuffer) -> TranscriptResult:
        import numpy as np

        model = self._ensure_model()

        # Convert PCM bytes to float32 numpy array
        pcm_array = np.frombuffer(audio.data, dtype=np.int16).astype(np.float32) / 32768.0

        # Resample to 16kHz if needed (Whisper requires 16kHz)
        if audio.sample_rate and audio.sample_rate != 16000:
            try:
                import librosa
                pcm_array = librosa.resample(
                    pcm_array, orig_sr=audio.sample_rate, target_sr=16000
                )
            except ImportError:
                # Fallback: simple linear interpolation resampling
                ratio = 16000 / audio.sample_rate
                new_len = int(len(pcm_array) * ratio)
                indices = np.linspace(0, len(pcm_array) - 1, new_len)
                pcm_array = np.interp(indices, np.arange(len(pcm_array)), pcm_array)
            logger.debug(
                "Resampled audio from %dHz to 16kHz (%d samples)",
                audio.sample_rate, len(pcm_array),
            )

        # Run transcription
        segments_iter, info = model.transcribe(
            pcm_array,
            beam_size=5,
            language=None,  # Auto-detect
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
        )

        segments: list[TranscriptSegment] = []
        full_text_parts: list[str] = []

        for seg in segments_iter:
            text = seg.text.strip()
            if not text:
                continue
            full_text_parts.append(text)
            segments.append(TranscriptSegment(
                role="agent",
                text=text,
                start_ms=seg.start * 1000.0,
                end_ms=seg.end * 1000.0,
                confidence=seg.avg_logprob if hasattr(seg, "avg_logprob") else 0.0,
                words=[
                    {
                        "word": w.word,
                        "start_ms": w.start * 1000.0,
                        "end_ms": w.end * 1000.0,
                        "probability": w.probability,
                    }
                    for w in (seg.words or [])
                ],
            ))

        detected_language = info.language if info else "en"

        return TranscriptResult(
            text=" ".join(full_text_parts),
            segments=segments,
            language=detected_language,
            duration_ms=audio.duration_ms,
        )

    async def close(self) -> None:
        self._model = None
