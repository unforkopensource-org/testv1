"""Silence evaluator — detect dead air in agent responses.

Measures two distinct types of silence:
1. Audio silence: gaps within the agent's audio stream (agent went quiet
   mid-response). Detected via signal analysis on agent_audio.
2. Conversational dead air: gaps between caller finishing and agent
   starting to respond. Detected via event timestamps (TURN_END or
   CALLER_AUDIO_END -> next AGENT_AUDIO). This is what callers
   actually perceive as "dead air".

The old approach only measured (1), which misses the main problem:
long pauses between turns where the caller is waiting.
"""

from __future__ import annotations

from typing import Any

from decibench.audio.analysis import detect_silence_segments
from decibench.evaluators.base import BaseEvaluator
from decibench.models import (
    AudioBuffer,
    CallSummary,
    EventType,
    MetricResult,
    Scenario,
    TranscriptResult,
)


class SilenceEvaluator(BaseEvaluator):
    """Detect and measure dead air — both audio silence and turn gaps."""

    @property
    def name(self) -> str:
        return "silence"

    @property
    def layer(self) -> str:
        return "statistical"

    @property
    def requires_audio(self) -> bool:
        # We can produce turn_gap metrics from events alone,
        # but audio silence still needs audio.
        return False

    async def evaluate(
        self,
        scenario: Scenario,
        summary: CallSummary,
        transcript: TranscriptResult,
        context: dict[str, Any],
    ) -> list[MetricResult]:
        results: list[MetricResult] = []

        # --- Turn-gap dead air (conversational silence) ---
        turn_gap_results = self._measure_turn_gaps(summary, context)
        results.extend(turn_gap_results)

        # --- Audio-stream silence (within agent audio) ---
        if summary.agent_audio:
            audio = AudioBuffer(data=summary.agent_audio)
            total_duration_ms = audio.duration_ms

            if total_duration_ms >= 100:
                min_silence_ms = context.get("min_silence_ms", 2000)
                silences = detect_silence_segments(
                    audio,
                    threshold_db=-40.0,
                    min_duration_ms=min_silence_ms,
                )

                total_silence_ms = sum(end - start for start, end in silences)
                silence_pct = (
                    (total_silence_ms / total_duration_ms) * 100
                    if total_duration_ms > 0
                    else 0
                )
                threshold = context.get("max_silence_pct", 5.0)

                results.append(MetricResult(
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
                ))
                results.append(MetricResult(
                    name="silence_pct",
                    value=round(silence_pct, 1),
                    unit="%",
                    passed=silence_pct <= threshold,
                    threshold=threshold,
                ))

        return results

    @staticmethod
    def _measure_turn_gaps(
        summary: CallSummary,
        context: dict[str, Any],
    ) -> list[MetricResult]:
        """Measure gaps between caller finishing and agent responding.

        This is the silence callers actually experience — waiting for
        the agent to start talking after they finish speaking.
        Uses CALLER_AUDIO_END or TURN_END events as the anchor.
        """
        events = summary.events
        if not events:
            return []

        # Find caller-finish -> agent-start gaps
        gaps: list[float] = []

        # Look for CALLER_AUDIO_END events first (most accurate)
        caller_ends = [
            e for e in events if e.type == EventType.CALLER_AUDIO_END
        ]
        # Fallback to TURN_END events
        if not caller_ends:
            caller_ends = [
                e for e in events
                if e.type == EventType.TURN_END
                and e.data.get("role") == "caller"
            ]

        for ce in caller_ends:
            # Find next agent audio after this caller end
            next_agent = None
            for e in events:
                if (
                    e.type in (EventType.AGENT_AUDIO, EventType.AGENT_TRANSCRIPT)
                    and e.timestamp_ms > ce.timestamp_ms
                ):
                    next_agent = e
                    break

            if next_agent is not None:
                gap_ms = next_agent.timestamp_ms - ce.timestamp_ms
                if gap_ms > 0:
                    gaps.append(gap_ms)

        if not gaps:
            return []

        max_gap = max(gaps)
        avg_gap = sum(gaps) / len(gaps)
        dead_air_threshold = context.get("dead_air_max_ms", 3000)

        return [
            MetricResult(
                name="turn_gap_avg_ms",
                value=round(avg_gap, 1),
                unit="ms",
                passed=avg_gap <= dead_air_threshold,
                threshold=dead_air_threshold,
                details={
                    "gaps": [round(g, 1) for g in gaps],
                    "max_gap_ms": round(max_gap, 1),
                    "count": len(gaps),
                },
            ),
        ]
