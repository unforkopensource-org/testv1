from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from decibench.api.app import app
from decibench.models import CallTrace, TraceSpan, TranscriptSegment
from decibench.store import RunStore

if TYPE_CHECKING:
    from pathlib import Path

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "version" in response.json()


def test_runs_endpoint_returns_json():
    response = client.get("/runs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_calls_endpoint_returns_json():
    response = client.get("/calls")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_invalid_run():
    response = client.get("/runs/invalid-12345")
    assert response.status_code == 404


def test_get_invalid_call():
    response = client.get("/calls/invalid-12345")
    assert response.status_code == 404


def test_call_scenario_endpoint(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))
    store = RunStore(store_path)
    store.save_call_trace(
        CallTrace(
            id="call-123",
            source="jsonl",
            transcript=[
                TranscriptSegment(role="caller", text="Where is my order?"),
                TranscriptSegment(role="agent", text="I can check your order status."),
            ],
        )
    )

    response = client.get("/calls/call-123/scenario")

    assert response.status_code == 200
    assert response.text.startswith("id: regression-call-123")
    assert "source_call_id: call-123" in response.text


def test_call_evaluate_endpoint(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))
    store = RunStore(store_path)
    store.save_call_trace(
        CallTrace(
            id="call-456",
            source="jsonl",
            transcript=[
                TranscriptSegment(role="caller", text="I need help with billing."),
                TranscriptSegment(role="agent", text="I can help with your billing question."),
            ],
        )
    )

    response = client.get("/calls/call-456/evaluate")

    assert response.status_code == 200
    data = response.json()
    assert data["scenario_id"] == "imported-call-456"
    assert "passed" in data

    latest_response = client.get("/calls/call-456/evaluation")
    assert latest_response.status_code == 200
    assert latest_response.json()["scenario_id"] == "imported-call-456"

    list_response = client.get("/call-evaluations", params={"call_id": "call-456"})
    assert list_response.status_code == 200
    evaluations = list_response.json()
    assert len(evaluations) == 1
    assert evaluations[0]["call_id"] == "call-456"

    detail_response = client.get(f"/call-evaluations/{evaluations[0]['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["scenario_id"] == "imported-call-456"


def test_call_timeline_endpoint(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))
    store = RunStore(store_path)
    store.save_call_trace(
        CallTrace(
            id="call-tl-1",
            source="jsonl",
            duration_ms=2500.0,
            transcript=[
                TranscriptSegment(role="caller", text="Hi", start_ms=0, end_ms=500),
                TranscriptSegment(role="agent", text="Hello", start_ms=500, end_ms=1500),
            ],
            spans=[
                TraceSpan(name="asr", start_ms=0, end_ms=500, duration_ms=500, turn_index=0),
                TraceSpan(name="llm", start_ms=500, end_ms=1200, duration_ms=700, turn_index=0),
                TraceSpan(name="tts", start_ms=1200, end_ms=1500, duration_ms=300, turn_index=0),
            ],
        )
    )

    response = client.get("/calls/call-tl-1/timeline")

    assert response.status_code == 200
    payload = response.json()
    assert payload["call_id"] == "call-tl-1"
    assert payload["duration_ms"] == 2500.0
    assert len(payload["spans"]) == 3
    assert {s["name"] for s in payload["spans"]} == {"asr", "llm", "tts"}
    assert len(payload["turns"]) == 2
    assert payload["turns"][0]["role"] == "caller"


def test_regression_post_endpoint(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))
    store = RunStore(store_path)
    store.save_call_trace(
        CallTrace(
            id="call-reg-1",
            source="jsonl",
            transcript=[
                TranscriptSegment(role="caller", text="Cancel my subscription"),
                TranscriptSegment(role="agent", text="I can help with cancellation."),
            ],
        )
    )

    response = client.post("/calls/call-reg-1/regression")

    assert response.status_code == 200
    payload = response.json()
    assert payload["call_id"] == "call-reg-1"
    assert payload["scenario_id"] == "regression-call-reg-1"
    assert "id: regression-call-reg-1" in payload["yaml"]


def test_failure_inbox_stats_endpoint(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))
    store = RunStore(store_path)

    # Empty store: stats should still respond cleanly.
    empty = client.get("/failure-inbox/stats")
    assert empty.status_code == 200
    assert empty.json()["total_evaluations"] == 0

    # Seed one call + evaluation so the aggregates have something to count.
    store.save_call_trace(
        CallTrace(
            id="call-stats-1",
            source="jsonl",
            transcript=[
                TranscriptSegment(role="caller", text="What time is it?"),
                TranscriptSegment(role="agent", text="It is 3 PM."),
            ],
        )
    )
    eval_response = client.get("/calls/call-stats-1/evaluate")
    assert eval_response.status_code == 200

    stats = client.get("/failure-inbox/stats").json()
    assert stats["total_evaluations"] == 1
    assert stats["sources"].get("jsonl") == 1
    assert stats["score"]["max"] >= 0


def test_call_evaluations_search_and_score_filters(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))
    store = RunStore(store_path)
    store.save_call_trace(
        CallTrace(
            id="filter-call-A",
            source="jsonl",
            transcript=[
                TranscriptSegment(role="caller", text="Question A"),
                TranscriptSegment(role="agent", text="Answer A"),
            ],
        )
    )

    assert client.get("/calls/filter-call-A/evaluate").status_code == 200

    # `q` substring search hits the call id.
    found = client.get("/call-evaluations", params={"q": "filter-call-a"}).json()
    assert len(found) == 1

    missing = client.get("/call-evaluations", params={"q": "nope-no-match"}).json()
    assert missing == []

    # `max_score=0` should exclude any non-failing evaluation.
    capped = client.get("/call-evaluations", params={"max_score": 0}).json()
    for entry in capped:
        assert entry["score"] <= 0
