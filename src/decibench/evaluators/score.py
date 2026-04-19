"""Decibench Score calculator — weighted composite quality score (0-100).

Combines all metrics into a single reproducible score. Supports
both full mode (with LLM judge) and deterministic-only mode.
All weights configurable. Same input + same config = same score.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decibench.config import ScoringWeights
    from decibench.models import EvalResult, MetricResult

logger = logging.getLogger(__name__)

# Metric-to-category mapping
_METRIC_CATEGORIES: dict[str, str] = {
    "task_completion": "task_completion",
    "tool_call_correctness": "task_completion",
    "slot_extraction_accuracy": "task_completion",
    "turn_latency_p50_ms": "latency",
    "turn_latency_p95_ms": "latency",
    "turn_latency_p99_ms": "latency",
    "ttfw_ms": "latency",
    "response_gap_avg_ms": "latency",
    "mos_ovrl": "audio_quality",
    "audio_quality_estimate": "audio_quality",
    "intelligibility_estimate": "audio_quality",
    "snr": "audio_quality",
    "wer": "conversation",
    "cer": "conversation",
    "hallucination_rate": "conversation",
    "keyword_presence": "conversation",
    "keyword_absence": "conversation",
    "silence_pct": "robustness",
    "silence_segments": "robustness",
    "turn_gap_avg_ms": "robustness",
    "pii_violations": "compliance",
    "ai_disclosure": "compliance",
    "compliance_score": "compliance",
    "hipaa_verification_order": "compliance",
    "pci_no_echo": "compliance",
    "interruption_recovery": "interruption",
    "barge_in_handling": "interruption",
}


class DecibenchScorer:
    """Calculate the composite Decibench Score from evaluation results."""

    def calculate(
        self,
        results: list[EvalResult],
        weights: ScoringWeights,
        has_judge: bool,
    ) -> tuple[float, dict[str, float]]:
        """Calculate the Decibench Score (0-100) with category breakdown.

        Args:
            results: Individual scenario evaluation results
            weights: Category weights from config
            has_judge: Whether semantic evaluators were active

        Returns:
            Tuple of (composite_score, category_breakdown_dict)
        """
        if not results:
            return 0.0, {}

        # Aggregate metrics across all scenarios
        category_scores = self._aggregate_categories(results)

        if has_judge:
            weight_map = {
                "task_completion": weights.task_completion,
                "latency": weights.latency,
                "audio_quality": weights.audio_quality,
                "conversation": weights.conversation,
                "robustness": weights.robustness,
                "interruption": weights.interruption,
                "compliance": weights.compliance,
            }
        else:
            # Redistribute semantic weights to deterministic categories
            weight_map = self._redistribute_weights(weights)

        score = 0.0
        total_weight = 0.0

        for category, weight in weight_map.items():
            if category in category_scores and weight > 0:
                score += category_scores[category] * weight
                total_weight += weight

        # Normalize: only divide by weight of categories that had data
        if total_weight > 0:
            score = score / total_weight

        # Critical failure gating: certain category failures cap the
        # overall score.  An agent that leaks PII, hallucinates heavily,
        # or completely fails its task cannot get a passing score
        # regardless of how well it performs in other categories.
        compliance = category_scores.get("compliance")
        if compliance is not None and compliance <= 0:
            score = min(score, 30.0)

        # Hallucination floor: >50% hallucination rate caps at 40
        conversation = category_scores.get("conversation")
        if conversation is not None and conversation <= 10:
            score = min(score, 40.0)

        # Task completion floor: total task failure caps at 45
        task = category_scores.get("task_completion")
        if task is not None and task <= 10:
            score = min(score, 45.0)

        # Round category scores for clean output
        breakdown = {k: round(v, 1) for k, v in category_scores.items()}

        return round(min(100.0, max(0.0, score)), 1), breakdown

    def _aggregate_categories(
        self,
        results: list[EvalResult],
    ) -> dict[str, float]:
        """Aggregate individual metrics into category scores (0-100).

        Uses floor-aware aggregation: 70% mean + 30% worst-case.
        Pure averaging lets one catastrophic failure (score=0) get
        diluted by 9 perfect scores (100) into avg=90, hiding the
        failure entirely.  The 70/30 blend ensures that a single
        zero-score scenario caps the category at ~70 instead of 90.
        """
        category_values: dict[str, list[float]] = {}

        for result in results:
            for metric_name, metric in result.metrics.items():
                category = _METRIC_CATEGORIES.get(metric_name)
                if category is None:
                    continue

                normalized = self._normalize_metric(metric_name, metric)
                if category not in category_values:
                    category_values[category] = []
                category_values[category].append(normalized)

        # Only include categories that actually have data.
        # Untested categories are EXCLUDED from the weighted average.
        aggregated: dict[str, float] = {}
        for cat, vals in category_values.items():
            if vals:
                mean = sum(vals) / len(vals)
                if len(vals) == 1:
                    aggregated[cat] = mean
                else:
                    # Blend: 70% mean + 30% worst-case
                    worst = min(vals)
                    aggregated[cat] = mean * 0.7 + worst * 0.3
        return aggregated

    @staticmethod
    def _normalize_metric(name: str, metric: MetricResult) -> float:
        """Normalize a metric value to 0-100 scale.

        Calibrated so that:
        - A weekend-project agent scores 25-45 (honest baseline)
        - A decent production agent scores 55-75
        - Excellent agents score 75-90
        - 90+ is world-class, nearly impossible
        """
        value = metric.value

        # --- Latency: strict curves, users hang up after 2s ---
        if name in ("turn_latency_p50_ms", "ttfw_ms"):
            # 300ms = 100, 800ms = 50, 2000ms = 0
            if value <= 300:
                return 100.0
            if value >= 2000:
                return 0.0
            return max(0, 100 - ((value - 300) / 1700 * 100))
        if name == "turn_latency_p95_ms":
            # 500ms = 100, 1200ms = 50, 3000ms = 0
            if value <= 500:
                return 100.0
            if value >= 3000:
                return 0.0
            return max(0, 100 - ((value - 500) / 2500 * 100))
        if name == "turn_latency_p99_ms":
            # 800ms = 100, 2000ms = 50, 5000ms = 0
            if value <= 800:
                return 100.0
            if value >= 5000:
                return 0.0
            return max(0, 100 - ((value - 800) / 4200 * 100))
        if name == "response_gap_avg_ms":
            # Sweet spot 300-600ms. >1500ms = 0
            if 300 <= value <= 600:
                return 100.0
            if value < 300:
                return max(50, 100 - (300 - value) / 6)  # Too fast is mildly bad
            if value >= 1500:
                return 0.0
            return max(0, 100 - ((value - 600) / 900 * 100))

        # --- Audio quality ---
        if name == "mos_ovrl":
            # 4.5+ = 100, 3.5 = 50, <2.5 = 0
            if value >= 4.5:
                return 100.0
            if value <= 2.5:
                return 0.0
            return (value - 2.5) / 2.0 * 100
        if name == "intelligibility_estimate":
            # Already 0-1. 0.85+ = 100, 0.5 = 50, <0.3 = 0
            if value >= 0.85:
                return 100.0
            if value <= 0.3:
                return 0.0
            return (value - 0.3) / 0.55 * 100
        if name == "audio_quality_estimate":
            # Heuristic-based, capped at 4.0. Same curve as mos_ovrl.
            if value >= 4.5:
                return 100.0
            if value <= 2.5:
                return 0.0
            return (value - 2.5) / 2.0 * 100
        if name == "snr":
            # 25+ dB = 100, 15 = 50, <5 = 0
            if value >= 25:
                return 100.0
            if value <= 5:
                return 0.0
            return (value - 5) / 20 * 100

        # --- Error rates: lower is better, strict ---
        if name in ("wer", "cer"):
            # 0% = 100, 10% = 50, 20% = 0
            if value <= 0:
                return 100.0
            if value >= 20:
                return 0.0
            return max(0, 100 - value * 5)
        if name == "hallucination_rate":
            # 0% = 100, 2% = 50, 5% = 0 (very strict)
            if value <= 0:
                return 100.0
            if value >= 5:
                return 0.0
            return max(0, 100 - value * 20)
        if name == "silence_pct":
            # 0% = 100, 5% = 50, 15% = 0
            if value <= 0:
                return 100.0
            if value >= 15:
                return 0.0
            return max(0, 100 - value * (100 / 15))
        if name == "turn_gap_avg_ms":
            # 500ms = 100, 1500ms = 50, 5000ms = 0
            if value <= 500:
                return 100.0
            if value >= 5000:
                return 0.0
            return max(0, 100 - ((value - 500) / 4500 * 100))

        # --- Counts: 0 violations is best ---
        if name == "pii_violations":
            # 0 = 100, 1 = 25, 2+ = 0 (extremely strict — PII leaks are critical)
            if value == 0:
                return 100.0
            if value == 1:
                return 25.0
            return 0.0
        if name == "silence_segments":
            return 100 if value == 0 else max(0, 100 - value * 25)

        # --- Percentage metrics: already 0-100 ---
        if metric.unit == "%" or name in (
            "task_completion",
            "tool_call_correctness",
            "slot_extraction_accuracy",
            "ai_disclosure",
            "compliance_score",
        ):
            return value

        # --- Keyword metrics: proportional, not binary ---
        # 100% hit = 100, 80% = 60, 50% = 25, 0% = 0
        if name in ("keyword_presence", "keyword_absence"):
            return value

        # --- Interruption metrics: already 0-100% ---
        if name in ("interruption_recovery", "barge_in_handling"):
            return value

        # Default: pass/fail binary
        return 100.0 if metric.passed else 0.0

    @staticmethod
    def _redistribute_weights(weights: ScoringWeights) -> dict[str, float]:
        """Redistribute weights when semantic evaluators are disabled.

        Without a judge, task_completion is fully removed.
        Conversation keeps its weight only because WER/keyword metrics
        still run deterministically. Weight is redistributed proportionally.
        """
        deterministic = {
            "latency": weights.latency,
            "audio_quality": weights.audio_quality,
            "conversation": weights.conversation,  # WER + keywords are deterministic
            "robustness": weights.robustness,
            "interruption": weights.interruption,
            "compliance": weights.compliance,
        }

        # Only task_completion is fully removed (needs judge for goal assessment)
        removed_weight = weights.task_completion
        deterministic_total = sum(deterministic.values())

        if deterministic_total > 0:
            scale = (deterministic_total + removed_weight) / deterministic_total
            return {k: v * scale for k, v in deterministic.items()}

        return deterministic
