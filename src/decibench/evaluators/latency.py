"""Latency evaluator — TTFW, turn latency percentiles, response gap.

Two modes:
- External: what the caller experiences (always available)
- Internal: component breakdown (only if platform provides it)
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from decibench.evaluators.base import BaseEvaluator
from decibench.models import CallSummary, EventType, MetricResult, Scenario, TranscriptResult


class LatencyEvaluator(BaseEvaluator):
    """Measure latency at multiple granularities."""

    @property
    def name(self) -> str:
        return "latency"

    async def evaluate(
        self,
        scenario: Scenario,
        summary: CallSummary,
        transcript: TranscriptResult,
        context: dict[str, Any],
    ) -> list[MetricResult]:
        results: list[MetricResult] = []
        events = summary.events

        if not events:
            return results

        # --- Time to First Word (TTFW) ---
        ttfw = self._calculate_ttfw(events)
        if ttfw is not None:
            results.append(MetricResult(
                name="ttfw_ms",
                value=round(ttfw, 1),
                unit="ms",
                passed=ttfw < context.get("ttfw_max_ms", 800),
                threshold=context.get("ttfw_max_ms", 800),
            ))

        # --- Turn latency percentiles ---
        turn_latencies = self._calculate_turn_latencies(events)
        if turn_latencies:
            sorted_latencies = sorted(turn_latencies)

            p50 = self._percentile(sorted_latencies, 50)
            p95 = self._percentile(sorted_latencies, 95)
            p99 = self._percentile(sorted_latencies, 99)

            p50_max = context.get("p50_max_ms", 800)
            p95_max = context.get("p95_max_ms", 1500)
            p99_max = context.get("p99_max_ms", 3000)

            results.append(MetricResult(
                name="turn_latency_p50_ms",
                value=round(p50, 1),
                unit="ms",
                passed=p50 <= p50_max,
                threshold=p50_max,
            ))
            results.append(MetricResult(
                name="turn_latency_p95_ms",
                value=round(p95, 1),
                unit="ms",
                passed=p95 <= p95_max,
                threshold=p95_max,
            ))
            results.append(MetricResult(
                name="turn_latency_p99_ms",
                value=round(p99, 1),
                unit="ms",
                passed=p99 <= p99_max,
                threshold=p99_max,
            ))

            # Average response gap — sweet spot is 200-1500ms
            avg_gap = statistics.mean(turn_latencies)
            gap_max = context.get("response_gap_max_ms", 1500)
            results.append(MetricResult(
                name="response_gap_avg_ms",
                value=round(avg_gap, 1),
                unit="ms",
                passed=avg_gap <= gap_max,
                threshold=gap_max,
                details={"target_range": f"<{gap_max}ms"},
            ))

        # --- Internal latency (if platform provides it) ---
        meta = summary.platform_metadata
        if "stt_latency" in meta:
            results.append(MetricResult(
                name="stt_latency_ms",
                value=float(meta["stt_latency"]),
                unit="ms",
                passed=True,
            ))
        if "llm_ttft" in meta:
            results.append(MetricResult(
                name="llm_ttft_ms",
                value=float(meta["llm_ttft"]),
                unit="ms",
                passed=True,
            ))
        if "tts_ttfb" in meta:
            results.append(MetricResult(
                name="tts_ttfb_ms",
                value=float(meta["tts_ttfb"]),
                unit="ms",
                passed=True,
            ))

        return results

    @staticmethod
    def _calculate_ttfw(events: list[Any]) -> float | None:
        """Time to First Word: time from caller finish to first agent response.

        Measures from the earliest reliable "caller finished speaking"
        anchor to the first agent audio/transcript event.

        Anchors (in priority order):
        1. CALLER_AUDIO_END — recorded when caller audio finishes sending
        2. First TURN_END with role=caller — connector-reported turn boundary
        3. Fallback: t=0 (call start) — least accurate but always available

        The old approach always used t=0, which measured connection setup
        + caller speech duration + agent processing, conflating everything.
        """
        # Find the best "caller finished" anchor
        anchor_ms = 0.0

        # Priority 1: CALLER_AUDIO_END (most accurate)
        for event in events:
            if event.type == EventType.CALLER_AUDIO_END:
                anchor_ms = event.timestamp_ms
                break

        # Priority 2: First caller TURN_END
        if anchor_ms == 0.0:
            for event in events:
                if (
                    event.type == EventType.TURN_END
                    and event.data.get("role") == "caller"
                ):
                    anchor_ms = event.timestamp_ms
                    break

        # Find first agent response after anchor
        for event in events:
            if (
                event.type in (EventType.AGENT_AUDIO, EventType.AGENT_TRANSCRIPT)
                and event.timestamp_ms > anchor_ms
            ):
                return event.timestamp_ms - anchor_ms

        return None

    @staticmethod
    def _calculate_turn_latencies(events: list[Any]) -> list[float]:
        """Calculate latency between turn ends and next agent response."""
        latencies: list[float] = []
        last_turn_end_ms: float | None = None

        for event in events:
            if event.type == EventType.TURN_END:
                last_turn_end_ms = event.timestamp_ms
            elif event.type == EventType.AGENT_AUDIO and last_turn_end_ms is not None:
                latency = event.timestamp_ms - last_turn_end_ms
                if latency > 0:
                    latencies.append(latency)
                last_turn_end_ms = None

        # If no explicit turn ends, measure gaps between audio bursts
        if not latencies:
            audio_events = [e for e in events if e.type == EventType.AGENT_AUDIO]
            if len(audio_events) >= 2:
                for i in range(1, len(audio_events)):
                    gap = audio_events[i].timestamp_ms - audio_events[i - 1].timestamp_ms
                    # Only count gaps > 200ms as inter-turn pauses (not intra-stream chunks)
                    if gap > 200:
                        latencies.append(gap)

        return latencies

    @staticmethod
    def _percentile(sorted_values: list[float], p: float) -> float:
        """Nearest-rank percentile. Returns an actually-observed value.

        For latency monitoring, nearest-rank is preferred (matches
        Prometheus/HDR Histogram behavior). Always returns a real
        measurement, correct even for N=1.
        """
        n = len(sorted_values)
        if n == 0:
            return 0.0
        rank = max(1, math.ceil(p / 100.0 * n))
        return sorted_values[rank - 1]
