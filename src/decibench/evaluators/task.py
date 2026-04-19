"""Task completion evaluator — did the agent achieve the caller's goal?

Uses a combination of deterministic checks (tool calls, slot extraction)
and LLM judge (semantic goal achievement) when available.
"""

from __future__ import annotations

from typing import Any

from decibench.evaluators.base import BaseEvaluator
from decibench.models import (
    CallSummary,
    EventType,
    MetricResult,
    Scenario,
    TranscriptResult,
)


class TaskCompletionEvaluator(BaseEvaluator):
    """Evaluate whether the agent completed the caller's task."""

    @property
    def name(self) -> str:
        return "task_completion"

    @property
    def requires_judge(self) -> bool:
        return True  # Best results with LLM judge, but can do partial deterministic

    async def evaluate(
        self,
        scenario: Scenario,
        summary: CallSummary,
        transcript: TranscriptResult,
        context: dict[str, Any],
    ) -> list[MetricResult]:
        results: list[MetricResult] = []

        has_tool_mocks = bool(scenario.tool_mocks)
        slot_score = self._check_slot_extraction(scenario, summary, transcript)
        has_slots = slot_score is not None

        # --- Deterministic: check tool calls match expectations ---
        if has_tool_mocks:
            tool_score = self._check_tool_calls(scenario, summary)
            results.append(MetricResult(
                name="tool_call_correctness",
                value=round(tool_score, 1),
                unit="%",
                passed=tool_score >= 95.0,
                threshold=95.0,
            ))
        else:
            tool_score = None

        # --- Deterministic: slot extraction accuracy ---
        if has_slots:
            results.append(MetricResult(
                name="slot_extraction_accuracy",
                value=round(slot_score, 1),
                unit="%",
                passed=slot_score >= 90.0,
                threshold=90.0,
            ))

        # --- Semantic: LLM judge for goal achievement ---
        judge = context.get("judge")
        if judge is not None and transcript.text and transcript.text.strip():
            judge_result = await self._judge_task_completion(scenario, transcript, judge)
            results.append(MetricResult(
                name="task_completion",
                value=round(judge_result, 1),
                unit="%",
                passed=judge_result >= 90.0,
                threshold=90.0,
            ))
        elif has_tool_mocks or has_slots:
            # Without judge but with deterministic signals: average them
            scores = []
            if tool_score is not None:
                scores.append(tool_score)
            if slot_score is not None:
                scores.append(slot_score)
            deterministic_score = sum(scores) / len(scores)
            results.append(MetricResult(
                name="task_completion",
                value=round(deterministic_score, 1),
                unit="%",
                passed=deterministic_score >= 90.0,
                threshold=90.0,
                details={"method": "deterministic_only"},
            ))
        # else: no mocks, no slots, no judge → return NO task_completion
        # metric.  The score calculator will exclude this category from
        # the weighted average instead of giving a free 100%.

        return results

    @staticmethod
    def _check_tool_calls(scenario: Scenario, summary: CallSummary) -> float:
        """Check if the right tools were called with the right parameters."""
        if not scenario.tool_mocks:
            return 100.0  # No tools expected, so no failures

        expected_tools = {mock.name: mock for mock in scenario.tool_mocks}
        actual_calls = [
            e.data for e in summary.events
            if e.type == EventType.TOOL_CALL
        ]

        if not expected_tools:
            return 100.0

        correct = 0
        total = len(expected_tools)

        for tool_name, mock in expected_tools.items():
            # Check if the tool was called
            matching = [c for c in actual_calls if c.get("name") == tool_name]
            if not matching:
                continue

            call = matching[0]
            # Check parameters
            if mock.when_called_with:
                call_args = call.get("args", call.get("arguments", {}))
                params_match = all(
                    str(call_args.get(k, "")).lower() == str(v).lower()
                    for k, v in mock.when_called_with.items()
                )
                if params_match:
                    correct += 1
            else:
                correct += 1  # Tool called, no specific params expected

        return (correct / total) * 100 if total > 0 else 100.0

    @staticmethod
    def _check_slot_extraction(
        scenario: Scenario,
        summary: CallSummary,
        transcript: TranscriptResult,
    ) -> float | None:
        """Check if the agent extracted the right values from caller speech.

        Uses per-turn checking: matches expected slots against the
        transcript segment closest to the relevant turn, not the full blob.
        Falls back to full text if segments aren't available.
        """
        # Collect expected slots with their turn index
        slot_checks: list[tuple[int, dict[str, str]]] = []
        agent_turn_idx = 0
        for turn in scenario.conversation:
            if turn.role == "agent":
                if turn.expect and turn.expect.must_extract:
                    slot_checks.append((agent_turn_idx, turn.expect.must_extract))
                agent_turn_idx += 1

        if not slot_checks:
            return None

        # Build per-turn agent text from segments
        agent_segments = [
            seg.text.lower() for seg in transcript.segments if seg.text
        ] if transcript.segments else []
        full_text = transcript.text.lower()

        correct = 0
        total = 0
        for turn_idx, slots in slot_checks:
            # Pick text for this specific turn
            if agent_segments and turn_idx < len(agent_segments):
                check_text = agent_segments[turn_idx]
            else:
                check_text = full_text

            for _slot_name, expected_value in slots.items():
                total += 1
                if expected_value.lower() in check_text:
                    correct += 1

        return (correct / total) * 100 if total > 0 else 100.0

    @staticmethod
    async def _judge_task_completion(
        scenario: Scenario,
        transcript: TranscriptResult,
        judge: Any,
    ) -> float:
        """Use LLM judge to evaluate goal achievement."""
        goal = scenario.goal or "Complete the task described in the scenario"
        criteria = [c.description or c.type for c in scenario.success_criteria]

        criteria_text = (
            chr(10).join(f'- {c}' for c in criteria)
            if criteria
            else 'Task was completed successfully'
        )

        prompt = f"""Evaluate whether the voice agent successfully completed the caller's task.

## Caller's Goal
{goal}

## Success Criteria
{criteria_text}

## Agent's Response
{transcript.text}

## Instructions
1. For EACH success criterion above, determine: was it MET, PARTIALLY MET, or NOT MET?
2. Cite specific evidence from the agent's response for each judgment
3. Conversational filler (greetings, closings) does not count for or against

## Scoring
- 100 = All criteria fully met with correct information
- 75 = Most criteria met, minor omissions
- 50 = Some criteria met, significant gaps
- 25 = Few criteria met, major task failure
- 0 = No criteria met, complete failure

Respond with JSON: {{"passed": true/false, "score": N, "reasoning": "criterion-by-criterion assessment"}}"""

        result = await judge.evaluate(prompt, {
            "transcript": transcript.text,
            "expected": goal,
        })
        return float(result.score)
