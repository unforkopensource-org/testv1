"""Tests for WER evaluator."""

from __future__ import annotations

import pytest

from decibench.evaluators.wer import WEREvaluator
from decibench.models import (
    CallSummary,
    ConversationTurn,
    Scenario,
    TranscriptResult,
    TurnExpectation,
)


@pytest.fixture
def evaluator() -> WEREvaluator:
    return WEREvaluator()


@pytest.fixture
def scenario_with_ref() -> Scenario:
    return Scenario(
        id="test-wer",
        conversation=[
            ConversationTurn(role="caller", text="Hello"),
            ConversationTurn(
                role="agent",
                expect=TurnExpectation(must_include=["schedule my appointment"]),
            ),
        ],
    )


@pytest.mark.asyncio
async def test_wer_perfect_match(evaluator, scenario_with_ref):
    transcript = TranscriptResult(text="schedule my appointment", language="en")
    summary = CallSummary(duration_ms=1000, turn_count=1)

    results = await evaluator.evaluate(scenario_with_ref, summary, transcript, {})
    assert len(results) > 0
    # keyword_presence comes first, then WER if reference text exists
    keyword_result = next((r for r in results if r.name == "keyword_presence"), None)
    assert keyword_result is not None
    assert keyword_result.passed is True


@pytest.mark.asyncio
async def test_wer_with_errors(evaluator, scenario_with_ref):
    transcript = TranscriptResult(text="cancel my appointment", language="en")
    summary = CallSummary(duration_ms=1000, turn_count=1)

    results = await evaluator.evaluate(scenario_with_ref, summary, transcript, {})
    assert len(results) > 0
    keyword_result = next((r for r in results if r.name == "keyword_presence"), None)
    assert keyword_result is not None
    assert keyword_result.value < 100.0  # "schedule" keyword missing


@pytest.mark.asyncio
async def test_wer_empty_transcript(evaluator, scenario_with_ref):
    transcript = TranscriptResult(text="", language="en")
    summary = CallSummary(duration_ms=1000, turn_count=1)

    results = await evaluator.evaluate(scenario_with_ref, summary, transcript, {})
    assert len(results) > 0
    assert results[0].value == 100.0
    assert results[0].passed is False


@pytest.mark.asyncio
async def test_wer_no_reference(evaluator):
    scenario = Scenario(id="test-no-ref", conversation=[])
    transcript = TranscriptResult(text="hello world", language="en")
    summary = CallSummary(duration_ms=1000, turn_count=1)

    results = await evaluator.evaluate(scenario, summary, transcript, {})
    assert len(results) == 0  # No reference = no WER to compute
