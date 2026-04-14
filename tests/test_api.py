from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from decibench.api.app import app
from decibench.models import CallTrace, TranscriptSegment
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
