"""Convert imported call traces into regression scenarios."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import yaml

if TYPE_CHECKING:
    from collections.abc import Sequence

    from decibench.models import CallTrace, TranscriptSegment


def trace_to_scenario_yaml(trace: CallTrace) -> str:
    """Create a conservative regression scenario YAML from a call trace."""
    caller_turns = [segment for segment in trace.transcript if segment.role == "caller"]
    agent_turns = [segment for segment in trace.transcript if segment.role == "agent"]
    conversation: list[dict[str, object]] = []

    for segment in trace.transcript:
        item: dict[str, object] = {"role": segment.role, "text": segment.text}
        if segment.role == "agent":
            item = {
                "role": "agent",
                "expect": {
                    "must_include": _keywords(segment.text),
                },
            }
        conversation.append(item)

    if not conversation and agent_turns:
        conversation.append(
            {
                "role": "agent",
                "expect": {"must_include": _keywords(agent_turns[-1].text)},
            }
        )

    scenario = {
        "id": f"regression-{trace.id}",
        "version": 1,
        "mode": "scripted",
        "description": f"Regression scenario generated from {trace.source} call {trace.id}",
        "tags": ["regression", f"source:{trace.source}"],
        "metadata": {
            "source_call_id": trace.id,
            "source": trace.source,
            "generated_by": "decibench replay",
        },
        "goal": _goal_from_trace(trace, caller_turns),
        "conversation": conversation,
        "success_criteria": [
            {
                "type": "task_completion",
                "description": "Agent should preserve the successful behavior from the source call",
                "check": "hybrid",
            },
            {
                "type": "latency",
                "description": "Agent should stay within the default latency budget",
                "p95_max_ms": 1500,
            },
        ],
    }
    return cast("str", yaml.safe_dump(scenario, sort_keys=False))


def _goal_from_trace(trace: CallTrace, caller_turns: Sequence[TranscriptSegment]) -> str:
    if caller_turns:
        first = caller_turns[0].text
        if first:
            return f"Handle caller request: {first}"
    return f"Replay and validate behavior from production call {trace.id}"


def _keywords(text: str, limit: int = 4) -> list[str]:
    words = [
        word.strip(".,!?;:()[]{}\"'").lower()
        for word in text.split()
        if len(word.strip(".,!?;:()[]{}\"'")) >= 4
    ]
    stop = {"that", "this", "with", "your", "have", "will", "from", "there"}
    keywords: list[str] = []
    for word in words:
        if word in stop or word in keywords:
            continue
        keywords.append(word)
        if len(keywords) >= limit:
            break
    return keywords or words[:1] or ["response"]
