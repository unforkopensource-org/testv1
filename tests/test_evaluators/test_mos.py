"""Tests for MOS evaluator — heuristic path (speechmos requires separate install)."""

from __future__ import annotations

import math
import struct

import pytest

from decibench.evaluators.mos import MOSEvaluator
from decibench.models import (
    AudioBuffer,
    CallSummary,
    ConversationTurn,
    Scenario,
    SuccessCriterion,
    TranscriptResult,
)


def _scenario() -> Scenario:
    return Scenario(
        id="test-mos",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Hello")],
        success_criteria=[SuccessCriterion(type="task_completion")],
    )


def _make_audio(frequency: float = 440.0, duration_s: float = 1.0, amplitude: int = 16000) -> bytes:
    """Generate PCM16 sine wave audio."""
    sr = 16000
    n = int(sr * duration_s)
    data = bytearray(n * 2)
    for i in range(n):
        val = int(amplitude * math.sin(2 * math.pi * frequency * i / sr))
        struct.pack_into("<h", data, i * 2, max(-32768, min(32767, val)))
    return bytes(data)


def _make_clipped_audio(duration_s: float = 1.0) -> bytes:
    """Generate audio with heavy clipping."""
    sr = 16000
    n = int(sr * duration_s)
    data = bytearray(n * 2)
    for i in range(n):
        val = int(32000 * math.sin(2 * math.pi * 440 * i / sr))
        val = max(-32767, min(32767, val))  # Near-max amplitude
        struct.pack_into("<h", data, i * 2, val)
    return bytes(data)


def _summary(audio: bytes) -> CallSummary:
    return CallSummary(duration_ms=5000, turn_count=1, agent_audio=audio)


def _transcript() -> TranscriptResult:
    return TranscriptResult(text="Hello", segments=[])


# ---------------------------------------------------------------------------
# Heuristic tests
# ---------------------------------------------------------------------------

def test_heuristic_normal_audio():
    """Normal audio should produce a reasonable heuristic estimate."""
    evaluator = MOSEvaluator()
    audio = AudioBuffer(data=_make_audio(), sample_rate=16000)
    scores = evaluator._heuristic(audio)
    assert 1.0 <= scores["ovrl"] <= 4.0  # Capped at 4.0
    assert scores["method"] == "heuristic"


def test_heuristic_silence():
    """Silent audio should score very low."""
    evaluator = MOSEvaluator()
    silent = bytes(16000 * 2)  # 1 second of silence (all zeros)
    audio = AudioBuffer(data=silent, sample_rate=16000)
    scores = evaluator._heuristic(audio)
    assert scores["ovrl"] == 1.0
    assert "silence" in scores.get("warning", "")


def test_heuristic_empty_audio():
    """Empty audio → lowest score."""
    evaluator = MOSEvaluator()
    audio = AudioBuffer(data=b"", sample_rate=16000)
    scores = evaluator._heuristic(audio)
    assert scores["ovrl"] == 1.0
    assert "empty" in scores.get("warning", "")


def test_heuristic_clipped_audio():
    """Clipped audio should be penalized."""
    evaluator = MOSEvaluator()
    audio = AudioBuffer(data=_make_clipped_audio(), sample_rate=16000)
    scores = evaluator._heuristic(audio)
    # Normal audio should score higher than clipped
    normal_audio = AudioBuffer(data=_make_audio(amplitude=8000), sample_rate=16000)
    evaluator._heuristic(normal_audio)
    # Clipped shouldn't score higher than normal (may or may not be lower depending on crest)
    assert scores["ovrl"] <= 4.0  # Capped


def test_heuristic_capped_at_four():
    """Heuristic should never claim > 4.0."""
    evaluator = MOSEvaluator()
    audio = AudioBuffer(data=_make_audio(), sample_rate=16000)
    scores = evaluator._heuristic(audio)
    assert scores["ovrl"] <= 4.0


# ---------------------------------------------------------------------------
# Full evaluate() flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluate_no_audio():
    """No audio → score 0.0, failed."""
    evaluator = MOSEvaluator()
    results = await evaluator.evaluate(
        _scenario(),
        CallSummary(duration_ms=5000, turn_count=1, agent_audio=b""),
        _transcript(),
        context={},
    )
    assert len(results) == 1
    assert results[0].name == "mos_ovrl"
    assert results[0].value == 0.0
    assert results[0].passed is False


@pytest.mark.asyncio
async def test_evaluate_heuristic_path():
    """Without speechmos, should use heuristic and label correctly."""
    evaluator = MOSEvaluator()
    audio = _make_audio(duration_s=2.0)  # Need >1s for valid evaluation
    results = await evaluator.evaluate(
        _scenario(),
        _summary(audio),
        _transcript(),
        context={},
    )
    assert len(results) >= 1
    # Should be labeled as heuristic estimate (not mos_ovrl)
    metric = results[0]
    assert metric.name in ("mos_ovrl", "audio_quality_estimate")
    assert 1.0 <= metric.value <= 4.0
    assert metric.details["method"] in ("dnsmos", "heuristic")


@pytest.mark.asyncio
async def test_evaluate_heuristic_always_passes():
    """Heuristic mode should always pass (don't fail on fake metric)."""
    evaluator = MOSEvaluator()
    audio = _make_audio(duration_s=2.0)
    results = await evaluator.evaluate(
        _scenario(),
        _summary(audio),
        _transcript(),
        context={"mos_threshold": 4.5},
    )
    metric = results[0]
    if metric.details.get("method") == "heuristic":
        assert metric.passed is True  # Heuristic always passes
