"""Helpers for creating and updating `decibench.toml`."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from decibench.llm_catalog import get_provider_catalog

if TYPE_CHECKING:
    from pathlib import Path

_SECTION_RE = re.compile(r"^\[(?P<section>[^\]]+)\]\s*$")


def build_config_text(
    *,
    project_name: str,
    target: str,
    judge_uri: str = "none",
    judge_model: str = "",
) -> str:
    """Build a fresh project config with current local-product defaults."""
    guidance = (
        "# Secrets are managed locally by `decibench auth set <provider>`.\n"
        "# Environment variable fallback is also supported.\n"
    )
    lines = [
        "# Decibench local project configuration",
        "",
        "[project]",
        f'name = {json.dumps(project_name)}',
        "",
        "[target]",
        f"default = {json.dumps(target)}",
        "",
        "[auth]",
        guidance.rstrip(),
        'vapi_api_key = ""',
        'retell_api_key = ""',
        'openai_api_key = ""',
        'anthropic_api_key = ""',
        'gemini_api_key = ""',
        "",
        "[providers]",
        'tts = "edge-tts"',
        'tts_voice = "en-US-JennyNeural"',
        'stt = "faster-whisper:base"',
        f"judge = {json.dumps(judge_uri)}",
        f"judge_model = {json.dumps(judge_model)}",
        'judge_api_key = ""',
        "",
        "[connector]",
        "# WebSocket protocol: auto, raw-pcm, openai-realtime, twilio, gemini-live",
        '# \"auto\" detects the protocol from the server\'s first message.',
        'ws_protocol = "auto"',
        "# Override individual settings (leave empty to use preset defaults):",
        '# ws_send_format = "json_base64"',
        '# ws_commit_message = \'{"type": "input_audio_buffer.commit"}\'',
        '# ws_setup_message = ""',
        "",
        "[audio]",
        "sample_rate = 16000",
        'noise_profiles_dir = "./noise_profiles"',
        "",
        "[evaluation]",
        "runs_per_scenario = 1",
        "judge_temperature = 0.0",
        "timeout_seconds = 120",
        "",
        "[scoring.weights]",
        "task_completion = 0.25",
        "latency = 0.20",
        "audio_quality = 0.15",
        "conversation = 0.15",
        "robustness = 0.10",
        "interruption = 0.10",
        "compliance = 0.05",
        "",
        "[ci]",
        "min_score = 80",
        "max_p95_latency_ms = 1500",
        "fail_on_compliance_violation = true",
        "",
        "[profiles.dev]",
        'suite = "quick"',
        "runs_per_scenario = 1",
        "",
        "[profiles.ci]",
        'suite = "standard"',
        "runs_per_scenario = 3",
        "min_score = 80",
    ]
    return "\n".join(lines) + "\n"


def update_judge_settings(path: Path, *, provider: str, model: str) -> None:
    """Update or create judge settings in `decibench.toml`."""
    catalog = get_provider_catalog(provider)
    text = _read_or_default(path)
    text = upsert_toml_key(text, "providers", "judge", catalog.judge_uri)
    text = upsert_toml_key(text, "providers", "judge_model", model)
    path.write_text(text, encoding="utf-8")


def upsert_toml_key(text: str, section: str, key: str, value: str | int | float | bool) -> str:
    """Upsert a simple scalar key in a TOML section."""
    rendered = f"{key} = {_serialize_toml(value)}"
    lines = text.splitlines()

    section_start: int | None = None
    section_end = len(lines)

    for index, line in enumerate(lines):
        match = _SECTION_RE.match(line.strip())
        if not match:
            continue
        current_section = match.group("section")
        if current_section == section:
            section_start = index
            continue
        if section_start is not None:
            section_end = index
            break

    if section_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"[{section}]", rendered])
        return "\n".join(lines) + "\n"

    for index in range(section_start + 1, section_end):
        stripped = lines[index].strip()
        if stripped.startswith(f"{key} ="):
            lines[index] = rendered
            return "\n".join(lines) + "\n"

    insert_at = section_end
    lines.insert(insert_at, rendered)
    return "\n".join(lines) + "\n"


def _serialize_toml(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(value)


def _read_or_default(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return build_config_text(project_name=path.parent.name or "my-voice-agent", target="demo")
