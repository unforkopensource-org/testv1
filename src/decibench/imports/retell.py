"""Retell production call importer."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from decibench.imports.base import BaseImporter
from decibench.imports.registry import register_importer
from decibench.models import AgentEvent, CallTrace, EventType, TranscriptSegment

logger = logging.getLogger(__name__)

@register_importer("retell")
class RetellImporter(BaseImporter):
    """Imports call traces from Retell AI."""

    @property
    def name(self) -> str:
        return "retell"

    async def fetch_calls(self, limit: int = 10, since: str | None = None, **kwargs: Any) -> list[CallTrace]:
        api_key = kwargs.get("api_key")
        if not api_key:
            raise ValueError("Retell API key is required (RETELL_API_KEY environment variable).")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        params: dict[str, str | int] = {"limit": limit}

        url = "https://api.retellai.com/v2/list-calls"

        async with httpx.AsyncClient() as client:
            try:
                # Security: ensure auth headers aren't dumped on error
                resp = await client.get(url, headers=headers, params=params, timeout=15.0)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as e:
                logger.error("Retell API returned error %s", e.response.status_code)
                raise
            except httpx.RequestError as e:
                logger.error("Retell network error: %s", str(e))
                raise

        # Retell can return a top-level array or {"data": [...]}.
        raw_calls = data if isinstance(data, list) else data.get("data", [])
        calls = [call for call in raw_calls if isinstance(call, dict)]

        if since:
            filtered_calls: list[dict[str, Any]] = []
            for call in calls:
                started_at = call.get("start_timestamp")
                if not isinstance(started_at, str) or started_at > since:
                    filtered_calls.append(call)
            calls = filtered_calls

        traces: list[CallTrace] = []
        for call in calls:
            trace = self._parse_call(call)
            if trace:
                traces.append(trace)

        return traces

    def _parse_call(self, call: dict[str, Any]) -> CallTrace | None:
        """Parse raw Retell call into a normalized CallTrace."""
        call_id = call.get("call_id")
        if not call_id:
            return None

        segments: list[TranscriptSegment] = []

        # Retell sends a raw text transcript block, and also 'transcript_object'
        transcript_obj = call.get("transcript_object", [])

        current_ms = 0.0

        if transcript_obj:
            for utterance in transcript_obj:
                role = utterance.get("role")
                text = utterance.get("content", "")
                words = utterance.get("words", [])

                # Use actual word timings if available!
                start = words[0].get("start", current_ms / 1000.0) if words else current_ms / 1000.0
                end = words[-1].get("end", start + len(text) * 0.05) if words else start + len(text) * 0.05

                start_ms = start * 1000
                end_ms = end * 1000
                current_ms = end_ms

                if role == "user":
                    segments.append(
                        TranscriptSegment(
                            role="caller",
                            text=text,
                            start_ms=start_ms,
                            end_ms=end_ms,
                        )
                    )
                else:
                    segments.append(
                        TranscriptSegment(
                            role="agent",
                            text=text,
                            start_ms=start_ms,
                            end_ms=end_ms,
                        )
                    )

        events = [
            AgentEvent(
                type=EventType.METADATA,
                timestamp_ms=0.0,
                data={"disconnection_reason": call.get("disconnection_reason")},
            ),
        ]

        events.append(AgentEvent(type=EventType.TURN_END, timestamp_ms=current_ms, data={}))

        duration_ms = call.get("duration", 0) * 1000

        # Create trace
        return CallTrace(
            id=call_id,
            source="retell",
            target=call.get("agent_id", "retell"),
            started_at=call.get("start_timestamp", ""),
            duration_ms=duration_ms,
            transcript=segments,
            events=events,
            metadata=call,
            imported_at=datetime.now(UTC).isoformat(),
        )
