"""Tests for core data models."""

from __future__ import annotations

from decibench.models import (
    AudioBuffer,
    CostBreakdown,
    EvalResult,
    MetricResult,
    Persona,
    Scenario,
    SuiteResult,
)


def test_audio_buffer_duration():
    # 1 second of 16kHz 16-bit mono = 32000 bytes
    buf = AudioBuffer(data=b"\x00" * 32000, sample_rate=16000)
    assert abs(buf.duration_ms - 1000.0) < 0.1


def test_audio_buffer_duration_empty():
    buf = AudioBuffer(data=b"")
    assert buf.duration_ms == 0.0


def test_persona_defaults():
    persona = Persona()
    assert persona.accent == "en-US"
    assert persona.speaking_speed == 1.0
    assert persona.background_noise == "clean"


def test_scenario_caller_turns():
    from decibench.models import ConversationTurn, TurnExpectation

    scenario = Scenario(
        id="test",
        conversation=[
            ConversationTurn(role="caller", text="Hello"),
            ConversationTurn(role="agent", expect=TurnExpectation(intent="greeting")),
            ConversationTurn(role="caller", text="Book me"),
            ConversationTurn(role="agent", expect=TurnExpectation(intent="booking")),
        ],
    )
    assert len(scenario.caller_turns) == 2
    assert len(scenario.agent_turns) == 2


def test_cost_breakdown():
    cost = CostBreakdown(tts=0.01, stt=0.02, judge=0.10, platform=0.50)
    assert cost.total == 0.63


def test_eval_result_metric_values():
    result = EvalResult(
        scenario_id="test",
        passed=True,
        score=85.0,
        metrics={
            "wer": MetricResult(name="wer", value=3.5, unit="%", passed=True),
            "latency": MetricResult(name="latency", value=650.0, unit="ms", passed=True),
        },
    )
    assert result.metric_values == {"wer": 3.5, "latency": 650.0}


def test_suite_result_config_hash():
    hash1 = SuiteResult.compute_config_hash({"a": 1, "b": 2})
    hash2 = SuiteResult.compute_config_hash({"b": 2, "a": 1})
    assert hash1 == hash2  # Order-independent

    hash3 = SuiteResult.compute_config_hash({"a": 1, "b": 3})
    assert hash1 != hash3
