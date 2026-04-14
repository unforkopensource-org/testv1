"""Tests for intelligibility (STOI proxy) evaluator."""

from __future__ import annotations

import pytest

from decibench.evaluators.stoi import STOIEvaluator
from decibench.models import (
    CallSummary,
    ConversationTurn,
    Scenario,
    SuccessCriterion,
    TranscriptResult,
    TranscriptSegment,
)


def _scenario() -> Scenario:
    return Scenario(
        id="test-intell",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Hello")],
        success_criteria=[SuccessCriterion(type="task_completion")],
    )


def _summary_with_audio() -> CallSummary:
    return CallSummary(duration_ms=5000, turn_count=1, agent_audio=b"\x00" * 32000)


def _summary_no_audio() -> CallSummary:
    return CallSummary(duration_ms=5000, turn_count=1, agent_audio=b"")


def _transcript_with_confidence(confidences: list[float]) -> TranscriptResult:
    segments = [
        TranscriptSegment(role="agent", text=f"word{i}", confidence=c)
        for i, c in enumerate(confidences)
    ]
    return TranscriptResult(
        text=" ".join(f"word{i}" for i in range(len(confidences))),
        segments=segments,
    )


# ---------------------------------------------------------------------------
# No data → empty results
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_audio_returns_empty():
    """No agent audio → empty results."""
    evaluator = STOIEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary_no_audio(),
        TranscriptResult(text="Hello", segments=[]),
        context={},
    )
    assert results == []


@pytest.mark.asyncio
async def test_no_segments_returns_empty():
    """Audio present but no transcript segments → empty (no data)."""
    evaluator = STOIEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary_with_audio(),
        TranscriptResult(text="Hello", segments=[]),
        context={},
    )
    assert results == []


@pytest.mark.asyncio
async def test_zero_confidence_segments_returns_empty():
    """All segments have 0 confidence → empty (no usable data)."""
    evaluator = STOIEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary_with_audio(),
        _transcript_with_confidence([0.0, 0.0, 0.0]),
        context={},
    )
    assert results == []


# ---------------------------------------------------------------------------
# Normal data → produces metric
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_high_confidence():
    """High STT confidence → high intelligibility estimate."""
    evaluator = STOIEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary_with_audio(),
        _transcript_with_confidence([0.95, 0.98, 0.92]),
        context={},
    )
    assert len(results) == 1
    metric = results[0]
    assert metric.name == "intelligibility_estimate"
    assert metric.value > 0.8
    assert metric.passed is True
    assert metric.details["method"] == "stt_confidence_proxy"


@pytest.mark.asyncio
async def test_low_confidence():
    """Low STT confidence → low intelligibility estimate."""
    evaluator = STOIEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary_with_audio(),
        _transcript_with_confidence([0.2, 0.15, 0.3]),
        context={},
    )
    assert len(results) == 1
    metric = results[0]
    assert metric.value < 0.6
    # Likely fails default threshold of 0.45
    assert metric.details["method"] == "stt_confidence_proxy"


@pytest.mark.asyncio
async def test_mixed_confidence():
    """Mixed confidence scores → mid-range estimate."""
    evaluator = STOIEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary_with_audio(),
        _transcript_with_confidence([0.9, 0.3, 0.85, 0.1]),
        context={},
    )
    assert len(results) == 1
    metric = results[0]
    assert 0.3 < metric.value < 0.95


# ---------------------------------------------------------------------------
# Static method tests
# ---------------------------------------------------------------------------

def test_estimate_no_segments():
    """No segments → -1 (no data signal)."""
    transcript = TranscriptResult(text="", segments=[])
    score = STOIEvaluator._estimate_intelligibility(transcript)
    assert score == -1.0


def test_estimate_high_confidence():
    """High confidence → high intelligibility."""
    transcript = _transcript_with_confidence([0.95, 0.9])
    score = STOIEvaluator._estimate_intelligibility(transcript)
    assert score > 0.9


def test_estimate_capped_at_one():
    """Score should never exceed 1.0."""
    transcript = _transcript_with_confidence([1.0, 1.0, 1.0])
    score = STOIEvaluator._estimate_intelligibility(transcript)
    assert score <= 1.0
