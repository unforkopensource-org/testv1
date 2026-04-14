import json
from pathlib import Path

from decibench.models import AgentEvent, CallTrace, EvalResult, EventType, MetricResult, TranscriptSegment
from decibench.store.privacy import RedactionPolicy
from decibench.store.sqlite import RunStore


def test_redaction_policy():
    redactor = RedactionPolicy()

    # Text redaction
    assert redactor.redact_text("Call me at 555-123-4567") == "Call me at [REDACTED_PHONE]"
    assert redactor.redact_text("My SSN is 123-45-6789") == "My SSN is [REDACTED_SSN]"
    assert redactor.redact_text("Email test@example.com") == "Email [REDACTED_EMAIL]"
    assert redactor.redact_text("Card 4111-1111-1111-1111") == "Card [REDACTED_CARD]"

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
        assert row["version"] == 3

        # Check meta table reflects latest schema
        meta_row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        assert meta_row["value"] == "3"

        # Check normalized tables exist
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [r["name"] for r in tables]
        assert "runs_scenarios" in table_names
        assert "runs_metrics" in table_names
        assert "traces_events" in table_names
        assert "traces_segments" in table_names
        assert "call_evaluations" in table_names
        assert "call_evaluation_metrics" in table_names

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


def test_store_v3_save_call_evaluation(tmp_path: Path):
    store = RunStore(tmp_path / "decibench.sqlite")
    trace = CallTrace(id="trace-456", source="retell", target="demo")
    result = EvalResult(
        scenario_id="imported-trace-456",
        passed=False,
        score=42.0,
        metrics={
            "latency_p95": MetricResult(
                name="latency_p95",
                value=2200.0,
                unit="ms",
                passed=False,
            )
        },
        failures=["latency_p95: 2200.0 (threshold: 1500.0)"],
        failure_summary=["latency"],
    )

    evaluation_id = store.save_call_evaluation(trace, result)

    rows = store.list_call_evaluations(limit=10, source="retell", failed_only=True, category="latency")
    assert len(rows) == 1
    assert rows[0]["id"] == evaluation_id
    assert rows[0]["call_id"] == "trace-456"
    assert rows[0]["failure_summary"] == ["latency"]

    loaded = store.get_call_evaluation(evaluation_id)
    assert loaded is not None
    assert loaded.score == 42.0
    assert loaded.failure_summary == ["latency"]

    with store._connect() as conn:
        metric_rows = conn.execute("SELECT * FROM call_evaluation_metrics").fetchall()
        assert len(metric_rows) == 1
        assert metric_rows[0]["name"] == "latency_p95"
