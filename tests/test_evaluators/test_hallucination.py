"""Tests for hallucination evaluator — entity extraction + judge paths."""

from __future__ import annotations

import pytest

from decibench.evaluators.hallucination import HallucinationEvaluator
from decibench.models import (
    AgentEvent,
    CallSummary,
    ConversationTurn,
    EventType,
    Scenario,
    SuccessCriterion,
    ToolMock,
    TranscriptResult,
    TranscriptSegment,
)


def _scenario(tool_returns: dict | None = None, caller_text: str = "Hello") -> Scenario:
    mocks = []
    if tool_returns:
        mocks.append(ToolMock(name="lookup", returns=tool_returns))
    return Scenario(
        id="test-hallucination",
        description="Test",
        conversation=[ConversationTurn(role="caller", text=caller_text)],
        success_criteria=[SuccessCriterion(type="task_completion")],
        tool_mocks=mocks,
    )


def _summary(tool_result_data: dict | None = None) -> CallSummary:
    events = []
    if tool_result_data:
        events.append(AgentEvent(
            type=EventType.TOOL_RESULT,
            timestamp_ms=100,
            data=tool_result_data,
        ))
    return CallSummary(duration_ms=5000, turn_count=2, events=events)


def _transcript(text: str) -> TranscriptResult:
    return TranscriptResult(
        text=text,
        segments=[TranscriptSegment(role="agent", text=text, confidence=0.95)],
    )


# ---------------------------------------------------------------------------
# Entity extraction (deterministic path)
# ---------------------------------------------------------------------------

def test_entity_extraction_grounded():
    """Entities from agent response that exist in grounding → no hallucination."""
    evaluator = HallucinationEvaluator()
    grounding = "Tool result: {'amount': '$500', 'date': 'Tuesday', 'time': '2:00 PM'}"
    transcript = _transcript("Your balance is $500. Your appointment is Tuesday at 2:00 PM.")
    score = evaluator._entity_grounding_check(transcript, grounding)
    assert score >= 80.0  # Most entities should be grounded


def test_entity_extraction_hallucinated_numbers():
    """Agent invents numbers not in grounding → detected as hallucination."""
    evaluator = HallucinationEvaluator()
    grounding = "Tool result: {'balance': '$200'}"
    transcript = _transcript("Your balance is $500 and your account ID is 99887766.")
    score = evaluator._entity_grounding_check(transcript, grounding)
    assert score < 50.0  # Most entities are NOT in grounding


def test_entity_extraction_conversational_filler():
    """Greetings and filler produce no entities → 100% (no hallucination)."""
    evaluator = HallucinationEvaluator()
    grounding = "No specific grounding context available."
    transcript = _transcript("Hello! How can I help you today?")
    score = evaluator._entity_grounding_check(transcript, grounding)
    assert score == 100.0  # No factual claims


def test_entity_extraction_empty_transcript():
    """Empty transcript → 100% (nothing to hallucinate)."""
    evaluator = HallucinationEvaluator()
    score = evaluator._entity_grounding_check(
        TranscriptResult(text="", segments=[]),
        "some grounding",
    )
    assert score == 100.0


def test_entity_extraction_empty_grounding():
    """No grounding context → 100% (can't check)."""
    evaluator = HallucinationEvaluator()
    score = evaluator._entity_grounding_check(
        TranscriptResult(text="", segments=[]),
        "",
    )
    assert score == 100.0


def test_entity_extraction_order_ids():
    """Order IDs like ORD-12345 should be extracted and checked."""
    evaluator = HallucinationEvaluator()
    grounding = "Tool result: {'order_id': 'ORD-12345', 'status': 'shipped'}"
    transcript = _transcript("Your order ORD-12345 has been shipped.")
    score = evaluator._entity_grounding_check(transcript, grounding)
    assert score >= 50.0  # ORD-12345 is grounded


def test_entity_extraction_email():
    """Email addresses should be extracted and checked."""
    evaluator = HallucinationEvaluator()
    grounding = "Caller said: My email is john@example.com"
    transcript = _transcript("I'll send the confirmation to john@example.com.")
    score = evaluator._entity_grounding_check(transcript, grounding)
    assert score >= 50.0


def test_entity_extraction_dates():
    """Day names and month+day dates should be extracted."""
    evaluator = HallucinationEvaluator()
    grounding = "Tool result: {'day': 'Monday', 'date': 'January 15'}"
    transcript = _transcript("Your appointment is on Monday, January 15.")
    score = evaluator._entity_grounding_check(transcript, grounding)
    assert score >= 50.0


def test_trivial_numbers_not_penalized():
    """Trivial numbers (1, 2) should not count as hallucination."""
    evaluator = HallucinationEvaluator()
    grounding = "No specific grounding context available."
    # "1" and "2" are trivial — should be filtered out
    transcript = _transcript("There are 2 options for you.")
    score = evaluator._entity_grounding_check(transcript, grounding)
    assert score == 100.0  # Trivial numbers filtered


# ---------------------------------------------------------------------------
# Full evaluate() flow (deterministic, no judge)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluate_no_transcript():
    """No transcript → skip with 0% hallucination."""
    evaluator = HallucinationEvaluator()
    results = await evaluator.evaluate(
        _scenario(),
        _summary(),
        TranscriptResult(text="", segments=[]),
        context={},
    )
    assert len(results) == 1
    assert results[0].name == "hallucination_rate"
    assert results[0].value == 0.0
    assert results[0].passed is True


@pytest.mark.asyncio
async def test_evaluate_deterministic_grounded():
    """Agent response grounded in tool results → low hallucination rate."""
    evaluator = HallucinationEvaluator()
    results = await evaluator.evaluate(
        _scenario(tool_returns={"balance": "$500", "name": "John"}),
        _summary(tool_result_data={"balance": "$500", "name": "John"}),
        _transcript("Your balance is $500."),
        context={},  # No judge
    )
    assert len(results) == 1
    assert results[0].name == "hallucination_rate"
    assert results[0].value <= 50.0  # Should be low


# ---------------------------------------------------------------------------
# Grounding context collection
# ---------------------------------------------------------------------------

def test_collect_grounding_tool_results():
    """Tool results should appear in grounding context."""
    scenario = _scenario(tool_returns={"balance": "$500"})
    summary = _summary(tool_result_data={"balance": "$500"})
    grounding = HallucinationEvaluator._collect_grounding(scenario, summary)
    assert "$500" in grounding


def test_collect_grounding_caller_text():
    """Caller text should appear in grounding context."""
    scenario = _scenario(caller_text="My account number is 12345")
    grounding = HallucinationEvaluator._collect_grounding(scenario, _summary())
    assert "12345" in grounding


def test_collect_grounding_empty():
    """No context → default message."""
    scenario = Scenario(
        id="empty",
        description="Test",
        conversation=[],
        success_criteria=[],
    )
    grounding = HallucinationEvaluator._collect_grounding(scenario, _summary())
    assert "No specific grounding" in grounding
