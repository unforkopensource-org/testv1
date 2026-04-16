"""Shared helpers for JSON-output LLM judges."""

from __future__ import annotations

import json
import re
from typing import Any

from decibench.providers.registry import JudgeResult

JUDGE_SYSTEM_PROMPT = """You are an expert voice agent evaluator. You assess voice agent responses \
for quality, accuracy, and compliance using structured chain-of-thought reasoning.

## Your Process
1. IDENTIFY: List the specific claims, actions, or behaviors to evaluate
2. EVIDENCE: For each item, cite the exact evidence from the provided context
3. JUDGE: Score each item, then compute an overall score
4. CONCLUDE: Summarize your verdict

## Scoring Rubric
- 90-100: Excellent — all criteria met, no issues
- 70-89: Good — minor issues, core task achieved
- 50-69: Partial — some criteria met, notable gaps
- 25-49: Poor — major failures, task mostly not achieved
- 0-24: Failed — criteria not met at all

## Output Format
You MUST respond with valid JSON:
{
    "passed": true/false,
    "score": 0.0-100.0,
    "reasoning": "Step-by-step reasoning with evidence citations"
}

Rules:
- Base evaluation ONLY on evidence provided — never assume facts not in context
- Conversational filler (greetings, "how can I help") is neutral, not positive or negative
- Be strict on factual accuracy, lenient on phrasing/style"""


def build_prompt(prompt: str, context: dict[str, Any]) -> str:
    """Build the final judge prompt with structured context sections."""
    parts = [prompt]

    if "transcript" in context:
        parts.append(f"\n## Conversation Transcript\n{context['transcript']}")

    if "expected" in context:
        parts.append(f"\n## Expected Behavior\n{context['expected']}")

    if "tool_calls" in context:
        parts.append(f"\n## Tool Calls Made\n{json.dumps(context['tool_calls'], indent=2)}")

    if "knowledge_base" in context:
        parts.append(f"\n## Knowledge Base\n{context['knowledge_base']}")

    return "\n".join(parts)


def parse_judge_response(raw: str) -> JudgeResult:
    """Parse JSON or JSON-in-markdown judge output into a JudgeResult."""
    text = raw.strip()
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1)

    for candidate in (text, _extract_json_object(text)):
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        try:
            return JudgeResult(
                passed=bool(payload.get("passed", False)),
                score=float(payload.get("score", 0.0)),
                reasoning=str(payload.get("reasoning", "")),
                raw_output=raw,
            )
        except (TypeError, ValueError):
            continue

    return JudgeResult(
        passed=False,
        score=0.0,
        reasoning=f"Failed to parse judge output: {raw[:200]}",
        raw_output=raw,
    )


def _extract_json_object(text: str) -> str | None:
    brace_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group()
    return None
