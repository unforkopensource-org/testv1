"""Hallucination evaluator — detect claims not grounded in context.

Checks agent responses against knowledge base, tool results, and
conversation context.

- With LLM judge: structured chain-of-thought grounding check
- Without judge: entity extraction + cross-reference (numbers, names, dates)
"""

from __future__ import annotations

import re
from typing import Any

from decibench.evaluators.base import BaseEvaluator
from decibench.models import CallSummary, EventType, MetricResult, Scenario, TranscriptResult


class HallucinationEvaluator(BaseEvaluator):
    """Detect hallucinated claims in agent responses."""

    @property
    def name(self) -> str:
        return "hallucination"

    @property
    def layer(self) -> str:
        return "semantic"

    @property
    def requires_judge(self) -> bool:
        return True

    async def evaluate(
        self,
        scenario: Scenario,
        summary: CallSummary,
        transcript: TranscriptResult,
        context: dict[str, Any],
    ) -> list[MetricResult]:
        judge = context.get("judge")

        # Guard: skip if no transcript
        if not transcript.text or not transcript.text.strip():
            return [MetricResult(
                name="hallucination_rate",
                value=0.0,
                unit="%",
                passed=True,
                details={"skipped": True, "reason": "no_transcript"},
            )]

        # Collect grounding context
        grounding = self._collect_grounding(scenario, summary)

        if judge is not None:
            score = await self._judge_hallucination(transcript, grounding, judge)
            method = "llm_judge"
        else:
            score = self._entity_grounding_check(transcript, grounding)
            method = "entity_extraction"

        hallucination_rate = 100.0 - score
        threshold = context.get("hallucination_threshold", 1.0)

        return [MetricResult(
            name="hallucination_rate",
            value=round(hallucination_rate, 2),
            unit="%",
            passed=hallucination_rate <= threshold,
            threshold=threshold,
            details={
                "grounding_score": round(score, 2),
                "method": method,
            },
        )]

    @staticmethod
    def _collect_grounding(scenario: Scenario, summary: CallSummary) -> str:
        """Collect all factual context the agent should ground on."""
        parts: list[str] = []

        for event in summary.events:
            if event.type == EventType.TOOL_RESULT:
                parts.append(f"Tool result: {event.data}")

        for mock in scenario.tool_mocks:
            if mock.returns:
                parts.append(f"Tool '{mock.name}' returns: {mock.returns}")

        for turn in scenario.conversation:
            if turn.role == "caller" and turn.text:
                parts.append(f"Caller said: {turn.text}")

        return "\n".join(parts) if parts else "No specific grounding context available."

    @staticmethod
    async def _judge_hallucination(
        transcript: TranscriptResult,
        grounding: str,
        judge: Any,
    ) -> float:
        """Use LLM judge with structured chain-of-thought grounding check."""
        prompt = f"""You are evaluating a voice agent's response for hallucinations.

## Grounding Context (facts the agent can use)
{grounding}

## Agent's Response
{transcript.text}

## Instructions
1. List every FACTUAL CLAIM in the agent's response (names, numbers, dates, amounts, statuses)
2. For each claim, check if it is GROUNDED in the context above
3. Conversational filler ("Hello", "How can I help?", "Is there anything else?") is NOT a claim — skip it
4. Polite offers, greetings, and meta-conversation are NOT hallucinations

## Examples
- "Your appointment is at 2:00 PM" → check if 2:00 PM appears in tool results → GROUNDED or UNGROUNDED
- "Hello, how can I help you today?" → NOT A CLAIM (conversational filler)
- "Your balance is $500" → check if $500 appears in context → GROUNDED or UNGROUNDED

Score 0-100:
- 100 = All factual claims are grounded OR response is only conversational (no claims to check)
- 75 = Minor ungrounded details but core facts correct
- 50 = Mix of grounded and ungrounded claims
- 0 = Every factual claim is fabricated

Respond with JSON: {{"passed": true/false, "score": N, "reasoning": "..."}}"""

        result = await judge.evaluate(prompt, {
            "transcript": transcript.text,
            "knowledge_base": grounding,
        })
        return float(result.score)

    @staticmethod
    def _entity_grounding_check(transcript: TranscriptResult, grounding: str) -> float:
        """Check if factual entities in agent response appear in grounding context.

        Extracts entities in priority order (complex → simple) to avoid
        double-counting. A "$500" match consumes "500" so it isn't counted again.
        """
        if not transcript.text or not grounding:
            return 100.0  # No claims to check

        agent_text = transcript.text
        ground_text = grounding.lower()

        # Track character positions already claimed by higher-priority patterns
        claimed_spans: list[tuple[int, int]] = []

        def _is_claimed(start: int, end: int) -> bool:
            return any(cs <= start < ce or cs < end <= ce for cs, ce in claimed_spans)

        # Extract entities in priority order: complex patterns first
        # Each match is (entity_text, start_pos, end_pos)
        entities: list[str] = []

        # Priority 1: Money amounts (most specific)
        for m in re.finditer(r'\$\d+(?:,\d{3})*(?:\.\d{2})?', agent_text):
            if not _is_claimed(m.start(), m.end()):
                entities.append(m.group())
                claimed_spans.append((m.start(), m.end()))

        # Priority 2: Email addresses
        for m in re.finditer(r'\b[\w.+-]+@[\w-]+\.[\w.]+\b', agent_text):
            if not _is_claimed(m.start(), m.end()):
                entities.append(m.group())
                claimed_spans.append((m.start(), m.end()))

        # Priority 3: Order/reference numbers (ORD-123, REF-456)
        for m in re.finditer(r'\b[A-Z]{2,5}-\d{3,}\b', agent_text):
            if not _is_claimed(m.start(), m.end()):
                entities.append(m.group())
                claimed_spans.append((m.start(), m.end()))

        # Priority 4: Times (2:00 PM)
        for m in re.finditer(r'\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b', agent_text):
            if not _is_claimed(m.start(), m.end()):
                entities.append(m.group())
                claimed_spans.append((m.start(), m.end()))

        # Priority 5: Full dates (January 15, etc.)
        for m in re.finditer(
            r'\b(?:January|February|March|April|May|June|July|August|'
            r'September|October|November|December)\s+\d{1,2}\b',
            agent_text, re.IGNORECASE,
        ):
            if not _is_claimed(m.start(), m.end()):
                entities.append(m.group())
                claimed_spans.append((m.start(), m.end()))

        # Priority 6: Day names
        for m in re.finditer(
            r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',
            agent_text, re.IGNORECASE,
        ):
            if not _is_claimed(m.start(), m.end()):
                entities.append(m.group())
                claimed_spans.append((m.start(), m.end()))

        # Priority 7: Numbers (only if not already captured by a higher pattern)
        # Exclude trivial/non-factual numbers
        _trivial_numbers = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "100"}
        for m in re.finditer(r'\b\d+(?:\.\d+)?\b', agent_text):
            if not _is_claimed(m.start(), m.end()) and m.group() not in _trivial_numbers:
                entities.append(m.group())
                claimed_spans.append((m.start(), m.end()))

        if not entities:
            return 100.0  # No factual claims found

        # Check each entity against grounding
        grounded = sum(1 for entity in entities if entity.lower() in ground_text)

        return (grounded / len(entities)) * 100
