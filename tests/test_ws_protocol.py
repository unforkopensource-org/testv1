"""Tests for WebSocket protocol presets and auto-detection.

Validates that the connector correctly handles different voice agent
protocols without requiring a live WebSocket server.
"""

from __future__ import annotations

import json

import pytest

from decibench.connectors.websocket import (
    PROTOCOL_PRESETS,
    WebSocketConnector,
    _detect_protocol_from_message,
)


# ---------------------------------------------------------------------------
# Preset registry
# ---------------------------------------------------------------------------


def test_preset_registry_has_all_expected_presets():
    assert "raw-pcm" in PROTOCOL_PRESETS
    assert "openai-realtime" in PROTOCOL_PRESETS
    assert "twilio" in PROTOCOL_PRESETS
    assert "gemini-live" in PROTOCOL_PRESETS


def test_openai_preset_has_correct_settings():
    preset = PROTOCOL_PRESETS["openai-realtime"]
    assert preset["sample_rate"] == 24000
    assert preset["ws_send_format"] == "json_base64"
    assert "input_audio_buffer.commit" in preset["ws_commit_message"]


def test_twilio_preset_has_correct_settings():
    preset = PROTOCOL_PRESETS["twilio"]
    assert preset["sample_rate"] == 8000
    assert preset["ws_send_format"] == "json_base64"


def test_gemini_preset_has_correct_settings():
    preset = PROTOCOL_PRESETS["gemini-live"]
    assert preset["sample_rate"] == 16000
    assert preset["ws_send_format"] == "json_base64"


def test_raw_pcm_preset_has_correct_settings():
    preset = PROTOCOL_PRESETS["raw-pcm"]
    assert preset["sample_rate"] == 16000
    assert preset["ws_send_format"] == "binary"


# ---------------------------------------------------------------------------
# Protocol fingerprinting
# ---------------------------------------------------------------------------


def test_detect_openai_session_created():
    msg = {"type": "session.created", "session": {"id": "sess_123"}}
    assert _detect_protocol_from_message(msg) == "openai-realtime"


def test_detect_openai_session_update():
    msg = {"type": "session.update"}
    assert _detect_protocol_from_message(msg) == "openai-realtime"


def test_detect_twilio_connected():
    msg = {"event": "connected", "protocol": "Call", "version": "1.0.0"}
    assert _detect_protocol_from_message(msg) == "twilio"


def test_detect_twilio_start():
    msg = {"event": "start", "start": {"streamSid": "MZ123", "callSid": "CA456"}}
    assert _detect_protocol_from_message(msg) == "twilio"


def test_detect_gemini_setup_complete():
    msg = {"setupComplete": {}}
    assert _detect_protocol_from_message(msg) == "gemini-live"


def test_detect_gemini_server_content():
    msg = {"serverContent": {"modelTurn": {"parts": []}}}
    assert _detect_protocol_from_message(msg) == "gemini-live"


def test_detect_unknown_json():
    msg = {"foo": "bar", "baz": 42}
    assert _detect_protocol_from_message(msg) is None


# ---------------------------------------------------------------------------
# Connector initialization and preset application
# ---------------------------------------------------------------------------


def test_connector_defaults_to_auto_protocol():
    ws = WebSocketConnector()
    assert ws._send_format == "binary"
    assert ws.required_sample_rate == 16000


def test_apply_preset_updates_connector_state():
    ws = WebSocketConnector()
    ws._apply_preset("openai-realtime")
    assert ws.required_sample_rate == 24000
    assert ws._send_format == "json_base64"
    assert ws._commit_message is not None
    assert ws._commit_message["type"] == "input_audio_buffer.commit"


def test_apply_preset_gemini():
    ws = WebSocketConnector()
    ws._apply_preset("gemini-live")
    assert ws.required_sample_rate == 16000
    assert ws._send_format == "json_base64"
    assert ws._recv_timeout == 5.0


def test_apply_preset_unknown_is_noop():
    ws = WebSocketConnector()
    original_rate = ws.required_sample_rate
    ws._apply_preset("nonexistent-preset")
    assert ws.required_sample_rate == original_rate


# ---------------------------------------------------------------------------
# Audio extraction — Gemini Live format
# ---------------------------------------------------------------------------


def test_extract_gemini_audio():
    import base64

    audio_data = b"\x00\x01\x02" * 100  # > 100 bytes
    b64 = base64.b64encode(audio_data).decode()
    msg = {
        "serverContent": {
            "modelTurn": {
                "parts": [
                    {"inlineData": {"mimeType": "audio/pcm", "data": b64}}
                ]
            }
        }
    }
    result = WebSocketConnector._extract_json_audio(msg)
    assert result == audio_data


def test_extract_gemini_audio_empty_parts():
    msg = {"serverContent": {"modelTurn": {"parts": []}}}
    assert WebSocketConnector._extract_json_audio(msg) is None


# ---------------------------------------------------------------------------
# Message parsing
# ---------------------------------------------------------------------------


def test_parse_message_binary():
    ws = WebSocketConnector()
    import time
    start_ns = time.monotonic_ns()
    event = ws._parse_message(b"\x00\x01\x02\x03", start_ns)
    assert event is not None
    assert event.type.value == "agent_audio"


def test_parse_message_json_transcript():
    ws = WebSocketConnector()
    import time
    start_ns = time.monotonic_ns()
    msg = json.dumps({"text": "Hello, how can I help?"})
    event = ws._parse_message(msg, start_ns)
    assert event is not None
    assert event.type.value == "agent_transcript"


def test_parse_message_json_error():
    ws = WebSocketConnector()
    import time
    start_ns = time.monotonic_ns()
    msg = json.dumps({"error": "something went wrong"})
    event = ws._parse_message(msg, start_ns)
    assert event is not None
    assert event.type.value == "error"
