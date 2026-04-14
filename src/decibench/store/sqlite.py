"""SQLite-backed store for runs and normalized production call traces."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from decibench.models import CallTrace, SuiteResult
from decibench.store.migrations import run_migrations
from decibench.store.privacy import RedactionPolicy

SCHEMA_VERSION = 2


def default_store_path(base_dir: Path | None = None) -> Path:
    """Return the default local Decibench database path."""
    env_path = os.environ.get("DECIBENCH_STORE_PATH")
    if env_path:
        return Path(env_path).expanduser()

    root = base_dir or Path.cwd()
    if os.access(root, os.W_OK):
        return root / ".decibench" / "decibench.sqlite"

    return Path(tempfile.gettempdir()) / "decibench" / "decibench.sqlite"


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
                ("schema_version", "1"),  # Migrations will update this to 2
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

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return run summaries newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, suite, target, score, passed, failed, total_scenarios, timestamp
                FROM runs
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
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

    def list_call_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return production call trace summaries newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, source, target, started_at, duration_ms, imported_at
                FROM call_traces
                ORDER BY imported_at DESC
                LIMIT ?
                """,
                (limit,),
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

    @staticmethod
    def _run_id(result: SuiteResult) -> str:
        safe_target = "".join(ch if ch.isalnum() else "-" for ch in result.target).strip("-")
        safe_suite = "".join(ch if ch.isalnum() else "-" for ch in result.suite).strip("-")
        timestamp = result.timestamp.replace(":", "").replace(".", "").replace("+", "Z")
        return f"{timestamp}-{safe_suite}-{safe_target}"[:160]
