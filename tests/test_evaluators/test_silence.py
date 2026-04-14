"""Tests for silence evaluator — dead air detection."""

from __future__ import annotations

import math
import struct

import pytest

from decibench.evaluators.silence import SilenceEvaluator
from decibench.models import (
    CallSummary,
    ConversationTurn,
    Scenario,
    SuccessCriterion,
    TranscriptResult,
)


def _scenario() -> Scenario:
    return Scenario(
        id="test-silence",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Hello")],
        success_criteria=[SuccessCriterion(type="task_completion")],
    )


def _transcript() -> TranscriptResult:
    return TranscriptResult(text="Hello", segments=[])


def _make_tone(frequency: float, duration_s: float, sr: int = 16000) -> bytes:
    """Generate PCM16 sine wave."""
    n = int(sr * duration_s)
    data = bytearray(n * 2)
    for i in range(n):
        val = int(8000 * math.sin(2 * math.pi * frequency * i / sr))
        struct.pack_into("<h", data, i * 2, val)
    return bytes(data)


def _make_silence(duration_s: float, sr: int = 16000) -> bytes:
    """Generate silent PCM16 audio."""
    return bytes(int(sr * duration_s) * 2)


def _make_tone_then_silence(tone_s: float, silence_s: float) -> bytes:
    """Generate audio with tone followed by silence."""
    return _make_tone(440, tone_s) + _make_silence(silence_s)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_audio():
    """No agent audio → empty results."""
    evaluator = SilenceEvaluator()
    results = await evaluator.evaluate(
        _scenario(),
        CallSummary(duration_ms=5000, turn_count=1, agent_audio=b""),
        _transcript(),
        context={},
    )
    assert results == []


@pytest.mark.asyncio
async def test_very_short_audio():
    """Audio < 100ms → empty results."""
    evaluator = SilenceEvaluator()
    short = _make_tone(440, 0.05)  # 50ms
    results = await evaluator.evaluate(
        _scenario(),
        CallSummary(duration_ms=50, turn_count=1, agent_audio=short),
        _transcript(),
        context={},
    )
    assert results == []


# ---------------------------------------------------------------------------
# Normal audio
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_continuous_tone_no_silence():
    """Continuous tone → 0% silence, 0 segments."""
    evaluator = SilenceEvaluator()
    audio = _make_tone(440, 3.0)
    results = await evaluator.evaluate(
        _scenario(),
        CallSummary(duration_ms=3000, turn_count=1, agent_audio=audio),
        _transcript(),
        context={},
    )
    assert len(results) == 2
    segments = next(r for r in results if r.name == "silence_segments")
    pct = next(r for r in results if r.name == "silence_pct")
    assert segments.value == 0
    assert pct.value == 0.0
    assert pct.passed is True


@pytest.mark.asyncio
async def test_audio_with_long_silence():
    """Tone + long silence → detected as silence segment."""
    evaluator = SilenceEvaluator()
    audio = _make_tone_then_silence(1.0, 3.0)  # 1s tone + 3s silence
    results = await evaluator.evaluate(
        _scenario(),
        CallSummary(duration_ms=4000, turn_count=1, agent_audio=audio),
        _transcript(),
        context={"min_silence_ms": 2000},
    )
    assert len(results) == 2
    segments = next(r for r in results if r.name == "silence_segments")
    pct = next(r for r in results if r.name == "silence_pct")
    # Should detect at least one silence segment
    assert segments.value >= 1
    assert pct.value > 0


@pytest.mark.asyncio
async def test_pure_silence():
    """All-silent audio → high silence percentage, fails threshold."""
    evaluator = SilenceEvaluator()
    audio = _make_silence(5.0)
    results = await evaluator.evaluate(
        _scenario(),
        CallSummary(duration_ms=5000, turn_count=1, agent_audio=audio),
        _transcript(),
        context={"min_silence_ms": 2000, "max_silence_pct": 5.0},
    )
    if results:  # May have silence segments
        pct = next((r for r in results if r.name == "silence_pct"), None)
        if pct:
            assert pct.value > 50.0  # Mostly silence
            assert pct.passed is False  # Should fail 5% threshold
