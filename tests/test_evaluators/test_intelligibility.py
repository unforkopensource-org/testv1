"""Tests for intelligibility (multi-signal) evaluator."""

from __future__ import annotations

import math
import struct

import pytest

from decibench.evaluators.stoi import STOIEvaluator
from decibench.models import (
    AudioBuffer,
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


def _make_tone(frequency: float, duration_s: float, sr: int = 16000) -> bytes:
    """Generate PCM16 sine wave."""
    n = int(sr * duration_s)
    data = bytearray(n * 2)
    for i in range(n):
        val = int(8000 * math.sin(2 * math.pi * frequency * i / sr))
        struct.pack_into("<h", data, i * 2, val)
    return bytes(data)


def _summary_with_audio(audio: bytes | None = None) -> CallSummary:
    return CallSummary(
        duration_ms=5000,
        turn_count=1,
        agent_audio=audio or _make_tone(440, 1.0),
    )


def _summary_no_audio() -> CallSummary:
    return CallSummary(duration_ms=5000, turn_count=1, agent_audio=b"")


def _transcript_with_confidence(
    confidences: list[float],
    duration_ms: float = 5000.0,
) -> TranscriptResult:
    segments = [
        TranscriptSegment(role="agent", text=f"word{i}", confidence=c)
        for i, c in enumerate(confidences)
    ]
    return TranscriptResult(
        text=" ".join(f"word{i}" for i in range(len(confidences))),
        segments=segments,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# No data -> empty results
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_audio_returns_empty():
    """No agent audio -> empty results."""
    evaluator = STOIEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary_no_audio(),
        TranscriptResult(text="Hello", segments=[]),
        context={},
    )
    assert results == []


@pytest.mark.asyncio
async def test_audio_but_no_segments_still_produces_metric():
    """Audio present but no segments -> uses audio-only signals (SNR, spectral).

    This is the FIX: the old evaluator returned [] here because it
    only used STT confidence (circular). Now audio-domain signals
    are used independently.
    """
    evaluator = STOIEvaluator()
    results = await evaluator.evaluate(
        _scenario(), _summary_with_audio(),
        TranscriptResult(text="Hello", segments=[]),
        context={},
    )
    assert len(results) == 1
    metric = results[0]
    assert metric.name == "intelligibility_estimate"
    assert metric.details["method"] == "multi_signal_estimate"
    # Should use SNR + spectral at minimum
    assert "snr_db" in metric.details


# ---------------------------------------------------------------------------
# Multi-signal estimation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_high_confidence_with_audio():
    """High STT confidence + clean audio -> produces metric with multi-signal method."""
    evaluator = STOIEvaluator()
    # Use realistic word count / duration for normal word rate
    transcript = TranscriptResult(
        text="Hello how are you doing today I am fine thank you",
        segments=[
            TranscriptSegment(role="agent", text="Hello how are you", confidence=0.95),
            TranscriptSegment(role="agent", text="doing today I am fine", confidence=0.98),
            TranscriptSegment(role="agent", text="thank you", confidence=0.92),
        ],
        duration_ms=4000.0,  # 10 words / 4s = 2.5 wps (normal)
    )
    results = await evaluator.evaluate(
        _scenario(), _summary_with_audio(),
        transcript,
        context={},
    )
    assert len(results) == 1
    metric = results[0]
    assert metric.name == "intelligibility_estimate"
    assert metric.details["method"] == "multi_signal_estimate"
    # Multi-signal: components should be present
    assert "stt_confidence" in metric.details
    assert "snr_db" in metric.details


@pytest.mark.asyncio
async def test_low_confidence_penalizes():
    """Low STT confidence should contribute negatively."""
    evaluator = STOIEvaluator()
    high_results = await evaluator.evaluate(
        _scenario(), _summary_with_audio(),
        _transcript_with_confidence([0.95, 0.95, 0.95]),
        context={},
    )
    low_results = await evaluator.evaluate(
        _scenario(), _summary_with_audio(),
        _transcript_with_confidence([0.1, 0.15, 0.1]),
        context={},
    )
    assert high_results[0].value > low_results[0].value


# ---------------------------------------------------------------------------
# Static method tests -- multi-signal
# ---------------------------------------------------------------------------

def test_spectral_clarity_speech_tone():
    """A 440Hz tone should have some spectral clarity in speech band."""
    audio = AudioBuffer(data=_make_tone(440, 0.5))
    score = STOIEvaluator._spectral_clarity(audio)
    assert score >= 0


def test_spectral_clarity_too_short():
    """Very short audio -> -1 (no data)."""
    audio = AudioBuffer(data=b"\x00" * 100)
    score = STOIEvaluator._spectral_clarity(audio)
    assert score == -1.0


def test_stt_confidence_score_no_segments():
    """No segments -> -1."""
    transcript = TranscriptResult(text="", segments=[])
    score = STOIEvaluator._stt_confidence_score(transcript)
    assert score == -1.0


def test_stt_confidence_score_high():
    """High confidence -> high score."""
    transcript = _transcript_with_confidence([0.9, 0.95])
    score = STOIEvaluator._stt_confidence_score(transcript)
    assert score > 0.9


def test_word_rate_score_normal():
    """Normal word rate (2-3.5 wps) -> 1.0."""
    # 10 words in 4 seconds = 2.5 wps
    transcript = TranscriptResult(
        text="one two three four five six seven eight nine ten",
        duration_ms=4000.0,
    )
    score = STOIEvaluator._word_rate_score(transcript)
    assert score == 1.0


def test_word_rate_score_too_fast():
    """Very fast word rate -> low score."""
    # 20 words in 1 second = 20 wps
    transcript = TranscriptResult(
        text=" ".join(f"w{i}" for i in range(20)),
        duration_ms=1000.0,
    )
    score = STOIEvaluator._word_rate_score(transcript)
    assert score == 0.0


def test_word_rate_score_no_duration():
    """No duration -> -1."""
    transcript = TranscriptResult(text="hello world", duration_ms=0)
    score = STOIEvaluator._word_rate_score(transcript)
    assert score == -1.0
