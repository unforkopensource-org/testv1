import json
from pathlib import Path

from decibench.models import AgentEvent, CallTrace, EventType, TranscriptSegment
from decibench.store.privacy import RedactionPolicy
from decibench.store.sqlite import RunStore


def test_redaction_policy():
    redactor = RedactionPolicy()

    # Text redaction
    assert redactor.redact_text("Call me at 555-123-4567") == "Call me at [REDACTED_PHONE]"
    assert redactor.redact_text("My SSN is 123-45-6789") == "My SSN is [REDACTED_SSN]"
    assert redactor.redact_text("Email test@example.com") == "Email [REDACTED_EMAIL]"
    assert redactor.redact_text("Card 1234-5678-1234-5678") == "Card [REDACTED_CARD]"

    # Dict redaction
    data = {
        "user": {
            "phone": "555-123-4567",
            "notes": ["sent to test@example.com"]
        },
        "id": 123
    }
    redacted = redactor.redact_dict(data)
    assert redacted["user"]["phone"] == "[REDACTED_PHONE]"
    assert redacted["user"]["notes"][0] == "sent to [REDACTED_EMAIL]"
    assert redacted["id"] == 123

def test_store_v2_initialization(tmp_path: Path):
    store = RunStore(tmp_path / "decibench.sqlite")

    with store._connect() as conn:
        # Check migrations table created
        row = conn.execute("SELECT MAX(version) as version FROM schema_migrations").fetchone()
        assert row["version"] == 2

        # Check meta table reflects v2
        meta_row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        assert meta_row["value"] == "2"

        # Check normalized tables exist
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [r["name"] for r in tables]
        assert "runs_scenarios" in table_names
        assert "runs_metrics" in table_names
        assert "traces_events" in table_names
        assert "traces_segments" in table_names

def test_store_v2_save_call_trace(tmp_path: Path):
    store = RunStore(tmp_path / "decibench.sqlite")

    trace = CallTrace(
        id="trace-123",
        source="jsonl",
        target="demo",
        events=[
            AgentEvent(type=EventType.TOOL_CALL, timestamp_ms=100.0, data={"tool": "get_weather"}),
        ],
        transcript=[
            TranscriptSegment(role="caller", text="My number is 555-123-4567", start_ms=0, end_ms=100)
        ]
    )

    store.save_call_trace(trace)

    with store._connect() as conn:
        # Check base table
        ct = conn.execute("SELECT * FROM call_traces").fetchall()
        assert len(ct) == 1
        assert "555-123-4567" not in ct[0]["payload"]
        assert "[REDACTED_PHONE]" in ct[0]["payload"]

        # Check events normalized
        ev = conn.execute("SELECT * FROM traces_events").fetchall()
        assert len(ev) == 1
        assert ev[0]["type"] == "tool_call"
        assert json.loads(ev[0]["data"]) == {"tool": "get_weather"}

        # Check segments normalized and redacted
        seg = conn.execute("SELECT * FROM traces_segments").fetchall()
        assert len(seg) == 1
        assert seg[0]["role"] == "caller"
        assert seg[0]["text"] == "My number is [REDACTED_PHONE]"

