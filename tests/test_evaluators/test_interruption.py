"""Tests for interruption evaluator — barge-in handling and recovery."""

from __future__ import annotations

import pytest

from decibench.evaluators.interruption import InterruptionEvaluator
from decibench.models import (
    AgentEvent,
    CallSummary,
    ConversationTurn,
    EventType,
    Scenario,
    SuccessCriterion,
    TranscriptResult,
    TranscriptSegment,
)


def _scenario() -> Scenario:
    return Scenario(
        id="test-interruption",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Hello")],
        success_criteria=[SuccessCriterion(type="task_completion")],
    )


def _transcript(texts: list[str] | None = None) -> TranscriptResult:
    if not texts:
        return TranscriptResult(text="Hello", segments=[])
    return TranscriptResult(
        text=" ".join(texts),
        segments=[
            TranscriptSegment(role="agent", text=t, confidence=0.95)
            for t in texts
        ],
    )


def _summary_with_interruptions(
    interruption_times: list[float],
    agent_audio_after: list[float] | None = None,
    recovery_audio_at: list[float] | None = None,
) -> CallSummary:
    """Build a summary with interruption events and optional agent audio after."""
    events = []
    for t in interruption_times:
        events.append(AgentEvent(type=EventType.INTERRUPTION, timestamp_ms=t))

    for t in (agent_audio_after or []):
        events.append(AgentEvent(type=EventType.AGENT_AUDIO, timestamp_ms=t))

    for t in (recovery_audio_at or []):
        events.append(AgentEvent(type=EventType.AGENT_AUDIO, timestamp_ms=t))

    events.sort(key=lambda e: e.timestamp_ms)
    return CallSummary(duration_ms=10000, turn_count=3, events=events)


# ---------------------------------------------------------------------------
# No interruptions → empty (excluded from scoring)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_interruptions_returns_empty():
    """No interruption events → return empty list, not inflated 50."""
    evaluator = InterruptionEvaluator()
    results = await evaluator.evaluate(
        _scenario(),
        CallSummary(duration_ms=5000, turn_count=2, events=[]),
        _transcript(),
        context={},
    )
    assert results == []


@pytest.mark.asyncio
async def test_no_interruptions_with_other_events():
    """Other event types present but no INTERRUPTION → still empty."""
    evaluator = InterruptionEvaluator()
    events = [
        AgentEvent(type=EventType.AGENT_AUDIO, timestamp_ms=100),
        AgentEvent(type=EventType.TURN_END, timestamp_ms=500),
    ]
    results = await evaluator.evaluate(
        _scenario(),
        CallSummary(duration_ms=5000, turn_count=2, events=events),
        _transcript(),
        context={},
    )
    assert results == []


# ---------------------------------------------------------------------------
# With interruptions → produces metrics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_interruption_fast_recovery():
    """One interruption, agent recovers quickly → good scores."""
    evaluator = InterruptionEvaluator()
    summary = _summary_with_interruptions(
        interruption_times=[1000],
        recovery_audio_at=[1300],  # 300ms recovery
    )
    results = await evaluator.evaluate(
        _scenario(), summary, _transcript(), context={},
    )
    assert len(results) == 2
    names = {r.name for r in results}
    assert "interruption_recovery" in names
    assert "barge_in_handling" in names

    recovery = next(r for r in results if r.name == "interruption_recovery")
    assert recovery.value > 50.0  # Fast recovery should score well


@pytest.mark.asyncio
async def test_interruption_with_overlap():
    """Agent keeps talking after interruption → overlap penalty."""
    evaluator = InterruptionEvaluator()
    summary = _summary_with_interruptions(
        interruption_times=[1000],
        agent_audio_after=[1100, 1200, 1300, 1400, 1500],  # 500ms of overlap
        recovery_audio_at=[2000],
    )
    results = await evaluator.evaluate(
        _scenario(), summary, _transcript(), context={},
    )
    barge_in = next(r for r in results if r.name == "barge_in_handling")
    # Significant overlap should reduce barge-in score
    assert barge_in.value < 100.0


# ---------------------------------------------------------------------------
# Static method unit tests
# ---------------------------------------------------------------------------

def test_recovery_score_fast():
    """< 500ms recovery → high score."""
    score = InterruptionEvaluator._calculate_recovery_score(
        interruption_count=1, overlap_ms=0, recovery_ms=300, repetition_score=100.0,
    )
    assert score > 80.0


def test_recovery_score_slow():
    """> 3000ms recovery → reduced score (recovery component = 0, but others still contribute)."""
    score = InterruptionEvaluator._calculate_recovery_score(
        interruption_count=1, overlap_ms=0, recovery_ms=4000, repetition_score=100.0,
    )
    # Recovery component (40%) is 0, but repetition (30%) and overlap (30%) are good
    assert score == 60.0


def test_barge_in_no_overlap():
    """No overlap → perfect barge-in."""
    score = InterruptionEvaluator._evaluate_barge_in([], 0.0)
    assert score == 100.0


def test_barge_in_heavy_overlap():
    """Heavy overlap → bad barge-in."""
    score = InterruptionEvaluator._evaluate_barge_in([], 3000.0)
    assert score == 0.0


def test_repetition_no_repeats():
    """Distinct segments → 100."""
    transcript = _transcript(["Hello how are you", "Let me check that for you"])
    score = InterruptionEvaluator._check_post_interruption_repetition(transcript)
    assert score == 100.0


def test_repetition_identical_segments():
    """Identical consecutive segments → detected as repetition."""
    transcript = _transcript([
        "Your appointment is at 2 PM",
        "Your appointment is at 2 PM",
    ])
    score = InterruptionEvaluator._check_post_interruption_repetition(transcript)
    assert score < 100.0
