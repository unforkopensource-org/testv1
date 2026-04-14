"""Vapi production call importer."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from decibench.imports.base import BaseImporter
from decibench.imports.registry import register_importer
from decibench.models import AgentEvent, CallTrace, EventType, TranscriptSegment

logger = logging.getLogger(__name__)

@register_importer("vapi")
class VapiImporter(BaseImporter):
    """Imports call traces from Vapi API."""

    @property
    def name(self) -> str:
        return "vapi"

    async def fetch_calls(self, limit: int = 10, since: str | None = None, **kwargs: Any) -> list[CallTrace]:
        api_key = kwargs.get("api_key")
        if not api_key:
            raise ValueError("Vapi API key is required (VAPI_API_KEY environment variable).")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Simple limit implementation.
        # For production you might want pagination handling.
        params: dict[str, str | int] = {"limit": limit}
        if since:
            params["createdAtGt"] = since

        url = "https://api.vapi.ai/call"

        async with httpx.AsyncClient() as client:
            try:
                # Security: ensure auth headers aren't dumped on error
                resp = await client.get(url, headers=headers, params=params, timeout=15.0)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as e:
                logger.error("Vapi API returned error %s", e.response.status_code)
                raise
            except httpx.RequestError as e:
                logger.error("Vapi network error: %s", str(e))
                raise

        raw_calls = data if isinstance(data, list) else data.get("data", [])
        traces: list[CallTrace] = []
        for call in raw_calls:
            if not isinstance(call, dict):
                continue
            trace = self._parse_call(call)
            if trace:
                traces.append(trace)

        return traces

    def _parse_call(self, call: dict[str, Any]) -> CallTrace | None:
        """Parse raw Vapi call into a normalized CallTrace."""
        call_id = call.get("id")
        if not call_id:
            return None

        # Build transcript segments
        segments: list[TranscriptSegment] = []
        messages = call.get("messages", [])

        current_ms = 0.0

        for msg in messages:
            role = msg.get("role")
            text = msg.get("message") or msg.get("content", "")

            # Simple heuristic timing for imported text if pure Vapi payload lacks it
            duration = len(text) * 50.0  # ~50ms per char as a fallback

            if role in ("user", "caller"):
                segments.append(
                    TranscriptSegment(
                        role="caller",
                        text=text,
                        start_ms=current_ms,
                        end_ms=current_ms + duration,
                    )
                )
                current_ms += duration + 500  # small gap
            elif role in ("assistant", "agent"):
                segments.append(
                    TranscriptSegment(
                        role="agent",
                        text=text,
                        start_ms=current_ms,
                        end_ms=current_ms + duration,
                    )
                )
                current_ms += duration + 500

        # Basic events
        events = [
            AgentEvent(
                type=EventType.METADATA,
                timestamp_ms=0.0,
                data={"status": call.get("status"), "endedReason": call.get("endedReason")},
            ),
        ]

        # Mark turn ends implicitly
        events.append(AgentEvent(type=EventType.TURN_END, timestamp_ms=current_ms, data={}))

        duration_ms = call.get("duration", 0) * 1000

        return CallTrace(
            id=call_id,
            source="vapi",
            target=call.get("phoneCallProvider", "vapi-web"),
            started_at=call.get("createdAt", ""),
            duration_ms=duration_ms,
            transcript=segments,
            events=events,
            metadata=call,
            imported_at=datetime.now(UTC).isoformat(),
        )
