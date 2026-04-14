"""Base evaluator interface.

All evaluators implement this interface. The orchestrator runs them
in order: deterministic -> statistical -> semantic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from decibench.models import CallSummary, MetricResult, Scenario, TranscriptResult


class BaseEvaluator(ABC):
    """Abstract base for all metric evaluators."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique evaluator name."""
        ...

    @property
    def layer(self) -> str:
        """Evaluation layer: deterministic, statistical, or semantic."""
        return "deterministic"

    @property
    def requires_judge(self) -> bool:
        """Whether this evaluator needs an LLM judge."""
        return False

    @property
    def requires_audio(self) -> bool:
        """Whether this evaluator requires raw audio bytes."""
        return False

    @abstractmethod
    async def evaluate(
        self,
        scenario: Scenario,
        summary: CallSummary,
        transcript: TranscriptResult,
        context: dict[str, Any],
    ) -> list[MetricResult]:
        """Run evaluation and return metric results.

        Args:
            scenario: Test scenario with expectations
            summary: Call summary with events and timing
            transcript: Transcribed agent response
            context: Additional context (judge, config, etc.)

        Returns:
            List of MetricResult objects
        """
        ...
