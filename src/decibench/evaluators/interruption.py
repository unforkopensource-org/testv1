"""Interruption evaluator — measures barge-in handling quality.

Evaluates how gracefully the agent handles caller interruptions:
- Does the agent stop speaking when interrupted?
- Does it acknowledge the interruption?
- Does it avoid repeating itself after resuming?

Maps to the 'interruption' scoring category (default 10% weight).
"""

from __future__ import annotations

import logging
from typing import Any

from decibench.evaluators.base import BaseEvaluator
from decibench.models import (
    CallSummary,
    EventType,
    MetricResult,
    Scenario,
    TranscriptResult,
)

logger = logging.getLogger(__name__)


class InterruptionEvaluator(BaseEvaluator):
    """Evaluate agent behaviour during caller interruptions."""

    @property
    def name(self) -> str:
        return "interruption"

    async def evaluate(
        self,
        scenario: Scenario,
        summary: CallSummary,
        transcript: TranscriptResult,
        context: dict[str, Any],
    ) -> list[MetricResult]:
        results: list[MetricResult] = []

        events = summary.events

        # 1. Detect interruption events
        interruptions = [e for e in events if e.type == EventType.INTERRUPTION]
        interruption_count = len(interruptions)

        # No interruptions → no data. Return empty so the category
        # is excluded from the weighted average (not inflated with 50).
        if interruption_count == 0:
            return []

        # 2. Check for overlapping audio (agent + caller speaking simultaneously)
        overlap_ms = self._detect_audio_overlap(summary)

        # 3. Measure recovery time after interruption
        recovery_ms = self._measure_recovery_time(events)

        # 4. Check for repetition after interruption (agent repeating itself)
        repetition_score = self._check_post_interruption_repetition(transcript)

        # Interruption recovery: how well does agent handle being cut off
        # Score 0-100: 100 = perfect handling
        recovery_score = self._calculate_recovery_score(
            interruption_count=interruption_count,
            overlap_ms=overlap_ms,
            recovery_ms=recovery_ms,
            repetition_score=repetition_score,
        )

        results.append(MetricResult(
            name="interruption_recovery",
            value=round(recovery_score, 1),
            unit="%",
            passed=recovery_score >= 50.0,
            threshold=50.0,
            details={
                "interruption_count": interruption_count,
                "overlap_ms": round(overlap_ms, 1),
                "recovery_ms": round(recovery_ms, 1),
                "repetition_score": round(repetition_score, 1),
            },
        ))

        # Barge-in handling: does the agent stop when interrupted?
        barge_in_score = self._evaluate_barge_in(events, overlap_ms)
        results.append(MetricResult(
            name="barge_in_handling",
            value=round(barge_in_score, 1),
            unit="%",
            passed=barge_in_score >= 50.0,
            threshold=50.0,
            details={
                "overlap_ms": round(overlap_ms, 1),
            },
        ))

        return results

    @staticmethod
    def _detect_audio_overlap(summary: CallSummary) -> float:
        """Detect overlapping agent/caller audio (double-talk).

        Returns total overlap duration in milliseconds.

        Two modes:
        1. If CALLER_AUDIO_END events exist (real caller timing), measure
           actual overlap between caller audio spans and agent audio.
        2. Fallback: measure how long the agent kept sending audio after
           an INTERRUPTION signal (connector-reported).
        """
        events = summary.events

        # Check if we have real caller audio timing
        caller_end_times = [
            e.timestamp_ms for e in events
            if e.type == EventType.CALLER_AUDIO_END
        ]

        interruption_times = [
            e.timestamp_ms for e in events if e.type == EventType.INTERRUPTION
        ]
        if not interruption_times:
            return 0.0

        total_overlap = 0.0

        if caller_end_times:
            # Mode 1: Real caller timing available.
            # For each interruption, find the closest caller_audio_end
            # and measure agent audio that overlaps with caller speech.
            for int_time in interruption_times:
                # Find caller speech end nearest to (and after) interruption
                caller_end = min(
                    (t for t in caller_end_times if t >= int_time),
                    default=int_time,
                )
                # Agent audio between interruption and caller speech end
                # is true double-talk
                overlapping = [
                    e for e in events
                    if e.type == EventType.AGENT_AUDIO
                    and int_time <= e.timestamp_ms <= caller_end + 500
                ]
                if len(overlapping) >= 2:
                    span = overlapping[-1].timestamp_ms - overlapping[0].timestamp_ms
                    chunk = span / (len(overlapping) - 1)
                    total_overlap += span + chunk
                elif len(overlapping) == 1:
                    evt = overlapping[0]
                    if evt.audio:
                        total_overlap += len(evt.audio) / 32.0
                    else:
                        total_overlap += 100.0
        else:
            # Mode 2: Fallback — no caller timing, use interruption signal
            for int_time in interruption_times:
                post_int_audio = [
                    e for e in events
                    if e.type == EventType.AGENT_AUDIO
                    and int_time < e.timestamp_ms < int_time + 3000
                ]
                if len(post_int_audio) >= 2:
                    first_ts = post_int_audio[0].timestamp_ms
                    last_ts = post_int_audio[-1].timestamp_ms
                    chunk_ms = (last_ts - first_ts) / (len(post_int_audio) - 1)
                    total_overlap += (last_ts - first_ts) + chunk_ms
                elif len(post_int_audio) == 1:
                    evt = post_int_audio[0]
                    if evt.audio:
                        total_overlap += len(evt.audio) / 32.0
                    else:
                        total_overlap += 100.0

        return total_overlap

    @staticmethod
    def _measure_recovery_time(events: list[Any]) -> float:
        """Measure time between interruption and agent's next coherent response.

        Returns average recovery time in milliseconds.
        """
        recovery_times: list[float] = []

        for i, event in enumerate(events):
            if event.type == EventType.INTERRUPTION:
                interrupt_time = event.timestamp_ms
                # Find next agent audio/transcript event
                for j in range(i + 1, len(events)):
                    next_event = events[j]
                    if next_event.type in (
                        EventType.AGENT_AUDIO,
                        EventType.AGENT_TRANSCRIPT,
                    ):
                        recovery_times.append(
                            next_event.timestamp_ms - interrupt_time
                        )
                        break

        if not recovery_times:
            return 0.0
        return sum(recovery_times) / len(recovery_times)

    @staticmethod
    def _check_post_interruption_repetition(transcript: TranscriptResult) -> float:
        """Check if agent repeats itself after being interrupted.

        Returns score 0-100: 100 = no repetition (good).
        """
        if not transcript.segments or len(transcript.segments) < 2:
            return 100.0

        texts = [seg.text.lower().strip() for seg in transcript.segments if seg.text]
        if len(texts) < 2:
            return 100.0

        # Check consecutive segments for high similarity
        repetitions = 0
        comparisons = 0
        for i in range(1, len(texts)):
            if not texts[i] or not texts[i - 1]:
                continue
            comparisons += 1
            # Simple word overlap check
            words_prev = set(texts[i - 1].split())
            words_curr = set(texts[i].split())
            if not words_prev or not words_curr:
                continue
            overlap = len(words_prev & words_curr) / max(
                len(words_prev), len(words_curr)
            )
            if overlap > 0.7:
                repetitions += 1

        if comparisons == 0:
            return 100.0
        return (1.0 - repetitions / comparisons) * 100.0

    @staticmethod
    def _calculate_recovery_score(
        interruption_count: int,
        overlap_ms: float,
        recovery_ms: float,
        repetition_score: float,
    ) -> float:
        """Calculate overall interruption recovery score (0-100)."""
        # Recovery time scoring: <500ms = 100, >3000ms = 0
        if recovery_ms <= 500:
            recovery_score = 100.0
        elif recovery_ms >= 3000:
            recovery_score = 0.0
        else:
            recovery_score = 100.0 - ((recovery_ms - 500) / 2500 * 100)

        # Overlap penalty: each 100ms of overlap costs 5 points
        overlap_penalty = min(40, overlap_ms / 100 * 5)

        # Combine: 40% recovery time, 30% repetition, 30% overlap
        combined = (
            recovery_score * 0.4
            + repetition_score * 0.3
            + max(0, 100 - overlap_penalty) * 0.3
        )
        return max(0.0, min(100.0, combined))

    @staticmethod
    def _evaluate_barge_in(events: list[Any], overlap_ms: float) -> float:
        """Evaluate barge-in handling quality.

        Good agent: stops speaking quickly after caller starts.
        Bad agent: keeps talking over the caller.
        """
        # Less overlap = better barge-in handling
        if overlap_ms <= 200:
            return 100.0
        if overlap_ms >= 3000:
            return 0.0
        return 100.0 - ((overlap_ms - 200) / 2800 * 100)
