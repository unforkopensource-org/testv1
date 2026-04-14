"""Minimal read-only FastAPI server for Decibench Store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

from decibench.config import load_config
from decibench.evaluators.compliance import ComplianceEvaluator
from decibench.evaluators.hallucination import HallucinationEvaluator
from decibench.evaluators.task import TaskCompletionEvaluator
from decibench.models import CallTrace, EvalResult, SuiteResult
from decibench.providers.registry import get_judge
from decibench.replay.evaluate import ImportedCallEvaluator
from decibench.replay.scenario import trace_to_scenario_yaml
from decibench.store import RunStore, default_store_path

app = FastAPI(
    title="Decibench API",
    description="Read-only API for inspecting stored runs and call traces.",
    version="1.0.0",
)


def get_static_html() -> str:
    path = Path(__file__).parent / "static" / "index.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "<h1>Dashboard Build Error: static/index.html not found.</h1>"


@app.get("/", summary="Dashboard Index", response_class=HTMLResponse)
@app.get("/dashboard", summary="Web Dashboard", response_class=HTMLResponse)
def serve_dashboard() -> str:
    return get_static_html()


def get_store() -> RunStore:
    """Dependency injection could be used here later if needed."""
    return RunStore(default_store_path())


def get_imported_call_evaluator() -> ImportedCallEvaluator:
    """Build the default imported-call evaluator stack."""
    config = load_config()
    judge = get_judge(config.providers.judge_model) if config.has_judge else None
    evaluators = [
        ComplianceEvaluator(),
        HallucinationEvaluator(),
        TaskCompletionEvaluator(),
    ]
    return ImportedCallEvaluator(evaluators, config, judge=judge)


@app.get("/health", summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}


@app.get("/runs", summary="List runs")
def list_runs(limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
    store = get_store()
    return store.list_runs(limit=limit)[skip:]


@app.get("/runs/{run_id}", summary="Get run by ID", response_model=SuiteResult)
def get_run(run_id: str) -> SuiteResult:
    store = get_store()
    result = store.get_suite_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found.")
    return result


@app.get("/calls", summary="List call traces")
def list_calls(
    limit: int = 50,
    skip: int = 0,
    source: str | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    store = get_store()
    return store.list_call_traces(limit=limit, source=source, since=since)[skip:]


@app.get("/calls/{call_id}", summary="Get call by ID", response_model=CallTrace)
def get_call(call_id: str) -> CallTrace:
    store = get_store()
    trace = store.get_call_trace(call_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Call trace not found.")
    return trace


@app.get(
    "/calls/{call_id}/scenario",
    summary="Convert call trace to regression scenario",
    response_class=PlainTextResponse,
)
def get_call_scenario(call_id: str) -> str:
    trace = get_call(call_id)
    return trace_to_scenario_yaml(trace)


@app.get(
    "/calls/{call_id}/evaluate",
    summary="Evaluate an imported call trace",
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
    summary="Get latest stored imported-call evaluation",
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


@app.get("/call-evaluations", summary="List stored imported-call evaluations")
def list_call_evaluations(
    limit: int = 50,
    source: str | None = None,
    failed_only: bool = False,
    category: str | None = None,
    call_id: str | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    store = get_store()
    return store.list_call_evaluations(
        limit=limit,
        source=source,
        failed_only=failed_only,
        category=category,
        call_id=call_id,
        since=since,
    )


@app.get(
    "/call-evaluations/{evaluation_id}",
    summary="Get stored imported-call evaluation by id",
    response_model=EvalResult,
)
def get_stored_call_evaluation(evaluation_id: str) -> EvalResult:
    store = get_store()
    result = store.get_call_evaluation(evaluation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Call evaluation not found.")
    return result
