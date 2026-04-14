"""Tests for the v1.0 storage/import/replay foundation."""

from __future__ import annotations

import json

from decibench.imports import import_jsonl
from decibench.models import CallTrace, CostBreakdown, SuiteResult, TranscriptSegment
from decibench.replay import trace_to_scenario_yaml
from decibench.store import RunStore


def test_run_store_round_trips_suite_result(tmp_path):
    store = RunStore(tmp_path / "decibench.sqlite")
    result = SuiteResult(
        suite="quick",
        target="demo",
        decibench_score=91.0,
        total_scenarios=1,
        passed=1,
        failed=0,
        cost=CostBreakdown(),
        timestamp="2026-04-14T00:00:00+00:00",
    )

    run_id = store.save_suite_result(result)
    loaded = store.get_suite_result(run_id)

    assert loaded is not None
    assert loaded.decibench_score == 91.0
    assert store.list_runs()[0]["id"] == run_id


def test_jsonl_import_and_trace_store(tmp_path):
    path = tmp_path / "calls.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "call-1",
                "source": "test",
                "target": "agent-a",
                "transcript": [
                    {"role": "caller", "text": "I need to reschedule"},
                    {"role": "agent", "text": "I can help reschedule your appointment"},
                ],
            }
        )
        + "\n"
    )

    traces = import_jsonl(path)
    store = RunStore(tmp_path / "decibench.sqlite")
    store.save_call_trace(traces[0])
    loaded = store.get_call_trace("call-1")

    assert loaded is not None
    assert loaded.source == "test"
    assert "reschedule" in loaded.text


def test_trace_to_scenario_yaml_contains_regression_context():
    trace = CallTrace(
        id="call-2",
        source="jsonl",
        transcript=[
            TranscriptSegment(role="caller", text="Where is my order?"),
            TranscriptSegment(role="agent", text="I can check your order status."),
        ],
    )

    scenario_yaml = trace_to_scenario_yaml(trace)

    assert "regression-call-2" in scenario_yaml
    assert "source_call_id: call-2" in scenario_yaml
    assert "order" in scenario_yaml
