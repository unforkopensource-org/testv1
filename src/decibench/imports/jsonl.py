"""Generic JSONL importer for production call traces.

The generic importer matters because v1.0 cannot wait for every platform
connector before users can bring real calls into Decibench. Native importers
can map richer metadata later; JSONL gives every team an escape hatch today.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from decibench.models import AgentEvent, CallTrace, EventType, TranscriptSegment

if TYPE_CHECKING:
    from pathlib import Path


def import_jsonl(path: Path) -> list[CallTrace]:
    """Import normalized traces from a JSONL file.

    Expected flexible fields per line:
    - id / call_id
    - source
    - target / agent
    - started_at / timestamp
    - duration_ms
    - transcript: either a string or a list of {role, text, start_ms, end_ms}
    - events: optional list of Decibench-style event dicts
    - metadata: optional arbitrary platform payload
    """
    traces: list[CallTrace] = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            msg = f"Invalid JSONL at {path}:{line_no}: {exc}"
            raise ValueError(msg) from exc
        if not isinstance(raw, dict):
            msg = f"Invalid JSONL at {path}:{line_no}: expected object"
            raise ValueError(msg)
        traces.append(_trace_from_raw(raw, fallback_id=f"{path.stem}-{line_no}"))
    return traces


def _trace_from_raw(raw: dict[str, Any], fallback_id: str) -> CallTrace:
    imported_at = datetime.now(UTC).isoformat()
    return CallTrace(
        id=str(raw.get("id") or raw.get("call_id") or fallback_id),
        source=str(raw.get("source") or "jsonl"),
        target=str(raw.get("target") or raw.get("agent") or ""),
        started_at=str(raw.get("started_at") or raw.get("timestamp") or ""),
        duration_ms=float(raw.get("duration_ms") or raw.get("duration") or 0.0),
        transcript=_parse_transcript(raw.get("transcript")),
        events=_parse_events(raw.get("events")),
        metadata=dict(raw.get("metadata") or raw),
        imported_at=imported_at,
    )


def _parse_transcript(value: Any) -> list[TranscriptSegment]:
    if value is None:
        return []
    if isinstance(value, str):
        return [TranscriptSegment(role="agent", text=value)]
    if not isinstance(value, list):
        return [TranscriptSegment(role="agent", text=str(value))]

    segments: list[TranscriptSegment] = []
    for item in value:
        if isinstance(item, str):
            segments.append(TranscriptSegment(role="agent", text=item))
            continue
        if not isinstance(item, dict):
            continue
        role: Literal["caller", "agent"] = (
            item["role"] if item.get("role") in ("caller", "agent") else "agent"
        )
        text = str(item.get("text") or item.get("message") or "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                role=role,
                text=text,
                start_ms=float(item.get("start_ms") or item.get("start") or 0.0),
                end_ms=float(item.get("end_ms") or item.get("end") or 0.0),
                confidence=float(item.get("confidence") or 1.0),
            )
        )
    return segments


def _parse_events(value: Any) -> list[AgentEvent]:
    if not isinstance(value, list):
        return []

    events: list[AgentEvent] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        raw_type = str(item.get("type") or EventType.METADATA.value)
        event_type = (
            EventType(raw_type)
            if raw_type in EventType._value2member_map_
            else EventType.METADATA
        )
        events.append(
            AgentEvent(
                type=event_type,
                timestamp_ms=float(item.get("timestamp_ms") or item.get("time_ms") or 0.0),
                data=dict(item.get("data") or item),
            )
        )
    return events
