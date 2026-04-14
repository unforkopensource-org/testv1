"""Audio transcoding — sample rate and encoding conversion.

Generates audio at highest quality, then downsamples per connector requirements.
Supports PCM, mu-law, and opus encoding.
"""

from __future__ import annotations

import logging

import numpy as np

from decibench.models import AudioBuffer, AudioEncoding

logger = logging.getLogger(__name__)

# μ-law constants (ITU-T G.711)
_MULAW_MAX = 0x1FFF
_MULAW_BIAS = 33
_MULAW_CLIP = 32635


def transcode(
    audio: AudioBuffer,
    target_rate: int,
    target_encoding: AudioEncoding = AudioEncoding.PCM_S16LE,
) -> AudioBuffer:
    """Transcode audio to match connector requirements."""
    data = audio.data
    current_rate = audio.sample_rate

    # Resample if rates differ
    if current_rate != target_rate:
        data = _resample(data, current_rate, target_rate)

    # Encode if format differs
    if target_encoding != AudioEncoding.PCM_S16LE:
        if target_encoding == AudioEncoding.MULAW:
            data = _pcm_to_mulaw(data)
        elif target_encoding == AudioEncoding.OPUS:
            data = _pcm_to_opus(data, target_rate)

    return AudioBuffer(
        data=data,
        sample_rate=target_rate,
        channels=audio.channels,
        bit_depth=16 if target_encoding == AudioEncoding.PCM_S16LE else 8,
        encoding=target_encoding,
    )


def _resample(pcm_data: bytes, orig_sr: int, target_sr: int) -> bytes:
    """Resample PCM 16-bit audio using librosa."""
    import librosa

    audio_array = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
    resampled = librosa.resample(audio_array, orig_sr=orig_sr, target_sr=target_sr)
    return (resampled * 32767).clip(-32768, 32767).astype(np.int16).tobytes()


def _pcm_to_mulaw(pcm_data: bytes) -> bytes:
    """Convert 16-bit PCM to 8-bit mu-law encoding (ITU-T G.711).

    Pure numpy implementation — no audioop dependency.
    """
    samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float64)

    # Clip to valid range
    samples = np.clip(samples, -_MULAW_CLIP, _MULAW_CLIP)

    sign = np.where(samples < 0, 0x80, 0).astype(np.uint8)
    magnitude = np.abs(samples).astype(np.int32) + _MULAW_BIAS

    # Compute exponent and mantissa
    exponent = np.zeros(len(magnitude), dtype=np.uint8)
    for i in range(7, 0, -1):
        mask = magnitude >= (1 << (i + 3))
        exponent = np.where(mask & (exponent == 0), i, exponent)

    # Fix: compute properly for each sample
    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    mulaw = ~(sign | (exponent << 4) | mantissa) & 0xFF

    return mulaw.astype(np.uint8).tobytes()


def _mulaw_to_pcm(mulaw_data: bytes) -> bytes:
    """Convert 8-bit mu-law to 16-bit PCM (ITU-T G.711).

    Pure numpy implementation — no audioop dependency.
    """
    mulaw = np.frombuffer(mulaw_data, dtype=np.uint8).astype(np.int32)
    mulaw = ~mulaw

    sign = mulaw & 0x80
    exponent = (mulaw >> 4) & 0x07
    mantissa = mulaw & 0x0F

    magnitude = ((mantissa << 3) + _MULAW_BIAS) << exponent
    magnitude -= _MULAW_BIAS

    samples = np.where(sign != 0, -magnitude, magnitude)
    return samples.clip(-32768, 32767).astype(np.int16).tobytes()


def _pcm_to_opus(pcm_data: bytes, sample_rate: int) -> bytes:
    """Convert PCM to Opus encoding.

    Requires opuslib. Raises ImportError with clear message if unavailable.
    """
    try:
        import opuslib
    except ImportError as err:
        msg = (
            "Opus encoding requires opuslib: pip install opuslib\n"
            "If your agent requires Opus, install the dependency.\n"
            "Alternatively, configure your agent to accept PCM audio."
        )
        raise ImportError(msg) from err

    encoder = opuslib.Encoder(sample_rate, 1, opuslib.APPLICATION_VOIP)

    # Opus requires specific frame sizes: 2.5, 5, 10, 20, 40, 60 ms
    frame_size = sample_rate // 50  # 20ms frames
    frame_bytes = frame_size * 2  # 16-bit = 2 bytes per sample

    opus_frames: list[bytes] = []
    for offset in range(0, len(pcm_data) - frame_bytes + 1, frame_bytes):
        frame = pcm_data[offset : offset + frame_bytes]
        encoded = encoder.encode(frame, frame_size)
        opus_frames.append(encoded)

    return b"".join(opus_frames)


def ensure_mono(audio: AudioBuffer) -> AudioBuffer:
    """Convert stereo audio to mono by averaging channels."""
    if audio.channels == 1:
        return audio

    samples = np.frombuffer(audio.data, dtype=np.int16)
    samples = samples.reshape(-1, audio.channels)
    mono = samples.mean(axis=1).astype(np.int16)

    return AudioBuffer(
        data=mono.tobytes(),
        sample_rate=audio.sample_rate,
        channels=1,
        bit_depth=audio.bit_depth,
        encoding=audio.encoding,
    )
