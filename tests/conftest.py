"""Shared test fixtures for Decibench test suite."""

from __future__ import annotations

import pytest

from decibench.config import DecibenchConfig
from decibench.models import (
    AudioBuffer,
    ConversationTurn,
    Scenario,
    SuccessCriterion,
    TurnExpectation,
)


@pytest.fixture
def default_config() -> DecibenchConfig:
    """Default test configuration."""
    return DecibenchConfig.defaults()


@pytest.fixture
def sample_audio() -> AudioBuffer:
    """Sample 1-second PCM audio buffer (sine wave)."""
    import math
    import struct

    sample_rate = 16000
    duration_s = 1.0
    frequency = 440.0
    num_samples = int(sample_rate * duration_s)

    data = bytearray(num_samples * 2)
    for i in range(num_samples):
        value = int(16000 * math.sin(2 * math.pi * frequency * i / sample_rate))
        struct.pack_into("<h", data, i * 2, value)

    return AudioBuffer(data=bytes(data), sample_rate=sample_rate)


@pytest.fixture
def sample_scenario() -> Scenario:
    """Sample test scenario for unit tests."""
    return Scenario(
        id="test-001",
        description="Test scenario",
        conversation=[
            ConversationTurn(role="caller", text="Hello"),
            ConversationTurn(
                role="agent",
                expect=TurnExpectation(
                    intent="greeting",
                    must_include=["hello", "help"],
                    max_latency_ms=800,
                ),
            ),
        ],
        success_criteria=[
            SuccessCriterion(type="task_completion"),
        ],
    )
