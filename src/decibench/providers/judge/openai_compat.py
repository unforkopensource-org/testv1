"""OpenAI-compatible LLM judge — universal interface for semantic evaluation.

One adapter covers: Ollama, vLLM, LM Studio, OpenAI, Groq, Together,
OpenRouter, Fireworks, Anthropic (via proxy), and any endpoint that
implements POST /v1/chat/completions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import statistics
from typing import Any

import httpx

from decibench.providers.registry import JudgeResult, register_judge

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 30.0

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


@register_judge("openai-compat")
class OpenAICompatJudge:
    """LLM judge using any OpenAI-compatible chat completions API."""

    def __init__(self, uri: str = "", config_str: str = "", **kwargs: Any) -> None:
        base_url = config_str.strip().lstrip("/")
        if not base_url:
            # Default to OpenAI's API
            base_url = "https://api.openai.com/v1"
        elif not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
        self._base_url = base_url.rstrip("/")
        self._model = kwargs.get("model", "")
        self._api_key = kwargs.get("api_key", "") or self._get_env_api_key()
        self._temperature = kwargs.get("temperature", 0.0)
        self._judge_runs = int(kwargs.get("judge_runs", 1))  # 3 = median of 3 runs

    @staticmethod
    def _get_env_api_key() -> str:
        """Fall back to OPENAI_API_KEY environment variable."""
        import os
        return os.environ.get("OPENAI_API_KEY", "")

    async def evaluate(self, prompt: str, context: dict[str, Any]) -> JudgeResult:
        if self._judge_runs > 1:
            return await self._evaluate_multi(prompt, context)
        return await self._evaluate_single(prompt, context)

    async def _evaluate_multi(self, prompt: str, context: dict[str, Any]) -> JudgeResult:
        """Run judge N times concurrently, return median score for stability."""
        tasks = [self._evaluate_single(prompt, context) for _ in range(self._judge_runs)]
        results = await asyncio.gather(*tasks)

        # Filter out failures (score=0 from API errors)
        valid = [r for r in results if r.score > 0 or r.passed]
        if not valid:
            return results[0]  # All failed — return first error

        scores = [r.score for r in valid]
        median_score = statistics.median(scores)

        # Pick the result closest to median for its reasoning
        best = min(valid, key=lambda r: abs(r.score - median_score))
        return JudgeResult(
            passed=best.passed,
            score=median_score,
            reasoning=f"[median of {len(valid)}/{self._judge_runs} runs] {best.reasoning}",
            raw_output=best.raw_output,
        )

    async def _evaluate_single(self, prompt: str, context: dict[str, Any]) -> JudgeResult:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # Build context-enriched prompt
        full_prompt = self._build_prompt(prompt, context)

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": full_prompt},
            ],
            "temperature": self._temperature,
        }

        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

            raw_output = data["choices"][0]["message"]["content"]
            return self._parse_response(raw_output)

        except httpx.HTTPStatusError as e:
            logger.error("Judge API error: %s", e)
            return JudgeResult(
                passed=False,
                score=0.0,
                reasoning=f"Judge API error: {e.response.status_code}",
                raw_output=str(e),
            )
        except (KeyError, IndexError) as e:
            logger.error("Judge response parsing error: %s", e)
            return JudgeResult(
                passed=False,
                score=0.0,
                reasoning=f"Invalid judge response format: {e}",
            )

    async def close(self) -> None:
        pass

    @staticmethod
    def _build_prompt(prompt: str, context: dict[str, Any]) -> str:
        """Build the evaluation prompt with context."""
        parts = [prompt]

        if "transcript" in context:
            parts.append(f"\n## Conversation Transcript\n{context['transcript']}")

        if "expected" in context:
            parts.append(f"\n## Expected Behavior\n{context['expected']}")

        if "tool_calls" in context:
            parts.append(
                f"\n## Tool Calls Made\n{json.dumps(context['tool_calls'], indent=2)}"
            )

        if "knowledge_base" in context:
            parts.append(f"\n## Knowledge Base\n{context['knowledge_base']}")

        return "\n".join(parts)

    @staticmethod
    def _parse_response(raw: str) -> JudgeResult:
        """Parse JSON response from the judge LLM.

        Handles both clean JSON and JSON embedded in markdown code blocks.
        """
        text = raw.strip()

        # Try to extract JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1)

        # Try direct JSON parse
        try:
            data = json.loads(text)
            return JudgeResult(
                passed=bool(data.get("passed", False)),
                score=float(data.get("score", 0.0)),
                reasoning=str(data.get("reasoning", "")),
                raw_output=raw,
            )
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: try to find JSON object in the text
        brace_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if brace_match:
            try:
                data = json.loads(brace_match.group())
                return JudgeResult(
                    passed=bool(data.get("passed", False)),
                    score=float(data.get("score", 0.0)),
                    reasoning=str(data.get("reasoning", "")),
                    raw_output=raw,
                )
            except (json.JSONDecodeError, ValueError):
                pass

        # Could not parse — return failure with raw output for debugging
        logger.warning("Could not parse judge response as JSON: %s", raw[:200])
        return JudgeResult(
            passed=False,
            score=0.0,
            reasoning=f"Failed to parse judge output: {raw[:200]}",
            raw_output=raw,
        )
