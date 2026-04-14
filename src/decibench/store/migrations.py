"""SQLite migrations runner and v2 schema."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

logger = logging.getLogger(__name__)


def run_migrations(conn: sqlite3.Connection) -> None:
    """Run all pending schema migrations."""

    # 1. Ensure migrations table exists (introduced with v2 migrations framework)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # 2. Get current version from old `meta` table if schema_migrations is empty
    # Handle the transition from v1 (which just had meta.schema_version = 1)
    row = conn.execute("SELECT MAX(version) as version FROM schema_migrations").fetchone()
    current_version = row["version"] if row and row["version"] is not None else 0

    if current_version == 0:
        # Check if v1 tables exist (runs, call_traces, meta)
        meta_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
        ).fetchone()

        if meta_exists:
            # We are currently at v1
            current_version = 1
            conn.execute("INSERT INTO schema_migrations (version) VALUES (1)")
            conn.commit()

    # 3. Apply migrations sequentially
    if current_version < 2:
        logger.info("Migrating Decibench Store to Schema v2 (Normalized Tables)")
        _migrate_v1_to_v2(conn)
        conn.execute("INSERT INTO schema_migrations (version) VALUES (2)")
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            ("schema_version", "2"),
        )
        conn.commit()


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate from v1 (JSON mostly) to v2 (normalized dashboards tables)."""
    # SQLite does not support adding foreign keys to existing tables easily,
    # but we are just ADDING new child tables. The `payload` JSON is kept for fidelity.

    # Allow foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    # 1. runs_scenarios: Breakdown of scenarios within a suite run
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs_scenarios (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            scenario_id TEXT NOT NULL,
            passed INTEGER NOT NULL,
            score REAL NOT NULL,
            duration_ms REAL NOT NULL,
            failures TEXT NOT NULL,          -- JSON list of failure messages
            failure_summary TEXT NOT NULL,   -- JSON list of failed categories
            FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
        )
        """
    )

    # 2. runs_metrics: Individual metric checks per scenario
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_run_id TEXT NOT NULL,
            name TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            passed INTEGER NOT NULL,
            FOREIGN KEY(scenario_run_id) REFERENCES runs_scenarios(id) ON DELETE CASCADE
        )
        """
    )

    # 3. traces_events: Individual events in a call trace
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS traces_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id TEXT NOT NULL,
            type TEXT NOT NULL,
            timestamp_ms REAL NOT NULL,
            data TEXT NOT NULL, -- JSON string
            FOREIGN KEY(call_id) REFERENCES call_traces(id) ON DELETE CASCADE
        )
        """
    )

    # 4. traces_segments: Transcript items in a call trace
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS traces_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id TEXT NOT NULL,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            start_ms REAL NOT NULL,
            end_ms REAL NOT NULL,
            confidence REAL NOT NULL,
            FOREIGN KEY(call_id) REFERENCES call_traces(id) ON DELETE CASCADE
        )
        """
    )

    # 5. traces_spans: Telemetry spans for observability in a call trace
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS traces_spans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id TEXT NOT NULL,
            name TEXT NOT NULL,
            start_ms REAL NOT NULL,
            end_ms REAL NOT NULL,
            duration_ms REAL NOT NULL,
            turn_index INTEGER,
            FOREIGN KEY(call_id) REFERENCES call_traces(id) ON DELETE CASCADE
        )
        """
    )

    # 6. runs_spans: Telemetry spans for observability in a scenario run
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs_spans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_run_id TEXT NOT NULL,
            name TEXT NOT NULL,
            start_ms REAL NOT NULL,
            end_ms REAL NOT NULL,
            duration_ms REAL NOT NULL,
            turn_index INTEGER,
            FOREIGN KEY(scenario_run_id) REFERENCES runs_scenarios(id) ON DELETE CASCADE
        )
        """
    )

    # Also add indices for common dashboard queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_scenarios_run_id ON runs_scenarios(run_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_metrics_scenario_run_id "
        "ON runs_metrics(scenario_run_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_events_call_id ON traces_events(call_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_segments_call_id ON traces_segments(call_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_spans_call_id ON traces_spans(call_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_spans_scenario_run_id "
        "ON runs_spans(scenario_run_id)"
    )

    # We do NOT backfill the new tables with existing data in `runs` and `call_traces` payloads
    # immediately because this could be a heavy operation for large stores.
    # Future versions can introduce a background job or CLI command to backfill if needed.
