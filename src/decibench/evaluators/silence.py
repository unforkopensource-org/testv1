"""Silence evaluator — detect dead air in agent responses.

Dead air segments >2 seconds indicate the agent is stuck, processing
too slowly, or has lost the conversation thread. Target: <5% of call.
"""

from __future__ import annotations

from typing import Any

from decibench.audio.analysis import detect_silence_segments
from decibench.evaluators.base import BaseEvaluator
from decibench.models import AudioBuffer, CallSummary, MetricResult, Scenario, TranscriptResult


class SilenceEvaluator(BaseEvaluator):
    """Detect and measure dead air in agent responses."""

    @property
    def name(self) -> str:
        return "silence"

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

        audio = AudioBuffer(data=summary.agent_audio)
        total_duration_ms = audio.duration_ms

        if total_duration_ms < 100:
            return []

        # Detect silence segments
        min_silence_ms = context.get("min_silence_ms", 2000)
        silences = detect_silence_segments(
            audio,
            threshold_db=-40.0,
            min_duration_ms=min_silence_ms,
        )

        # Calculate silence percentage
        total_silence_ms = sum(end - start for start, end in silences)
        silence_pct = (total_silence_ms / total_duration_ms) * 100 if total_duration_ms > 0 else 0
        threshold = context.get("max_silence_pct", 5.0)

        return [
            MetricResult(
                name="silence_segments",
                value=float(len(silences)),
                unit="count",
                passed=True,
                details={
                    "segments": [
                        {"start_ms": round(s, 1), "end_ms": round(e, 1)}
                        for s, e in silences
                    ]
                },
            ),
            MetricResult(
                name="silence_pct",
                value=round(silence_pct, 1),
                unit="%",
                passed=silence_pct <= threshold,
                threshold=threshold,
            ),
        ]
