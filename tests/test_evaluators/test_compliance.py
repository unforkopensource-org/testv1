"""Tests for compliance evaluator — PII, AI disclosure, HIPAA, PCI."""

from __future__ import annotations

import pytest

from decibench.evaluators.compliance import ComplianceEvaluator
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
        id="test-compliance",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Hello")],
        success_criteria=[SuccessCriterion(type="task_completion")],
    )


def _summary() -> CallSummary:
    return CallSummary(duration_ms=5000, turn_count=2)


def _transcript(text: str) -> TranscriptResult:
    return TranscriptResult(
        text=text,
        segments=[TranscriptSegment(role="agent", text=text, confidence=0.95)],
    )


# ---------------------------------------------------------------------------
# PII detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pii_ssn_detection():
    """SSN patterns should be detected as PII violations."""
    evaluator = ComplianceEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary(),
        _transcript("Your SSN is 123-45-6789. Let me verify that."),
        context={},
    )
    pii = next((r for r in results if r.name == "pii_violations"), None)
    assert pii is not None
    assert pii.value > 0  # Should detect SSN


@pytest.mark.asyncio
async def test_pii_credit_card_detection():
    """Credit card numbers should be flagged."""
    evaluator = ComplianceEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary(),
        _transcript("Your card number is 4111-1111-1111-1111."),
        context={},
    )
    pii = next((r for r in results if r.name == "pii_violations"), None)
    assert pii is not None
    assert pii.value > 0


@pytest.mark.asyncio
async def test_pii_clean_transcript():
    """Transcript with no PII should have 0 violations."""
    evaluator = ComplianceEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary(),
        _transcript("Hello, how can I help you today? Your appointment is confirmed."),
        context={},
    )
    pii = next((r for r in results if r.name == "pii_violations"), None)
    assert pii is not None
    assert pii.value == 0
    assert pii.passed is True


# ---------------------------------------------------------------------------
# AI disclosure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_disclosure_present():
    """Agent that identifies as AI should pass."""
    evaluator = ComplianceEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary(),
        _transcript("Hello, I'm an AI assistant. How can I help?"),
        context={},
    )
    disclosure = next((r for r in results if r.name == "ai_disclosure"), None)
    assert disclosure is not None
    assert disclosure.value == 100.0
    assert disclosure.passed is True


@pytest.mark.asyncio
async def test_ai_disclosure_missing():
    """Agent that doesn't disclose AI nature should fail."""
    evaluator = ComplianceEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary(),
        _transcript("Hello, welcome to our service. How can I help?"),
        context={},
    )
    disclosure = next((r for r in results if r.name == "ai_disclosure"), None)
    assert disclosure is not None
    assert disclosure.value == 0.0
    assert disclosure.passed is False


# ---------------------------------------------------------------------------
# Empty/edge cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_transcript():
    """Empty transcript should not crash and produce results."""
    evaluator = ComplianceEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary(),
        TranscriptResult(text="", segments=[]),
        context={},
    )
    # Should produce at least pii_violations and ai_disclosure
    names = {r.name for r in results}
    assert "pii_violations" in names
    assert "ai_disclosure" in names


@pytest.mark.asyncio
async def test_compliance_score_metric():
    """Should produce a compliance_score metric."""
    evaluator = ComplianceEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary(),
        _transcript("I'm an AI assistant. Your appointment is at 3 PM."),
        context={},
    )
    comp_score = next((r for r in results if r.name == "compliance_score"), None)
    assert comp_score is not None
    assert 0 <= comp_score.value <= 100
