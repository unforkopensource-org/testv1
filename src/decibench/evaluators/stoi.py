"""Intelligibility estimator — STT confidence proxy.

STOI (Short-Time Objective Intelligibility) requires a clean reference
of the SAME utterance. In voice agent testing we don't have that.

This evaluator estimates intelligibility from STT confidence scores —
a reasonable proxy (if the STT can't understand it, humans probably
struggle too). Clearly labeled as an estimate, not real STOI.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from decibench.evaluators.base import BaseEvaluator
from decibench.models import CallSummary, MetricResult, Scenario, TranscriptResult

logger = logging.getLogger(__name__)


class STOIEvaluator(BaseEvaluator):
    """Speech intelligibility estimation from STT confidence."""

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
        score = self._estimate_intelligibility(transcript)

        # No data → no metric. Don't pollute the score with made-up numbers.
        if score < 0:
            return []

        return [MetricResult(
            name="intelligibility_estimate",
            value=round(score, 3),
            unit="",
            passed=score >= threshold,
            threshold=threshold,
            details={
                "method": "stt_confidence_proxy",
                "note": "Estimated from STT confidence. Not a real STOI measurement.",
            },
        )]

    @staticmethod
    def _estimate_intelligibility(transcript: TranscriptResult) -> float:
        """Estimate intelligibility from STT confidence scores.

        Maps STT confidence (typically 0-1) to a 0-1 intelligibility estimate.
        If STT struggles with the audio, intelligibility is likely low.
        """
        if not transcript.segments:
            return -1.0  # Signal: no data available

        confidences = [
            seg.confidence for seg in transcript.segments
            if seg.confidence > 0
        ]

        if not confidences:
            return -1.0  # Signal: STT provided no confidence scores

        avg_conf = sum(confidences) / len(confidences)
        # Most STT confidence is 0.0-1.0
        # Map to intelligibility: 0.3 (very low conf) → 1.0 (perfect conf)
        estimated = 0.3 + avg_conf * 0.7
        return float(np.clip(estimated, 0.0, 1.0))
