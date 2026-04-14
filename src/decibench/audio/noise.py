"""Noise mixing engine — add background noise to caller audio.

Supports mixing at configurable SNR levels with various noise profiles.
Includes built-in synthetic noise generators and support for custom WAV profiles.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from decibench.models import AudioBuffer

logger = logging.getLogger(__name__)


class NoiseMixer:
    """Mix background noise into clean audio at a specified SNR level."""

    def __init__(self, noise_profiles_dir: str = "") -> None:
        self._profiles_dir = Path(noise_profiles_dir) if noise_profiles_dir else None
        self._noise_cache: dict[str, np.ndarray] = {}

    def mix(
        self,
        audio: AudioBuffer,
        profile: str = "clean",
        snr_db: float = 15.0,
    ) -> AudioBuffer:
        """Add noise to audio at specified SNR level.

        Args:
            audio: Clean caller audio
            profile: Noise profile name (clean, white, cafe, street, car, office)
            snr_db: Signal-to-noise ratio in dB (higher = quieter noise)

        Returns:
            Audio with noise mixed in
        """
        if profile == "clean":
            return audio

        # Convert PCM to float array
        signal = np.frombuffer(audio.data, dtype=np.int16).astype(np.float64)

        if len(signal) == 0:
            return audio

        # Generate or load noise
        noise = self._get_noise(profile, len(signal), audio.sample_rate)

        # Calculate scaling factor for target SNR
        signal_power = np.mean(signal ** 2)
        if signal_power < 1e-10:
            return audio

        noise_power = np.mean(noise ** 2)
        if noise_power < 1e-10:
            return audio

        target_noise_power = signal_power / (10 ** (snr_db / 10))
        scale = np.sqrt(target_noise_power / noise_power)

        # Mix
        mixed = signal + scale * noise

        # Clip and convert back to int16
        mixed = np.clip(mixed, -32768, 32767).astype(np.int16)

        return AudioBuffer(
            data=mixed.tobytes(),
            sample_rate=audio.sample_rate,
            channels=audio.channels,
            bit_depth=audio.bit_depth,
            encoding=audio.encoding,
        )

    def _get_noise(
        self,
        profile: str,
        num_samples: int,
        sample_rate: int,
    ) -> np.ndarray:
        """Get noise array for a profile, generating or loading as needed."""
        # Check cache
        cache_key = f"{profile}_{sample_rate}"
        if cache_key in self._noise_cache:
            cached = self._noise_cache[cache_key]
            return self._tile_noise(cached, num_samples)

        # Try loading from file
        if self._profiles_dir:
            noise_file = self._profiles_dir / f"{profile}.wav"
            if noise_file.exists():
                noise = self._load_noise_file(noise_file, sample_rate)
                self._noise_cache[cache_key] = noise
                return self._tile_noise(noise, num_samples)

        # Generate synthetic noise
        noise = self._generate_synthetic_noise(profile, num_samples, sample_rate)
        return noise

    def _generate_synthetic_noise(
        self,
        profile: str,
        num_samples: int,
        sample_rate: int,
    ) -> np.ndarray:
        """Generate synthetic noise for built-in profiles."""
        rng = np.random.default_rng(seed=42)  # Deterministic for reproducibility

        if profile == "white":
            return rng.normal(0, 3000, num_samples)

        if profile == "cafe":
            # Cafe noise: low-frequency rumble + voice-like chatter
            t = np.arange(num_samples) / sample_rate
            rumble = 2000 * np.sin(2 * np.pi * 50 * t)
            chatter = rng.normal(0, 1500, num_samples)
            # Low-pass filter approximation for chatter
            from scipy.signal import butter, sosfilt
            try:
                sos = butter(4, 2000, btype="low", fs=sample_rate, output="sos")
                chatter = sosfilt(sos, chatter)
            except ImportError:
                pass  # Fallback: use unfiltered chatter
            return np.asarray(rumble + chatter)

        if profile == "street":
            # Street noise: broadband with traffic rumble
            t = np.arange(num_samples) / sample_rate
            traffic = 3000 * np.sin(2 * np.pi * 80 * t + rng.uniform(0, 2 * np.pi))
            broadband = rng.normal(0, 2000, num_samples)
            return np.asarray(traffic + broadband)

        if profile == "car":
            # Car noise: engine hum + wind
            t = np.arange(num_samples) / sample_rate
            engine = 2500 * np.sin(2 * np.pi * 120 * t)
            harmonic = 1500 * np.sin(2 * np.pi * 240 * t)
            wind = rng.normal(0, 800, num_samples)
            return np.asarray(engine + harmonic + wind)

        if profile == "office":
            # Office: very quiet background hum + occasional typing
            hum = 500 * np.sin(2 * np.pi * 60 * np.arange(num_samples) / sample_rate)
            ambient = rng.normal(0, 300, num_samples)
            return np.asarray(hum + ambient)

        # Unknown profile: use white noise
        logger.warning("Unknown noise profile '%s', using white noise", profile)
        return np.asarray(rng.normal(0, 3000, num_samples))

    @staticmethod
    def _load_noise_file(path: Path, target_sr: int) -> np.ndarray:
        """Load a WAV noise file and convert to float64 array."""
        import soundfile as sf

        audio, sr = sf.read(str(path), dtype="float64")

        # Convert to mono
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        # Resample if needed
        if sr != target_sr:
            import librosa
            audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)

        # Scale to int16 range
        return np.asarray(audio * 32768)

    @staticmethod
    def _tile_noise(noise: np.ndarray, target_length: int) -> np.ndarray:
        """Tile or truncate noise to match target length."""
        if len(noise) >= target_length:
            return noise[:target_length]
        # Tile to fill
        repeats = (target_length // len(noise)) + 1
        return np.tile(noise, repeats)[:target_length]
