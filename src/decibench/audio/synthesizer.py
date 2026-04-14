"""Audio synthesizer — orchestrates TTS + noise mixing + speed adjustment.

This is the single entry point for generating caller audio from a scenario.
It coordinates TTS provider, noise mixing, speed adjustment, and transcoding.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from decibench.audio.noise import NoiseMixer
from decibench.audio.transcode import transcode
from decibench.models import AudioBuffer, AudioEncoding, Persona

if TYPE_CHECKING:
    from decibench.providers.registry import TTSProvider

logger = logging.getLogger(__name__)


class AudioSynthesizer:
    """Generate caller audio from text + persona configuration."""

    def __init__(
        self,
        tts_provider: TTSProvider,
        noise_profiles_dir: str = "",
    ) -> None:
        self._tts = tts_provider
        self._noise_mixer = NoiseMixer(noise_profiles_dir)

    async def synthesize(
        self,
        text: str,
        persona: Persona,
        target_sample_rate: int = 16000,
        target_encoding: AudioEncoding = AudioEncoding.PCM_S16LE,
    ) -> AudioBuffer:
        """Generate caller audio with persona characteristics applied.

        Pipeline:
        1. TTS: text -> clean audio
        2. Speed adjustment (if persona.speaking_speed != 1.0)
        3. Noise mixing (if persona.background_noise != "clean")
        4. Transcode to target format

        Args:
            text: What the caller says
            persona: Persona config (accent, speed, noise, etc.)
            target_sample_rate: Required by the connector
            target_encoding: Required by the connector

        Returns:
            AudioBuffer ready to send to the agent
        """
        # 1. Synthesize with TTS
        voice = persona.voice
        if not voice:
            # Try to resolve from accent using edge-tts defaults
            from decibench.providers.tts.edge import EdgeTTSProvider
            voice = EdgeTTSProvider.resolve_voice(persona.accent)

        audio = await self._tts.synthesize(
            text=text,
            voice=voice,
            speed=persona.speaking_speed,
        )

        # 2. Mix noise if not clean
        if persona.background_noise != "clean":
            audio = self._noise_mixer.mix(
                audio,
                profile=persona.background_noise,
                snr_db=persona.noise_level_db,
            )

        # 3. Transcode to connector's required format
        if (
            audio.sample_rate != target_sample_rate
            or audio.encoding != target_encoding
        ):
            audio = transcode(audio, target_sample_rate, target_encoding)

        return audio

    async def close(self) -> None:
        """Release TTS provider resources."""
        if hasattr(self._tts, "close"):
            await self._tts.close()
