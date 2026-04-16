"""Tests for configuration loading and validation."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from decibench.config import DecibenchConfig


def test_default_config():
    config = DecibenchConfig.defaults()
    assert config.project.name == "my-voice-agent"
    assert config.target.default == "demo"
    assert config.providers.tts == "edge-tts"
    assert config.providers.stt == "faster-whisper:base"
    assert config.providers.judge == "none"
    assert config.auth.anthropic_api_key == ""
    assert config.auth.gemini_api_key == ""
    assert not config.has_judge


def test_config_has_judge():
    config = DecibenchConfig.defaults()
    assert not config.has_judge

    config.providers.judge = "openai-compat://localhost:11434/v1"
    assert config.has_judge


def test_scoring_weights_sum():
    config = DecibenchConfig.defaults()
    weights = config.scoring.weights
    total = (
        weights.task_completion
        + weights.latency
        + weights.audio_quality
        + weights.conversation
        + weights.robustness
        + weights.interruption
        + weights.compliance
    )
    assert abs(total - 1.0) < 0.01


def test_scoring_weights_validation():
    with pytest.raises(ValueError):
        DecibenchConfig.model_validate({
            "scoring": {
                "weights": {
                    "task_completion": 0.5,
                    "latency": 0.5,
                    "audio_quality": 0.5,
                    "conversation": 0.0,
                    "robustness": 0.0,
                    "interruption": 0.0,
                    "compliance": 0.0,
                }
            }
        })


def test_load_from_toml():
    toml_content = """
[project]
name = "test-agent"

[target]
default = "ws://localhost:8080"

[providers]
tts = "edge-tts"
judge = "none"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(toml_content)
        f.flush()
        config = DecibenchConfig.from_toml(Path(f.name))

    os.unlink(f.name)
    assert config.project.name == "test-agent"
    assert config.target.default == "ws://localhost:8080"


def test_env_var_expansion():
    toml_content = """
[auth]
vapi_api_key = "${TEST_DECIBENCH_KEY}"
"""
    os.environ["TEST_DECIBENCH_KEY"] = "test-secret-123"
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            config = DecibenchConfig.from_toml(Path(f.name))

        os.unlink(f.name)
        assert config.auth.vapi_api_key == "test-secret-123"
    finally:
        del os.environ["TEST_DECIBENCH_KEY"]


def test_judge_api_key_inferred_from_auth():
    config = DecibenchConfig.model_validate({
        "auth": {"anthropic_api_key": "anthropic-secret"},
        "providers": {
            "judge": "anthropic",
            "judge_model": "claude-sonnet-4-20250514",
        },
    })
    assert config.providers.judge_api_key == "anthropic-secret"


def test_profile_application():
    config = DecibenchConfig.model_validate({
        "profiles": {
            "ci": {
                "suite": "standard",
                "runs_per_scenario": 3,
                "min_score": 85.0,
            }
        }
    })
    ci_config = config.with_profile("ci")
    assert ci_config.evaluation.runs_per_scenario == 3
    assert ci_config.ci.min_score == 85.0


def test_profile_not_found():
    config = DecibenchConfig.defaults()
    with pytest.raises(ValueError, match="not found"):
        config.with_profile("nonexistent")
