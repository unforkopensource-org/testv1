"""Centralized registry for TTS, STT, and LLM judge providers.

Uses Protocol classes to define the interface contract and a decorator-based
registration pattern. Providers are resolved by URI scheme at runtime.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from decibench.models import AudioBuffer, TranscriptResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider protocols (interfaces)
# ---------------------------------------------------------------------------

@runtime_checkable
class TTSProvider(Protocol):
    """Interface for text-to-speech providers."""

    async def synthesize(
        self,
        text: str,
        voice: str = "",
        speed: float = 1.0,
    ) -> AudioBuffer:
        """Convert text to speech audio."""
        ...

    async def list_voices(self) -> list[dict[str, Any]]:
        """List available voices."""
        ...

    async def close(self) -> None:
        """Release resources."""
        ...


@runtime_checkable
class STTProvider(Protocol):
    """Interface for speech-to-text providers."""

    async def transcribe(self, audio: AudioBuffer) -> TranscriptResult:
        """Transcribe audio to text."""
        ...

    async def close(self) -> None:
        """Release resources."""
        ...


class JudgeResult:
    """Result from an LLM judge evaluation."""

    __slots__ = ("passed", "raw_output", "reasoning", "score")

    def __init__(
        self,
        passed: bool,
        score: float,
        reasoning: str = "",
        raw_output: str = "",
    ) -> None:
        self.passed = passed
        self.score = score
        self.reasoning = reasoning
        self.raw_output = raw_output


@runtime_checkable
class JudgeProvider(Protocol):
    """Interface for LLM-as-judge providers."""

    async def evaluate(self, prompt: str, context: dict[str, Any]) -> JudgeResult:
        """Evaluate using LLM judge."""
        ...

    async def close(self) -> None:
        """Release resources."""
        ...


# ---------------------------------------------------------------------------
# Registry storage
# ---------------------------------------------------------------------------

_tts_registry: dict[str, type[Any]] = {}
_stt_registry: dict[str, type[Any]] = {}
_judge_registry: dict[str, type[Any]] = {}


# ---------------------------------------------------------------------------
# Registration decorators
# ---------------------------------------------------------------------------

def register_tts(scheme: str) -> Callable[[type[Any]], type[Any]]:
    """Register a TTS provider class for a URI scheme."""
    def decorator(cls: type[Any]) -> type[Any]:
        _tts_registry[scheme] = cls
        logger.debug("Registered TTS provider: %s -> %s", scheme, cls.__name__)
        return cls
    return decorator


def register_stt(scheme: str) -> Callable[[type[Any]], type[Any]]:
    """Register an STT provider class for a URI scheme."""
    def decorator(cls: type[Any]) -> type[Any]:
        _stt_registry[scheme] = cls
        logger.debug("Registered STT provider: %s -> %s", scheme, cls.__name__)
        return cls
    return decorator


def register_judge(scheme: str) -> Callable[[type[Any]], type[Any]]:
    """Register an LLM judge provider class for a URI scheme."""
    def decorator(cls: type[Any]) -> type[Any]:
        _judge_registry[scheme] = cls
        logger.debug("Registered judge provider: %s -> %s", scheme, cls.__name__)
        return cls
    return decorator


# ---------------------------------------------------------------------------
# Resolution functions
# ---------------------------------------------------------------------------

def _parse_scheme(uri: str) -> tuple[str, str]:
    """Extract scheme and remainder from a provider URI.

    Examples:
        'edge-tts'                     -> ('edge-tts', '')
        'faster-whisper:base'          -> ('faster-whisper', 'base')
        'openai-compat://host:port/v1' -> ('openai-compat', '//host:port/v1')
    """
    if "://" in uri:
        scheme, rest = uri.split("://", 1)
        return scheme, f"//{rest}"
    if ":" in uri:
        scheme, rest = uri.split(":", 1)
        return scheme, rest
    return uri, ""


def get_tts(uri: str, **kwargs: Any) -> Any:
    """Resolve and instantiate a TTS provider from URI."""
    scheme, config_str = _parse_scheme(uri)
    if scheme not in _tts_registry:
        available = ", ".join(sorted(_tts_registry.keys())) or "none"
        msg = f"Unknown TTS provider: '{scheme}'. Available: {available}"
        raise ValueError(msg)
    return _tts_registry[scheme](uri=uri, config_str=config_str, **kwargs)


def get_stt(uri: str, **kwargs: Any) -> Any:
    """Resolve and instantiate an STT provider from URI."""
    scheme, config_str = _parse_scheme(uri)
    if scheme not in _stt_registry:
        available = ", ".join(sorted(_stt_registry.keys())) or "none"
        msg = f"Unknown STT provider: '{scheme}'. Available: {available}"
        raise ValueError(msg)
    return _stt_registry[scheme](uri=uri, config_str=config_str, **kwargs)


def get_judge(uri: str, **kwargs: Any) -> Any:
    """Resolve and instantiate an LLM judge provider from URI."""
    scheme, config_str = _parse_scheme(uri)
    if scheme not in _judge_registry:
        available = ", ".join(sorted(_judge_registry.keys())) or "none"
        msg = f"Unknown judge provider: '{scheme}'. Available: {available}"
        raise ValueError(msg)
    return _judge_registry[scheme](uri=uri, config_str=config_str, **kwargs)
