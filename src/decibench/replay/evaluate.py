"""Evaluate imported CallTraces post-mortem."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from decibench.models import (
    CallSummary,
    CallTrace,
    EvalResult,
    MetricResult,
    Scenario,
    TranscriptResult,
)

if TYPE_CHECKING:
    from decibench.config import DecibenchConfig
    from decibench.evaluators.base import BaseEvaluator

logger = logging.getLogger(__name__)

class ImportedCallEvaluator:
    """Runs a suite of evaluators on an imported offline CallTrace."""

    def __init__(
        self,
        evaluators: list[BaseEvaluator],
        config: DecibenchConfig,
        judge: Any | None = None,
    ) -> None:
        self._evaluators = evaluators
        self._config = config
        self._judge = judge

    async def evaluate_trace(self, trace: CallTrace, scenario: Scenario | None = None) -> EvalResult:
        """Evaluate a single CallTrace."""
        start = time.monotonic()

        # 1. Synthesize inputs
        # If no scenario is provided, create a dummy one for base statistical metrics.
        safe_scenario = scenario or Scenario(
            id=f"imported-{trace.id}",
            description="Synthetic scenario for imported call.",
        )

        transcript = TranscriptResult(
            text=trace.text,
            segments=trace.transcript,
            language="en",
            duration_ms=trace.duration_ms,
        )
        summary = CallSummary(
            duration_ms=trace.duration_ms,
            turn_count=len([e for e in trace.events if e.type.value == "turn_end"]),
            events=trace.events,
            agent_audio=b"",  # Audio bytes are rarely saved by default from importers.
        )

        all_metrics: dict[str, MetricResult] = {}
        eval_context: dict[str, Any] = {
            "judge": self._judge,
            "config": self._config,
            "p50_max_ms": (self._config.ci.max_p95_latency_ms or 1500) * 0.53,
            "p95_max_ms": self._config.ci.max_p95_latency_ms or 1500,
            "p99_max_ms": (self._config.ci.max_p95_latency_ms or 1500) * 2.0,
            "ttfw_max_ms": (self._config.ci.max_p95_latency_ms or 1500) * 0.53,
            "is_imported_call": True,
        }

        # 2. Run applicable evaluators
        for evaluator in self._evaluators:
            if evaluator.requires_judge and self._judge is None:
                continue
            if getattr(evaluator, "requires_audio", False) and not summary.agent_audio:
                continue

            try:
                metrics = await evaluator.evaluate(safe_scenario, summary, transcript, eval_context)
                for metric in metrics:
                    all_metrics[metric.name] = metric
            except Exception as e:
                logger.warning(
                    "Evaluator '%s' failed on imported trace '%s': %s",
                    evaluator.name,
                    trace.id,
                    e,
                )

        # 3. Aggregate failures
        failures = [
            f"{m.name}: {m.value} (threshold: {m.threshold})"
            for m in all_metrics.values()
            if not m.passed
        ]
        passed = len(failures) == 0

        # Build failure_summary categories
        from decibench.evaluators.score import _METRIC_CATEGORIES

        failed_categories = set()
        for m in all_metrics.values():
            if not m.passed and m.name in _METRIC_CATEGORIES:
                failed_categories.add(_METRIC_CATEGORIES[m.name])

        # Composite score
        from decibench.evaluators.score import DecibenchScorer

        scorer = DecibenchScorer()

        # We need to wrap it into an intermediate EvalResult to use the scorer
        tmp_result = EvalResult(scenario_id=safe_scenario.id, passed=passed, score=0.0, metrics=all_metrics)
        score, _ = scorer.calculate(
            [tmp_result],
            self._config.scoring.weights,
            has_judge=(self._judge is not None),
        )

        return EvalResult(
            scenario_id=safe_scenario.id,
            passed=passed,
            score=score,
            metrics=all_metrics,
            failures=failures,
            failure_summary=list(failed_categories),
            duration_ms=(time.monotonic() - start) * 1000,
        )
