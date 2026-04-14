"""Tests for Decibench Score calculator."""

from __future__ import annotations

from decibench.config import ScoringWeights
from decibench.evaluators.score import DecibenchScorer
from decibench.models import EvalResult, MetricResult


def _make_result(**metrics: tuple[float, str, bool]) -> EvalResult:
    """Helper to create EvalResult with specific metrics."""
    return EvalResult(
        scenario_id="test",
        passed=True,
        score=0.0,
        metrics={
            name: MetricResult(name=name, value=val, unit=unit, passed=passed)
            for name, (val, unit, passed) in metrics.items()
        },
    )


def test_scorer_empty_results():
    scorer = DecibenchScorer()
    score, breakdown = scorer.calculate([], ScoringWeights(), has_judge=False)
    assert score == 0.0
    assert breakdown == {}


def test_scorer_perfect_metrics():
    scorer = DecibenchScorer()
    result = _make_result(
        turn_latency_p50_ms=(200, "ms", True),
        turn_latency_p95_ms=(400, "ms", True),
        wer=(0.0, "%", True),
        mos_ovrl=(5.0, "/5.0", True),
        task_completion=(100.0, "%", True),
        compliance_score=(100.0, "%", True),
    )
    score, breakdown = scorer.calculate([result], ScoringWeights(), has_judge=True)
    assert score > 80  # Should be high with perfect metrics
    assert "latency" in breakdown
    assert "compliance" in breakdown


def test_scorer_bad_latency():
    scorer = DecibenchScorer()
    result = _make_result(
        turn_latency_p50_ms=(2000, "ms", False),
        turn_latency_p95_ms=(5000, "ms", False),
        wer=(0.0, "%", True),
        mos_ovrl=(4.5, "/5.0", True),
        task_completion=(100.0, "%", True),
        compliance_score=(100.0, "%", True),
    )
    score, breakdown = scorer.calculate([result], ScoringWeights(), has_judge=True)
    # Should be lower due to bad latency
    assert score < 80
    assert breakdown["latency"] < 50  # Bad latency should score low


def test_scorer_no_judge_mode():
    scorer = DecibenchScorer()
    result = _make_result(
        turn_latency_p50_ms=(500, "ms", True),
        wer=(5.0, "%", True),
        mos_ovrl=(4.2, "/5.0", True),
        compliance_score=(100.0, "%", True),
    )
    score, _breakdown = scorer.calculate([result], ScoringWeights(), has_judge=False)
    assert 0 <= score <= 100


def test_scorer_compliance_failure():
    scorer = DecibenchScorer()
    result = _make_result(
        turn_latency_p50_ms=(500, "ms", True),
        wer=(3.0, "%", True),
        mos_ovrl=(4.5, "/5.0", True),
        task_completion=(95.0, "%", True),
        compliance_score=(0.0, "%", False),
        pii_violations=(2.0, "count", False),
    )
    score, _breakdown = scorer.calculate([result], ScoringWeights(), has_judge=True)
    # Compliance failure should impact score
    assert score < 90


def test_scorer_excludes_untested_categories():
    """Untested categories should be excluded, not given free 50."""
    scorer = DecibenchScorer()
    result = _make_result(
        turn_latency_p50_ms=(500, "ms", True),
    )
    _score, breakdown = scorer.calculate([result], ScoringWeights(), has_judge=True)
    # Only latency should appear — untested categories are excluded
    assert "latency" in breakdown
    assert "task_completion" not in breakdown
    assert "compliance" not in breakdown
