"""Core data models for Decibench.

All models are immutable after creation (frozen=True where appropriate).
These are the data contracts between every module in the system.
"""

from __future__ import annotations

import hashlib
import time
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Audio primitives
# ---------------------------------------------------------------------------

class AudioEncoding(StrEnum):
    PCM_S16LE = "pcm_s16le"
    MULAW = "mulaw"
    OPUS = "opus"


class AudioBuffer(BaseModel):
    """Raw audio data with format metadata."""
    data: bytes
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16
    encoding: AudioEncoding = AudioEncoding.PCM_S16LE

    @property
    def duration_ms(self) -> float:
        """Calculate duration in milliseconds from buffer size."""
        if not self.data:
            return 0.0
        bytes_per_sample = self.bit_depth // 8
        total_samples = len(self.data) // (bytes_per_sample * self.channels)
        return (total_samples / self.sample_rate) * 1000.0

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Scenario models
# ---------------------------------------------------------------------------

class Persona(BaseModel):
    """Caller persona configuration for a test scenario."""
    name: str = "Default"
    accent: str = "en-US"
    voice: str = ""  # TTS voice ID; empty = auto-select from accent
    speaking_speed: float = Field(1.0, ge=0.3, le=3.0)
    patience_level: Literal["low", "medium", "high"] = "medium"
    background_noise: str = "clean"
    noise_level_db: float = Field(15.0, ge=0.0, le=40.0)
    behavior: dict[str, Any] = Field(default_factory=dict)


class TurnExpectation(BaseModel):
    """Expected behavior from the agent on a given turn."""
    intent: str | None = None
    must_ask: list[str] = Field(default_factory=list)
    must_not_say: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list)
    must_extract: dict[str, str] = Field(default_factory=dict)
    max_latency_ms: int | None = None
    tone: str | None = None


class ConversationTurn(BaseModel):
    """A single turn in a scripted conversation."""
    role: Literal["caller", "agent"]
    text: str | None = None
    expect: TurnExpectation | None = None
    audio_overrides: dict[str, Any] = Field(default_factory=dict)


class ToolMock(BaseModel):
    """Mock definition for an agent's tool call during testing."""
    name: str
    when_called_with: dict[str, Any] = Field(default_factory=dict)
    returns: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0


class SuccessCriterion(BaseModel):
    """A single success criterion for a scenario."""
    type: str  # task_completion | compliance | latency | no_hallucination | custom
    description: str | None = None
    check: Literal["deterministic", "llm_judge", "hybrid"] = "hybrid"
    rule: str | None = None
    threshold: float | None = None
    p95_max_ms: int | None = None


class VariantConfig(BaseModel):
    """Variant expansion configuration."""
    noise_levels: list[str] = Field(default_factory=lambda: ["clean"])
    accents: list[str] = Field(default_factory=lambda: ["en-US"])
    speeds: list[float] = Field(default_factory=lambda: [1.0])


class Scenario(BaseModel):
    """A complete test scenario definition."""
    id: str
    version: int = 1
    mode: Literal["scripted", "adaptive"] = "scripted"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    persona: Persona = Field(default_factory=Persona)
    conversation: list[ConversationTurn] = Field(default_factory=list)
    goal: str | None = None
    success_criteria: list[SuccessCriterion] = Field(default_factory=list)
    tool_mocks: list[ToolMock] = Field(default_factory=list)
    variants: VariantConfig = Field(default_factory=VariantConfig)
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    max_turns: int = Field(default=20, ge=1, le=100)

    @property
    def caller_turns(self) -> list[ConversationTurn]:
        return [t for t in self.conversation if t.role == "caller"]

    @property
    def agent_turns(self) -> list[ConversationTurn]:
        return [t for t in self.conversation if t.role == "agent"]


# ---------------------------------------------------------------------------
# Connector event models
# ---------------------------------------------------------------------------

class EventType(StrEnum):
    AGENT_AUDIO = "agent_audio"
    AGENT_TRANSCRIPT = "agent_transcript"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    INTERRUPTION = "interruption"
    TURN_END = "turn_end"
    METADATA = "metadata"
    ERROR = "error"


class AgentEvent(BaseModel):
    """An event emitted by an agent connector during a test."""
    type: EventType
    timestamp_ms: float
    data: dict[str, Any] = Field(default_factory=dict)
    audio: bytes | None = None

    model_config = {"arbitrary_types_allowed": True}


class ConnectionHandle(BaseModel):
    """Opaque handle for an active connection to a voice agent."""
    connector_type: str
    start_time_ns: int = Field(default_factory=time.monotonic_ns)
    state: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class TraceSpan(BaseModel):
    """Timing measurement for a specific component within a turn."""
    name: str  # e.g., 'asr', 'llm', 'tts', 'tool_call', 'turn_latency'
    start_ms: float
    end_ms: float
    duration_ms: float
    turn_index: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CallSummary(BaseModel):
    """Summary of a completed call to a voice agent."""
    duration_ms: float
    turn_count: int
    agent_audio: bytes = b""
    events: list[AgentEvent] = Field(default_factory=list)
    spans: list[TraceSpan] = Field(default_factory=list)
    platform_metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Evaluation result models
# ---------------------------------------------------------------------------

class MetricResult(BaseModel):
    """Result of a single metric evaluation."""
    name: str
    value: float
    unit: str = ""
    passed: bool = True
    threshold: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class EvalResult(BaseModel):
    """Complete evaluation result for a single scenario run."""
    scenario_id: str
    passed: bool
    score: float = Field(ge=0, le=100)
    metrics: dict[str, MetricResult] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)
    failure_summary: list[str] = Field(default_factory=list)  # Failed categories: ["latency", "compliance"]
    latency: dict[str, float] = Field(default_factory=dict)
    cost: dict[str, float] = Field(default_factory=dict)
    duration_ms: float = 0
    transcript: list[dict[str, Any]] = Field(default_factory=list)
    run_index: int = 0
    spans: list[TraceSpan] = Field(default_factory=list)

    @property
    def metric_values(self) -> dict[str, float]:
        """Flat dict of metric_name → value for quick access."""
        return {name: m.value for name, m in self.metrics.items()}


class CostBreakdown(BaseModel):
    """Cost tracking for a test run."""
    tts: float = 0.0
    stt: float = 0.0
    judge: float = 0.0
    platform: float = 0.0

    @property
    def total(self) -> float:
        return self.tts + self.stt + self.judge + self.platform


class SuiteResult(BaseModel):
    """Complete result of running a test suite."""
    suite: str
    target: str
    decibench_score: float = Field(ge=0, le=100)
    score_breakdown: dict[str, float] = Field(default_factory=dict)  # category → score (0-100)
    total_scenarios: int
    passed: int
    failed: int
    results: list[EvalResult] = Field(default_factory=list)
    latency: dict[str, float] = Field(default_factory=dict)
    cost: CostBreakdown = Field(default_factory=CostBreakdown)
    duration_seconds: float = 0.0
    judge_model: str = ""  # Which LLM judge was used, or "none"
    config_hash: str = ""
    timestamp: str = ""
    decibench_version: str = "1.0.0"

    @classmethod
    def compute_config_hash(cls, config_dict: dict[str, Any]) -> str:
        """Deterministic hash of config for reproducibility tracking."""
        import json
        serialized = json.dumps(config_dict, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Transcript model
# ---------------------------------------------------------------------------

class TranscriptSegment(BaseModel):
    """A segment of transcribed speech."""
    role: Literal["caller", "agent"]
    text: str
    start_ms: float = 0.0
    end_ms: float = 0.0
    confidence: float = 1.0
    words: list[dict[str, Any]] = Field(default_factory=list)


class TranscriptResult(BaseModel):
    """Result from STT transcription."""
    text: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    language: str = "en"
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Production call / replay models
# ---------------------------------------------------------------------------

class CallTrace(BaseModel):
    """Normalized production or test call trace for replay and analysis.

    A trace is intentionally provider-neutral: importers should preserve raw
    platform payloads in metadata, but normalize the transcript and event stream
    so evaluators, reports, and future dashboards can use one shape.
    """

    id: str
    source: str = "unknown"
    target: str = ""
    started_at: str = ""
    duration_ms: float = 0.0
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    events: list[AgentEvent] = Field(default_factory=list)
    spans: list[TraceSpan] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    imported_at: str = ""

    @property
    def text(self) -> str:
        """Human-readable transcript text."""
        return "\n".join(f"{segment.role}: {segment.text}" for segment in self.transcript)
