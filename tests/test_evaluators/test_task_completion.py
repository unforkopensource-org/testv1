"""Tests for task completion evaluator — tool calls, slot extraction, deterministic path."""

from __future__ import annotations

import pytest

from decibench.evaluators.task import TaskCompletionEvaluator
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
    TurnExpectation,
)


def _transcript(text: str) -> TranscriptResult:
    return TranscriptResult(
        text=text,
        segments=[TranscriptSegment(role="agent", text=text, confidence=0.95)],
    )


def _summary(tool_calls: list[dict] | None = None) -> CallSummary:
    events = []
    for tc in (tool_calls or []):
        events.append(AgentEvent(
            type=EventType.TOOL_CALL,
            timestamp_ms=100,
            data=tc,
        ))
    return CallSummary(duration_ms=5000, turn_count=2, events=events)


# ---------------------------------------------------------------------------
# Tool call correctness
# ---------------------------------------------------------------------------

def test_tool_calls_all_correct():
    """All expected tools called with correct params → 100%."""
    scenario = Scenario(
        id="test",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Book appointment")],
        success_criteria=[SuccessCriterion(type="task_completion")],
        tool_mocks=[
            ToolMock(name="book_appointment", when_called_with={"time": "2:00 PM"}),
        ],
    )
    summary = _summary([{"name": "book_appointment", "args": {"time": "2:00 PM"}}])
    score = TaskCompletionEvaluator._check_tool_calls(scenario, summary)
    assert score == 100.0


def test_tool_calls_wrong_params():
    """Tool called but with wrong params → 0%."""
    scenario = Scenario(
        id="test",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Book appointment")],
        success_criteria=[SuccessCriterion(type="task_completion")],
        tool_mocks=[
            ToolMock(name="book_appointment", when_called_with={"time": "2:00 PM"}),
        ],
    )
    summary = _summary([{"name": "book_appointment", "args": {"time": "3:00 PM"}}])
    score = TaskCompletionEvaluator._check_tool_calls(scenario, summary)
    assert score == 0.0


def test_tool_calls_missing():
    """Expected tool not called → 0%."""
    scenario = Scenario(
        id="test",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Book appointment")],
        success_criteria=[SuccessCriterion(type="task_completion")],
        tool_mocks=[
            ToolMock(name="book_appointment"),
        ],
    )
    summary = _summary([])  # No tool calls
    score = TaskCompletionEvaluator._check_tool_calls(scenario, summary)
    assert score == 0.0


def test_tool_calls_no_expected():
    """No tools expected → 100%."""
    scenario = Scenario(
        id="test",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Hello")],
        success_criteria=[SuccessCriterion(type="task_completion")],
    )
    summary = _summary([])
    score = TaskCompletionEvaluator._check_tool_calls(scenario, summary)
    assert score == 100.0


def test_tool_calls_no_param_check():
    """Tool expected with no specific params → called = correct."""
    scenario = Scenario(
        id="test",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Lookup")],
        success_criteria=[SuccessCriterion(type="task_completion")],
        tool_mocks=[ToolMock(name="lookup_order")],
    )
    summary = _summary([{"name": "lookup_order", "args": {"id": "anything"}}])
    score = TaskCompletionEvaluator._check_tool_calls(scenario, summary)
    assert score == 100.0


# ---------------------------------------------------------------------------
# Slot extraction
# ---------------------------------------------------------------------------

def test_slot_extraction_found():
    """Expected slots found in transcript → 100%."""
    scenario = Scenario(
        id="test",
        description="Test",
        conversation=[
            ConversationTurn(role="caller", text="My name is John"),
            ConversationTurn(
                role="agent",
                expect=TurnExpectation(
                    intent="confirm",
                    must_extract={"name": "John"},
                ),
            ),
        ],
        success_criteria=[SuccessCriterion(type="task_completion")],
    )
    transcript = _transcript("I see, John. Let me look that up.")
    score = TaskCompletionEvaluator._check_slot_extraction(
        scenario, _summary(), transcript,
    )
    assert score == 100.0


def test_slot_extraction_missing():
    """Expected slot not in transcript → 0%."""
    scenario = Scenario(
        id="test",
        description="Test",
        conversation=[
            ConversationTurn(role="caller", text="My name is John"),
            ConversationTurn(
                role="agent",
                expect=TurnExpectation(
                    intent="confirm",
                    must_extract={"name": "John"},
                ),
            ),
        ],
        success_criteria=[SuccessCriterion(type="task_completion")],
    )
    transcript = _transcript("Hello, how can I help you?")
    score = TaskCompletionEvaluator._check_slot_extraction(
        scenario, _summary(), transcript,
    )
    assert score == 0.0


def test_slot_extraction_no_slots():
    """No slots expected → None (not applicable)."""
    scenario = Scenario(
        id="test",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Hello")],
        success_criteria=[SuccessCriterion(type="task_completion")],
    )
    score = TaskCompletionEvaluator._check_slot_extraction(
        scenario, _summary(), _transcript("Hello"),
    )
    assert score is None


# ---------------------------------------------------------------------------
# Full evaluate() (deterministic, no judge)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluate_deterministic_no_judge():
    """Without judge → produces tool_call_correctness + task_completion."""
    evaluator = TaskCompletionEvaluator()
    scenario = Scenario(
        id="test",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Book it")],
        success_criteria=[SuccessCriterion(type="task_completion")],
        tool_mocks=[ToolMock(name="book", when_called_with={"time": "2 PM"})],
    )
    results = await evaluator.evaluate(
        scenario,
        _summary([{"name": "book", "args": {"time": "2 PM"}}]),
        _transcript("Booked for 2 PM."),
        context={},  # No judge
    )
    names = {r.name for r in results}
    assert "tool_call_correctness" in names
    assert "task_completion" in names

    tc = next(r for r in results if r.name == "tool_call_correctness")
    assert tc.value == 100.0

    task = next(r for r in results if r.name == "task_completion")
    assert task.details.get("method") == "deterministic_only"
