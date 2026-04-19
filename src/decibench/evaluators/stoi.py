"""Intelligibility estimator — multi-signal speech quality proxy.

STOI (Short-Time Objective Intelligibility) requires a clean reference
of the SAME utterance. In voice agent testing we don't have that.

This evaluator combines multiple independent signals to estimate
intelligibility:
  1. Audio-domain: SNR and spectral clarity from the raw waveform
  2. STT-domain: transcription confidence (useful but NOT the sole signal)
  3. Lexical-domain: word rate sanity check

Using STT confidence alone is circular — "the STT is confident" just
means the STT model is confident, not that the audio is actually clear.
By combining audio-level measurements with STT confidence we break the
circularity and produce a more robust estimate.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from decibench.audio.analysis import calculate_snr
from decibench.evaluators.base import BaseEvaluator
from decibench.models import AudioBuffer, CallSummary, MetricResult, Scenario, TranscriptResult

logger = logging.getLogger(__name__)


class STOIEvaluator(BaseEvaluator):
    """Multi-signal speech intelligibility estimation."""

    @property
    def name(self) -> str:
        return "intelligibility_estimate"

    @property
    def layer(self) -> str:
        return "statistical"

    @property
    def requires_audio(self) -> bool:
        return True

    async def evaluate(
        self,
        scenario: Scenario,
        summary: CallSummary,
        transcript: TranscriptResult,
        context: dict[str, Any],
    ) -> list[MetricResult]:
        if not summary.agent_audio:
            return []

        threshold = context.get("intelligibility_threshold", 0.45)
        audio = AudioBuffer(data=summary.agent_audio)

        score, components = self._estimate_intelligibility(audio, transcript)

        # No data at all → skip metric entirely
        if score < 0:
            return []

        return [MetricResult(
            name="intelligibility_estimate",
            value=round(score, 3),
            unit="",
            passed=score >= threshold,
            threshold=threshold,
            details={
                "method": "multi_signal_estimate",
                "note": (
                    "Combined from audio SNR, spectral clarity, STT confidence, "
                    "and word rate. Not a reference-based STOI measurement."
                ),
                **components,
            },
        )]

    @staticmethod
    def _estimate_intelligibility(
        audio: AudioBuffer,
        transcript: TranscriptResult,
    ) -> tuple[float, dict[str, float]]:
        """Estimate intelligibility from multiple independent signals.

        Returns (score, components_dict).  Score is 0-1.
        Returns (-1.0, {}) when no usable data is available.

        Signals and weights:
          - SNR (40%): Audio-domain, fully independent of STT
          - Spectral clarity (20%): Audio-domain, checks energy in speech band
          - STT confidence (25%): Useful cross-check, but capped at 0.25 weight
          - Word rate sanity (15%): Too fast/slow speech hurts intelligibility
        """
        components: dict[str, float] = {}
        weighted_sum = 0.0
        total_weight = 0.0

        # --- Signal 1: SNR (40% weight) ---
        snr_db = calculate_snr(audio)
        # Map SNR: 5dB=0.0, 15dB=0.5, 30dB=1.0
        snr_score = float(np.clip((snr_db - 5.0) / 25.0, 0.0, 1.0))
        components["snr_db"] = round(snr_db, 1)
        components["snr_score"] = round(snr_score, 3)
        weighted_sum += snr_score * 0.40
        total_weight += 0.40

        # --- Signal 2: Spectral clarity (20% weight) ---
        spectral_score = STOIEvaluator._spectral_clarity(audio)
        if spectral_score >= 0:
            components["spectral_clarity"] = round(spectral_score, 3)
            weighted_sum += spectral_score * 0.20
            total_weight += 0.20

        # --- Signal 3: STT confidence (25% weight, capped) ---
        conf_score = STOIEvaluator._stt_confidence_score(transcript)
        if conf_score >= 0:
            components["stt_confidence"] = round(conf_score, 3)
            weighted_sum += conf_score * 0.25
            total_weight += 0.25

        # --- Signal 4: Word rate sanity (15% weight) ---
        wps_score = STOIEvaluator._word_rate_score(transcript)
        if wps_score >= 0:
            components["word_rate_score"] = round(wps_score, 3)
            weighted_sum += wps_score * 0.15
            total_weight += 0.15

        if total_weight == 0:
            return -1.0, {}

        final = weighted_sum / total_weight
        return float(np.clip(final, 0.0, 1.0)), components

    @staticmethod
    def _spectral_clarity(audio: AudioBuffer) -> float:
        """Measure energy concentration in the speech frequency band (300-3400 Hz).

        Returns 0-1: proportion of energy in the speech band vs total.
        A clean speech signal concentrates energy here; noise is broadband.
        Returns -1 if audio is too short.
        """
        signal = np.frombuffer(audio.data, dtype=np.int16).astype(np.float64)
        if len(signal) < 1024:
            return -1.0

        # Use FFT on windowed segments
        n_fft = 2048
        if len(signal) < n_fft:
            n_fft = len(signal)

        spectrum = np.abs(np.fft.rfft(signal[:n_fft]))
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / audio.sample_rate)

        total_energy = np.sum(spectrum ** 2)
        if total_energy < 1e-10:
            return 0.0

        # Speech band: 300-3400 Hz
        speech_mask = (freqs >= 300) & (freqs <= 3400)
        speech_energy = np.sum(spectrum[speech_mask] ** 2)

        ratio = speech_energy / total_energy
        # Map: 0.3 ratio = 0.0, 0.7+ ratio = 1.0
        return float(np.clip((ratio - 0.3) / 0.4, 0.0, 1.0))

    @staticmethod
    def _stt_confidence_score(transcript: TranscriptResult) -> float:
        """Extract STT confidence as one signal (not sole signal).

        Returns 0-1 or -1 if no confidence data.
        Unlike the old approach, this is just 25% of the final score.
        """
        if not transcript.segments:
            return -1.0

        confidences = [
            seg.confidence for seg in transcript.segments
            if seg.confidence > 0
        ]
        if not confidences:
            return -1.0

        return sum(confidences) / len(confidences)

    @staticmethod
    def _word_rate_score(transcript: TranscriptResult) -> float:
        """Check if word rate is in a reasonable range for clear speech.

        Normal speech: 2-3 words/second. Too fast or too slow
        reduces intelligibility.  Returns -1 if no timing data.
        """
        if not transcript.text or transcript.duration_ms <= 0:
            return -1.0

        word_count = len(transcript.text.split())
        if word_count == 0:
            return 0.0

        duration_s = transcript.duration_ms / 1000.0
        wps = word_count / duration_s

        # Optimal: 2-3.5 wps. Penalty outside that range.
        if 2.0 <= wps <= 3.5:
            return 1.0
        if wps < 0.5 or wps > 7.0:
            return 0.0
        if wps < 2.0:
            return float(np.clip((wps - 0.5) / 1.5, 0.0, 1.0))
        # wps > 3.5
        return float(np.clip((7.0 - wps) / 3.5, 0.0, 1.0))
