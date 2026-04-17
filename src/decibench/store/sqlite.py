"""SQLite-backed store for runs and normalized production call traces."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from decibench.models import CallTrace, EvalResult, SuiteResult
from decibench.store.migrations import run_migrations
from decibench.store.privacy import RedactionPolicy

SCHEMA_VERSION = 3


def default_store_path(base_dir: Path | None = None) -> Path:
    """Return the default local Decibench database path.

    Resolution order:

    1. ``DECIBENCH_STORE_PATH`` environment variable (absolute override).
    2. Explicit ``base_dir`` argument.
    3. Walk up from ``cwd()`` looking for ``decibench.toml`` and anchor the
       store next to it.  This makes store location stable regardless of
       which subdirectory the user happens to be in.
    4. Fall back to ``cwd()`` if no project root is found.
    5. Use the system temp dir if the resolved root is not writable.
    """
    env_path = os.environ.get("DECIBENCH_STORE_PATH")
    if env_path:
        return Path(env_path).expanduser()

    root = base_dir if base_dir is not None else _find_project_root() or Path.cwd()

    if os.access(root, os.W_OK):
        return root / ".decibench" / "decibench.sqlite"

    return Path(tempfile.gettempdir()) / "decibench" / "decibench.sqlite"


def _find_project_root() -> Path | None:
    """Walk up from cwd looking for decibench.toml."""
    current = Path.cwd()
    for directory in [current, *current.parents]:
        if (directory / "decibench.toml").is_file():
            return directory
    return None


class RunStore:
    """Small, local-first SQLite store.

    This is deliberately boring infrastructure. The dashboard, CI summaries,
    and production replay features need one reliable source of truth before any
    UI or native platform integration can be credible.
    """

    def __init__(
        self,
        path: Path | str | None = None,
        redaction_policy: RedactionPolicy | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else default_store_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.redactor = redaction_policy or RedactionPolicy()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            # Another process may be initializing the database. The default
            # journal mode is still correct; WAL is only an optimization.
            with suppress(sqlite3.OperationalError):
                conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    suite TEXT NOT NULL,
                    target TEXT NOT NULL,
                    score REAL NOT NULL,
                    passed INTEGER NOT NULL,
                    failed INTEGER NOT NULL,
                    total_scenarios INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS call_traces (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    imported_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            # Meta table initialization
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                ("schema_version", "1"),  # Migrations will update this to the latest schema.
            )

            # Execute schema migrations
            run_migrations(conn)

    def save_suite_result(self, result: SuiteResult) -> str:
        """Persist a suite result and return its run id."""
        run_id = self._run_id(result)
        payload = result.model_dump(mode="json")
        with self._connect() as conn:
            # Insert into v1 runs table
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    id, suite, target, score, passed, failed, total_scenarios,
                    timestamp, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    result.suite,
                    result.target,
                    result.decibench_score,
                    result.passed,
                    result.failed,
                    result.total_scenarios,
                    result.timestamp,
                    json.dumps(self.redactor.redact_dict(payload), sort_keys=True),
                ),
            )

            # Shred into v2 normalized tables
            for er in result.results:
                scenario_run_id = f"{run_id}-{er.scenario_id}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runs_scenarios (
                        id, run_id, scenario_id, passed, score, duration_ms, failures, failure_summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        scenario_run_id,
                        run_id,
                        er.scenario_id,
                        1 if er.passed else 0,
                        er.score,
                        er.duration_ms,
                        json.dumps(er.failures),
                        json.dumps(er.failure_summary),
                    )
                )
                for _metric_name, m_res in er.metrics.items():
                    conn.execute(
                        """
                        INSERT INTO runs_metrics (
                            scenario_run_id, name, value, unit, passed
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            scenario_run_id,
                            m_res.name,
                            m_res.value,
                            m_res.unit,
                            1 if m_res.passed else 0,
                        ),
                    )
                for span in er.spans:
                    conn.execute(
                        """
                        INSERT INTO runs_spans (
                            scenario_run_id, name, start_ms, end_ms, duration_ms, turn_index
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            scenario_run_id,
                            span.name,
                            span.start_ms,
                            span.end_ms,
                            span.duration_ms,
                            span.turn_index,
                        ),
                    )
        return run_id

    def list_runs(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """Return run summaries newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, suite, target, score, passed, failed, total_scenarios, timestamp
                FROM runs
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_suite_result(self, run_id: str) -> SuiteResult | None:
        """Load a stored suite result."""
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return SuiteResult.model_validate(json.loads(row["payload"]))

    def save_call_trace(self, trace: CallTrace) -> str:
        """Persist a normalized production call trace."""
        payload = trace.model_dump(mode="json")
        redacted_payload = self.redactor.redact_dict(payload)

        with self._connect() as conn:
            # v1 base table
            conn.execute(
                """
                INSERT OR REPLACE INTO call_traces (
                    id, source, target, started_at, duration_ms, imported_at, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.id,
                    trace.source,
                    trace.target,
                    trace.started_at,
                    trace.duration_ms,
                    trace.imported_at,
                    json.dumps(redacted_payload, sort_keys=True),
                ),
            )

            # v2 normalized shredding
            for event in trace.events:
                conn.execute(
                    """
                    INSERT INTO traces_events (
                        call_id, type, timestamp_ms, data
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        trace.id,
                        event.type.value,
                        event.timestamp_ms,
                        json.dumps(self.redactor.redact_dict(event.data)),
                    ),
                )
            for segment in trace.transcript:
                conn.execute(
                    """
                    INSERT INTO traces_segments (
                        call_id, role, text, start_ms, end_ms, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace.id,
                        segment.role,
                        self.redactor.redact_text(segment.text),
                        segment.start_ms,
                        segment.end_ms,
                        segment.confidence,
                    ),
                )
            for span in trace.spans:
                conn.execute(
                    """
                    INSERT INTO traces_spans (
                        call_id, name, start_ms, end_ms, duration_ms, turn_index
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace.id,
                        span.name,
                        span.start_ms,
                        span.end_ms,
                        span.duration_ms,
                        span.turn_index,
                    ),
                )

        return trace.id

    def list_call_traces(
        self,
        limit: int = 20,
        offset: int = 0,
        source: str | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return production call trace summaries newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, source, target, started_at, duration_ms, imported_at
                FROM call_traces
                WHERE (? IS NULL OR source = ?)
                  AND (? IS NULL OR imported_at >= ?)
                ORDER BY imported_at DESC
                LIMIT ? OFFSET ?
                """,
                (source, source, since, since, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_call_trace(self, call_id: str) -> CallTrace | None:
        """Load a stored call trace."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM call_traces WHERE id = ?",
                (call_id,),
            ).fetchone()
        if row is None:
            return None
        return CallTrace.model_validate(json.loads(row["payload"]))

    def save_call_evaluation(self, trace: CallTrace, result: EvalResult) -> str:
        """Persist an imported-call evaluation and return its evaluation id."""
        evaluated_at = datetime.now(UTC).isoformat()
        evaluation_id = self._call_evaluation_id(trace.id, evaluated_at)
        payload = self.redactor.redact_dict(result.model_dump(mode="json"))

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO call_evaluations (
                    id, call_id, source, scenario_id, score, passed, evaluated_at, failure_summary, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation_id,
                    trace.id,
                    trace.source,
                    result.scenario_id,
                    result.score,
                    1 if result.passed else 0,
                    evaluated_at,
                    json.dumps(result.failure_summary),
                    json.dumps(payload, sort_keys=True),
                ),
            )
            for metric in result.metrics.values():
                conn.execute(
                    """
                    INSERT INTO call_evaluation_metrics (
                        evaluation_id, name, value, unit, passed
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        evaluation_id,
                        metric.name,
                        metric.value,
                        metric.unit,
                        1 if metric.passed else 0,
                    ),
                )
        return evaluation_id

    def list_call_evaluations(
        self,
        limit: int = 20,
        source: str | None = None,
        failed_only: bool = False,
        category: str | None = None,
        call_id: str | None = None,
        since: str | None = None,
        max_score: float | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return imported-call evaluation summaries newest first.

        Filters used by the failure workbench:

        - ``failed_only``     — only ``passed=0`` rows
        - ``source``          — exact source match (jsonl/vapi/retell/...)
        - ``category``        — failed-category substring match (compliance/latency/...)
        - ``max_score``       — only evaluations with ``score <= max_score``
        - ``q``               — case-insensitive substring across call id / scenario / source
        - ``call_id``, ``since``, ``limit`` — usual narrowing
        """
        category_like = f'%"{category}"%' if category else None
        q_like = f"%{q.lower()}%" if q else None
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, call_id, source, scenario_id, score, passed, evaluated_at, failure_summary
                FROM call_evaluations
                WHERE (? IS NULL OR source = ?)
                  AND (? = 0 OR passed = 0)
                  AND (? IS NULL OR failure_summary LIKE ?)
                  AND (? IS NULL OR call_id = ?)
                  AND (? IS NULL OR evaluated_at >= ?)
                  AND (? IS NULL OR score <= ?)
                  AND (
                    ? IS NULL
                    OR LOWER(call_id) LIKE ?
                    OR LOWER(scenario_id) LIKE ?
                    OR LOWER(source) LIKE ?
                  )
                ORDER BY evaluated_at DESC
                LIMIT ?
                """,
                (
                    source,
                    source,
                    1 if failed_only else 0,
                    category_like,
                    category_like,
                    call_id,
                    call_id,
                    since,
                    since,
                    max_score,
                    max_score,
                    q_like,
                    q_like,
                    q_like,
                    q_like,
                    limit,
                ),
            ).fetchall()

        summaries: list[dict[str, Any]] = []
        for row in rows:
            summary = dict(row)
            summary["passed"] = bool(summary["passed"])
            summary["failure_summary"] = json.loads(summary["failure_summary"])
            summaries.append(summary)
        return summaries

    def failure_inbox_stats(self) -> dict[str, Any]:
        """Aggregate counts the failure workbench shows in its header.

        Returns a dict shaped like::

            {
              "total_evaluations": 42,
              "failed": 17,
              "passed": 25,
              "sources": {"jsonl": 30, "vapi": 12},
              "categories": {"compliance": 9, "latency": 6, "hallucination": 2},
              "score": {"avg": 71.4, "min": 12.0, "max": 100.0}
            }

        Aggregating in SQL keeps the dashboard fast — the frontend never has to
        page through every evaluation just to count them.
        """
        with self._connect() as conn:
            totals_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN passed = 0 THEN 1 ELSE 0 END) AS failed,
                    SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) AS passed,
                    AVG(score) AS avg_score,
                    MIN(score) AS min_score,
                    MAX(score) AS max_score
                FROM call_evaluations
                """
            ).fetchone()

            source_rows = conn.execute(
                """
                SELECT source, COUNT(*) AS n
                FROM call_evaluations
                GROUP BY source
                ORDER BY n DESC
                """
            ).fetchall()

            category_rows = conn.execute(
                """
                SELECT failure_summary
                FROM call_evaluations
                WHERE passed = 0 AND failure_summary != '[]'
                """
            ).fetchall()

        category_counts: dict[str, int] = {}
        for row in category_rows:
            try:
                cats = json.loads(row["failure_summary"])
            except (TypeError, ValueError):
                continue
            for cat in cats:
                if not isinstance(cat, str):
                    continue
                category_counts[cat] = category_counts.get(cat, 0) + 1

        total = int(totals_row["total"] or 0)
        return {
            "total_evaluations": total,
            "failed": int(totals_row["failed"] or 0),
            "passed": int(totals_row["passed"] or 0),
            "sources": {row["source"]: int(row["n"]) for row in source_rows},
            "categories": dict(
                sorted(category_counts.items(), key=lambda kv: kv[1], reverse=True)
            ),
            "score": {
                "avg": float(totals_row["avg_score"]) if total else 0.0,
                "min": float(totals_row["min_score"]) if total else 0.0,
                "max": float(totals_row["max_score"]) if total else 0.0,
            },
        }

    def get_call_evaluation(self, evaluation_id: str) -> EvalResult | None:
        """Load a stored imported-call evaluation by id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM call_evaluations WHERE id = ?",
                (evaluation_id,),
            ).fetchone()
        if row is None:
            return None
        return EvalResult.model_validate(json.loads(row["payload"]))

    @staticmethod
    def _run_id(result: SuiteResult) -> str:
        safe_target = "".join(ch if ch.isalnum() else "-" for ch in result.target).strip("-")
        safe_suite = "".join(ch if ch.isalnum() else "-" for ch in result.suite).strip("-")
        timestamp = result.timestamp.replace(":", "").replace(".", "").replace("+", "Z")
        return f"{timestamp}-{safe_suite}-{safe_target}"[:160]

    @staticmethod
    def _call_evaluation_id(call_id: str, evaluated_at: str) -> str:
        safe_call_id = "".join(ch if ch.isalnum() else "-" for ch in call_id).strip("-")
        timestamp = evaluated_at.replace(":", "").replace(".", "").replace("+", "Z")
        return f"{timestamp}-{safe_call_id}"[:160]
