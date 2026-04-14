"""Audio signal analysis — SNR, silence detection, onset detection.

Low-level audio analysis utilities used by evaluators.
All functions operate on AudioBuffer or raw numpy arrays.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from decibench.models import AudioBuffer


def calculate_snr(audio: AudioBuffer, frame_length: int = 1024) -> float:
    """Calculate signal-to-noise ratio in dB using segmental SNR.

    Segmental SNR (frame-level average) correlates better with
    subjective perception than global SNR.

    Returns:
        SNR in dB. Higher is cleaner. 30+ = clean, 20 = noticeable, <10 = poor.
    """
    signal = np.frombuffer(audio.data, dtype=np.int16).astype(np.float64)

    if len(signal) < frame_length:
        return 0.0

    # Frame the signal
    num_frames = len(signal) // frame_length
    frames = signal[: num_frames * frame_length].reshape(num_frames, frame_length)

    # Calculate per-frame energy
    frame_energy = np.sum(frames ** 2, axis=1)

    # Estimate noise floor from lowest-energy frames (bottom 10%)
    sorted_energy = np.sort(frame_energy)
    noise_frames = max(1, num_frames // 10)
    noise_energy = np.mean(sorted_energy[:noise_frames])

    if noise_energy < 1e-10:
        return 60.0  # Essentially silence — very high SNR

    # Signal energy from highest-energy frames (top 50%)
    signal_energy = np.mean(sorted_energy[num_frames // 2 :])

    if signal_energy < 1e-10:
        return 0.0

    snr = 10 * np.log10(signal_energy / noise_energy)
    return float(np.clip(snr, 0, 60))


def detect_silence_segments(
    audio: AudioBuffer,
    threshold_db: float = -40.0,
    min_duration_ms: float = 500.0,
) -> list[tuple[float, float]]:
    """Detect silence segments in audio.

    Args:
        audio: Audio to analyze
        threshold_db: dB threshold below which audio is considered silence
        min_duration_ms: Minimum silence duration to report

    Returns:
        List of (start_ms, end_ms) tuples for each silence segment
    """
    signal = np.frombuffer(audio.data, dtype=np.int16).astype(np.float64)

    if len(signal) == 0:
        return []

    # Frame parameters
    frame_ms = 20  # 20ms frames
    frame_length = int(audio.sample_rate * frame_ms / 1000)
    hop_length = frame_length  # Non-overlapping

    # Reference level for dB calculation
    reference = 32768.0  # Max int16 value

    silences: list[tuple[float, float]] = []
    silence_start: float | None = None

    for i in range(0, len(signal) - frame_length, hop_length):
        frame = signal[i : i + frame_length]
        rms = np.sqrt(np.mean(frame ** 2))

        db = -100.0 if rms < 1e-10 else 20 * np.log10(rms / reference)

        time_ms = (i / audio.sample_rate) * 1000.0

        if db < threshold_db:
            if silence_start is None:
                silence_start = time_ms
        else:
            if silence_start is not None:
                duration = time_ms - silence_start
                if duration >= min_duration_ms:
                    silences.append((silence_start, time_ms))
                silence_start = None

    # Handle silence at end
    if silence_start is not None:
        end_ms = (len(signal) / audio.sample_rate) * 1000.0
        duration = end_ms - silence_start
        if duration >= min_duration_ms:
            silences.append((silence_start, end_ms))

    return silences


def detect_speech_onset(audio: AudioBuffer, threshold_db: float = -30.0) -> float:
    """Detect the onset of speech in audio.

    Returns:
        Time in ms of first speech onset, or -1 if no speech detected.
    """
    signal = np.frombuffer(audio.data, dtype=np.int16).astype(np.float64)

    if len(signal) == 0:
        return -1.0

    frame_ms = 10  # 10ms frames for fine resolution
    frame_length = int(audio.sample_rate * frame_ms / 1000)
    reference = 32768.0

    for i in range(0, len(signal) - frame_length, frame_length):
        frame = signal[i : i + frame_length]
        rms = np.sqrt(np.mean(frame ** 2))
        if rms > 1e-10:
            db = 20 * np.log10(rms / reference)
            if db > threshold_db:
                return (i / audio.sample_rate) * 1000.0

    return -1.0


def calculate_duration_ms(audio: AudioBuffer) -> float:
    """Calculate audio duration in milliseconds."""
    return audio.duration_ms
