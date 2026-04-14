"""Provider registry for pluggable TTS, STT, and LLM judge backends."""

import decibench.providers.judge.none
import decibench.providers.judge.openai_compat
import decibench.providers.stt.faster_whisper
import decibench.providers.stt.openai_compat

# Import all built-in providers to trigger registration
import decibench.providers.tts.edge
import decibench.providers.tts.openai_compat  # noqa: F401
from decibench.providers.registry import (
    get_judge,
    get_stt,
    get_tts,
    register_judge,
    register_stt,
    register_tts,
)

__all__ = [
    "get_judge",
    "get_stt",
    "get_tts",
    "register_judge",
    "register_stt",
    "register_tts",
]
