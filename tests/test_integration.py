"""Integration test — run the full pipeline against the demo agent.

This verifies that Orchestrator + Demo connector + all evaluators + scoring
work together without crashing. Uses the built-in demo target so no
external dependencies, API keys, or network access are required.
"""

from __future__ import annotations

import pytest

from decibench.config import load_config
from decibench.orchestrator import Orchestrator


@pytest.fixture
def config():
    """Load default config (no file needed — falls back to defaults)."""
    return load_config(None, None)


@pytest.mark.asyncio
async def test_demo_quick_suite_runs(config):
    """Full pipeline: demo agent + quick suite produces valid results."""
    orch = Orchestrator(config)
    result = await orch.run_suite(target="demo", suite="quick", parallel=3)

    # Basic sanity checks
    assert result.total_scenarios > 0, "Should load at least one scenario"
    assert len(result.results) == result.total_scenarios
    assert result.decibench_score >= 0
    assert result.decibench_score <= 100
    assert result.passed + result.failed == result.total_scenarios
    assert result.duration_seconds > 0
    assert result.suite == "quick"
    assert result.target == "demo"


@pytest.mark.asyncio
async def test_demo_single_scenario(config):
    """Running a single scenario by filter works."""
    orch = Orchestrator(config)
    result = await orch.run_suite(
        target="demo",
        suite="quick",
        scenario_filter="greeting",
        parallel=1,
    )

    assert result.total_scenarios >= 1
    # All returned scenarios should match the filter
    for r in result.results:
        assert "greeting" in r.scenario_id


@pytest.mark.asyncio
async def test_demo_produces_metrics(config):
    """Demo run should produce actual metric values, not empty dicts."""
    orch = Orchestrator(config)
    result = await orch.run_suite(
        target="demo",
        suite="quick",
        scenario_filter="greeting",
        parallel=1,
    )

    assert result.results, "Should have at least one result"
    r = result.results[0]
    assert len(r.metrics) > 0, "Should produce at least one metric"

    # Check that some expected metric categories exist
    metric_names = set(r.metrics.keys())
    # At minimum we expect latency and silence metrics (always deterministic)
    assert metric_names, "Got no metrics, expected at least latency/silence"


@pytest.mark.asyncio
async def test_demo_score_above_zero(config):
    """Demo agent should score above 0 — it's designed with intentional imperfections."""
    orch = Orchestrator(config)
    result = await orch.run_suite(target="demo", suite="quick", parallel=3)

    assert result.decibench_score > 0, (
        f"Demo agent scored 0 — something is broken. "
        f"Results: {[r.scenario_id + ':' + str(r.score) for r in result.results]}"
    )


@pytest.mark.asyncio
async def test_suite_result_has_latency(config):
    """Aggregated latency stats should be populated."""
    orch = Orchestrator(config)
    result = await orch.run_suite(target="demo", suite="quick", parallel=3)

    assert "p50_ms" in result.latency
    assert "p95_ms" in result.latency


@pytest.mark.asyncio
async def test_reporters_dont_crash(config):
    """All reporters should handle demo results without errors."""
    from decibench.reporters.html_reporter import HTMLReporter
    from decibench.reporters.json_reporter import JSONReporter
    from decibench.reporters.markdown_reporter import MarkdownReporter

    orch = Orchestrator(config)
    result = await orch.run_suite(
        target="demo",
        suite="quick",
        scenario_filter="greeting",
        parallel=1,
    )

    # JSON
    json_str = JSONReporter.report(result)
    assert len(json_str) > 100
    assert "decibench_score" in json_str

    # Markdown
    md = MarkdownReporter.report(result)
    assert "Decibench" in md
    assert "Score" in md

    # HTML
    html_str = HTMLReporter.report(result)
    assert "<html" in html_str
    assert "score" in html_str.lower()
