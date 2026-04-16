"""Configuration loading and validation for Decibench.

Loads decibench.toml, expands environment variables, validates with Pydantic,
and resolves profiles. The config object is immutable after creation.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from decibench.llm_catalog import judge_provider_from_uri
from decibench.secrets import resolve_secret

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

DEFAULT_CONFIG_NAME = "decibench.toml"


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand ${VAR} patterns in strings from environment."""
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            env_val = os.environ.get(var_name)
            if env_val is None:
                return match.group(0)  # Leave unexpanded if not set
            return env_val
        return _ENV_VAR_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


class ProjectConfig(BaseModel):
    """[project] section."""
    name: str = "my-voice-agent"


class TargetConfig(BaseModel):
    """[target] section."""
    default: str = "demo"


class AuthConfig(BaseModel):
    """[auth] section — values may come from config, env vars, or keyring."""
    model_config = {"extra": "allow"}

    vapi_api_key: str = ""
    retell_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""


class ProvidersConfig(BaseModel):
    """[providers] section — pluggable TTS, STT, and LLM judge."""
    tts: str = "edge-tts"
    tts_voice: str = "en-US-JennyNeural"
    stt: str = "faster-whisper:base"
    judge: str = "none"
    judge_model: str = ""
    judge_api_key: str = ""


class AudioConfig(BaseModel):
    """[audio] section."""
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16
    noise_profiles_dir: str = "./noise_profiles"


class EvaluationConfig(BaseModel):
    """[evaluation] section."""
    runs_per_scenario: int = Field(default=1, ge=1, le=20)
    judge_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    judge_runs: int = Field(default=1, ge=1, le=5)  # 3 = median-of-3 for stability
    timeout_seconds: int = Field(default=120, ge=10, le=600)


class ScoringWeights(BaseModel):
    """[scoring.weights] section — all weights must sum to 1.0."""
    task_completion: float = 0.25
    latency: float = 0.20
    audio_quality: float = 0.15
    conversation: float = 0.15
    robustness: float = 0.10
    interruption: float = 0.10
    compliance: float = 0.05

    @model_validator(mode="after")
    def _validate_weights_sum(self) -> ScoringWeights:
        total = (
            self.task_completion
            + self.latency
            + self.audio_quality
            + self.conversation
            + self.robustness
            + self.interruption
            + self.compliance
        )
        if abs(total - 1.0) > 0.01:
            msg = f"Scoring weights must sum to 1.0, got {total:.3f}"
            raise ValueError(msg)
        return self


class ScoringConfig(BaseModel):
    """[scoring] section."""
    weights: ScoringWeights = Field(default_factory=ScoringWeights)


class CIConfig(BaseModel):
    """[ci] section."""
    min_score: float = Field(default=80.0, ge=0.0, le=100.0)
    max_p95_latency_ms: int = Field(default=1500, ge=100)
    fail_on_compliance_violation: bool = True


class ProfileConfig(BaseModel):
    """A named configuration profile (e.g., dev, ci, benchmark)."""
    suite: str = "quick"
    runs_per_scenario: int = Field(default=1, ge=1, le=20)
    min_score: float = Field(default=0.0, ge=0.0, le=100.0)
    noise_levels: list[str] = Field(default_factory=lambda: ["clean"])
    accents: list[str] = Field(default_factory=lambda: ["en-US"])


class DecibenchConfig(BaseModel):
    """Root configuration model for decibench.toml."""
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    target: TargetConfig = Field(default_factory=TargetConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    ci: CIConfig = Field(default_factory=CIConfig)
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _populate_runtime_secrets(self) -> DecibenchConfig:
        return _resolve_config_secrets(self)

    @classmethod
    def from_toml(cls, path: Path) -> DecibenchConfig:
        """Load config from a TOML file, expanding environment variables."""
        with open(path, "rb") as f:
            raw = tomllib.load(f)
        expanded = _expand_env_vars(raw)
        return cls.model_validate(expanded)

    @classmethod
    def defaults(cls) -> DecibenchConfig:
        """Return default configuration (no file needed)."""
        return cls()

    def with_profile(self, profile_name: str) -> DecibenchConfig:
        """Return a new config with profile overrides applied."""
        if profile_name not in self.profiles:
            msg = (
                f"Profile '{profile_name}' not found. "
                f"Available: {list(self.profiles.keys())}"
            )
            raise ValueError(msg)
        profile = self.profiles[profile_name]
        data = self.model_dump()
        data["evaluation"]["runs_per_scenario"] = profile.runs_per_scenario
        data["ci"]["min_score"] = profile.min_score
        return DecibenchConfig.model_validate(data)

    @property
    def has_judge(self) -> bool:
        """Whether an LLM judge is configured."""
        return self.providers.judge != "none"


def find_config(start_dir: Path | None = None) -> Path | None:
    """Walk up from start_dir looking for decibench.toml."""
    current = start_dir or Path.cwd()
    for directory in [current, *current.parents]:
        candidate = directory / DEFAULT_CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def load_config(
    config_path: Path | None = None,
    profile: str | None = None,
) -> DecibenchConfig:
    """Load config from file or defaults, optionally applying a profile."""
    if config_path is None:
        config_path = find_config()

    if config_path is not None and config_path.is_file():
        config = DecibenchConfig.from_toml(config_path)
    else:
        config = DecibenchConfig.defaults()

    if profile is not None:
        config = config.with_profile(profile)

    return config


def _resolve_config_secrets(config: DecibenchConfig) -> DecibenchConfig:
    """Populate secret-bearing config fields from env vars or keyring."""
    config.auth.vapi_api_key = resolve_secret("vapi", config.auth.vapi_api_key)
    config.auth.retell_api_key = resolve_secret("retell", config.auth.retell_api_key)
    config.auth.openai_api_key = resolve_secret("openai", config.auth.openai_api_key)
    config.auth.anthropic_api_key = resolve_secret("anthropic", config.auth.anthropic_api_key)
    config.auth.gemini_api_key = resolve_secret("gemini", config.auth.gemini_api_key)

    judge_provider = judge_provider_from_uri(config.providers.judge)
    if judge_provider == "openai":
        config.providers.judge_api_key = resolve_secret(
            "openai",
            config.providers.judge_api_key or config.auth.openai_api_key,
        )
    elif judge_provider == "anthropic":
        config.providers.judge_api_key = resolve_secret(
            "anthropic",
            config.providers.judge_api_key or config.auth.anthropic_api_key,
        )
    elif judge_provider == "gemini":
        config.providers.judge_api_key = resolve_secret(
            "gemini",
            config.providers.judge_api_key or config.auth.gemini_api_key,
        )

    return config
