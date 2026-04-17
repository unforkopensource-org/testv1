"""FastAPI server backing the Decibench dashboard / failure workbench.

This is intentionally a thin layer over `RunStore` and the imported-call
evaluation pipeline. Every endpoint either:

- returns a typed Pydantic model from `decibench.models`, or
- returns a small structured dict the dashboard explicitly needs.

The frontend should never have to crack open large JSON blobs to discover
structure — when a screen needs derived shape (timeline, inbox stats, etc.)
the backend exposes a first-class endpoint for it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from decibench.config import load_config
from decibench.evaluators.compliance import ComplianceEvaluator
from decibench.evaluators.hallucination import HallucinationEvaluator
from decibench.evaluators.task import TaskCompletionEvaluator
from decibench.models import CallTrace, EvalResult, SuiteResult, TraceSpan
from decibench.providers.registry import get_judge
from decibench.replay.evaluate import ImportedCallEvaluator
from decibench.replay.scenario import trace_to_scenario_yaml
from decibench.store import RunStore, default_store_path

app = FastAPI(
    title="Decibench API",
    description="Local-first API for the Decibench failure-analysis workbench.",
    version="1.0.0",
)


# --------------------------------------------------------------------- helpers


_STATIC_DIR = Path(__file__).parent / "static"
_ASSETS_DIR = _STATIC_DIR / "assets"
if _ASSETS_DIR.is_dir():
    # Vite emits hashed bundles into static/assets/*.{js,css}. Mount them so
    # the built `index.html` can resolve `/assets/...` references.
    app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")


def get_static_html() -> str:
    path = _STATIC_DIR / "index.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return (
        "<h1>Dashboard build missing.</h1>"
        "<p>Run <code>cd dashboard && npm install && npm run build</code> "
        "to produce <code>src/decibench/api/static/index.html</code>.</p>"
    )


def get_store() -> RunStore:
    """Per-request store instance — cheap (just opens a SQLite connection)."""
    return RunStore(default_store_path())


def get_imported_call_evaluator() -> ImportedCallEvaluator:
    """Build the default imported-call evaluator stack from on-disk config."""
    config = load_config()
    judge = (
        get_judge(
            config.providers.judge,
            model=config.providers.judge_model,
            api_key=config.providers.judge_api_key,
            temperature=config.evaluation.judge_temperature,
            judge_runs=config.evaluation.judge_runs,
        )
        if config.has_judge
        else None
    )
    evaluators = [
        ComplianceEvaluator(),
        HallucinationEvaluator(),
        TaskCompletionEvaluator(),
    ]
    return ImportedCallEvaluator(evaluators, config, judge=judge)


# ------------------------------------------------------------- response models


class CallTimelinePayload(BaseModel):
    """Lightweight timeline view for the call-detail screen.

    The full ``CallTrace`` payload can be heavy (raw audio metadata, tool
    payloads, vendor blobs). The timeline only carries what the timing chart
    and turn list need: spans, transcript turns, and minimal event tags.
    """

    call_id: str
    duration_ms: float
    spans: list[TraceSpan]
    turns: list[dict[str, Any]]
    event_kinds: dict[str, int]


class RegressionScenarioPayload(BaseModel):
    """Structured response for the regression-action button.

    The ``yaml`` field is what the user copies/exports; ``scenario_id`` matches
    what the YAML's ``id:`` field will be so the frontend can pre-fill any
    follow-up view without re-parsing.
    """

    call_id: str
    scenario_id: str
    yaml: str


class FailureInboxStats(BaseModel):
    """Aggregate counters that drive the workbench header."""

    total_evaluations: int
    failed: int
    passed: int
    sources: dict[str, int]
    categories: dict[str, int]
    score: dict[str, float]


# --------------------------------------------------------------- dashboard SPA


@app.get("/", summary="Dashboard index", response_class=HTMLResponse)
@app.get("/dashboard", summary="Web dashboard", response_class=HTMLResponse)
def serve_dashboard() -> str:
    return get_static_html()


@app.get("/health", summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}


# -------------------------------------------------------------------- runs API


@app.get("/runs", summary="List runs")
def list_runs(limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
    return get_store().list_runs(limit=limit, offset=skip)


@app.get("/runs/{run_id}", summary="Get run by ID", response_model=SuiteResult)
def get_run(run_id: str) -> SuiteResult:
    result = get_store().get_suite_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found.")
    return result


# ------------------------------------------------------------------- calls API


@app.get("/calls", summary="List call traces")
def list_calls(
    limit: int = 50,
    skip: int = 0,
    source: str | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    return get_store().list_call_traces(limit=limit, offset=skip, source=source, since=since)


@app.get("/calls/{call_id}", summary="Get call by ID", response_model=CallTrace)
def get_call(call_id: str) -> CallTrace:
    trace = get_store().get_call_trace(call_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Call trace not found.")
    return trace


@app.get(
    "/calls/{call_id}/timeline",
    summary="Get call timeline (spans + turns) for the dashboard timeline view",
    response_model=CallTimelinePayload,
)
def get_call_timeline(call_id: str) -> CallTimelinePayload:
    trace = get_call(call_id)
    event_kinds: dict[str, int] = {}
    for event in trace.events:
        key = event.type.value
        event_kinds[key] = event_kinds.get(key, 0) + 1
    turns = [
        {
            "role": segment.role,
            "text": segment.text,
            "start_ms": segment.start_ms,
            "end_ms": segment.end_ms,
            "confidence": segment.confidence,
        }
        for segment in trace.transcript
    ]
    return CallTimelinePayload(
        call_id=trace.id,
        duration_ms=trace.duration_ms,
        spans=trace.spans,
        turns=turns,
        event_kinds=event_kinds,
    )


@app.get(
    "/calls/{call_id}/scenario",
    summary="Render the regression scenario for this call as YAML text",
    response_class=PlainTextResponse,
)
def get_call_scenario(call_id: str) -> str:
    trace = get_call(call_id)
    return trace_to_scenario_yaml(trace)


@app.post(
    "/calls/{call_id}/regression",
    summary="Generate a regression scenario from a call (structured response)",
    response_model=RegressionScenarioPayload,
)
def generate_regression(call_id: str) -> RegressionScenarioPayload:
    """Workbench action: turn this failed call into a regression scenario.

    Returns the YAML text plus the scenario id so the dashboard can offer
    copy/download without a second round-trip.
    """
    trace = get_call(call_id)
    yaml_text = trace_to_scenario_yaml(trace)
    return RegressionScenarioPayload(
        call_id=trace.id,
        scenario_id=f"regression-{trace.id}",
        yaml=yaml_text,
    )


@app.post(
    "/calls/{call_id}/evaluate",
    summary="Evaluate an imported call trace (and persist the result)",
    response_model=EvalResult,
)
async def evaluate_call(call_id: str) -> EvalResult:
    trace = get_call(call_id)
    evaluator = get_imported_call_evaluator()
    result = await evaluator.evaluate_trace(trace)
    get_store().save_call_evaluation(trace, result)
    return result


@app.get(
    "/calls/{call_id}/evaluation",
    summary="Get the latest stored evaluation for a call",
    response_model=EvalResult,
)
def get_latest_call_evaluation(call_id: str) -> EvalResult:
    store = get_store()
    summaries = store.list_call_evaluations(limit=1, call_id=call_id)
    if not summaries:
        raise HTTPException(status_code=404, detail="Call evaluation not found.")
    result = store.get_call_evaluation(summaries[0]["id"])
    if result is None:
        raise HTTPException(status_code=404, detail="Call evaluation payload not found.")
    return result


# ---------------------------------------------------------- evaluations / inbox


@app.get("/call-evaluations", summary="List stored imported-call evaluations")
def list_call_evaluations(
    limit: int = Query(50, ge=1, le=500),
    source: str | None = None,
    failed_only: bool = False,
    category: str | None = None,
    call_id: str | None = None,
    since: str | None = None,
    max_score: float | None = Query(None, ge=0, le=100),
    q: str | None = Query(None, description="Substring match on call id, scenario, or source"),
) -> list[dict[str, Any]]:
    return get_store().list_call_evaluations(
        limit=limit,
        source=source,
        failed_only=failed_only,
        category=category,
        call_id=call_id,
        since=since,
        max_score=max_score,
        q=q,
    )


@app.get(
    "/call-evaluations/{evaluation_id}",
    summary="Get stored imported-call evaluation by id",
    response_model=EvalResult,
)
def get_stored_call_evaluation(evaluation_id: str) -> EvalResult:
    result = get_store().get_call_evaluation(evaluation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Call evaluation not found.")
    return result


@app.get(
    "/failure-inbox/stats",
    summary="Aggregate counters that drive the failure-workbench header",
    response_model=FailureInboxStats,
)
def failure_inbox_stats() -> FailureInboxStats:
    return FailureInboxStats(**get_store().failure_inbox_stats())
