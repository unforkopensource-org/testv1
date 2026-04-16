"""Anthropic Claude judge provider."""

from __future__ import annotations

import asyncio
import logging
import statistics
from typing import Any

import httpx

from decibench.providers.judge._common import (
    JUDGE_SYSTEM_PROMPT,
    build_prompt,
    parse_judge_response,
)
from decibench.providers.registry import JudgeResult, register_judge

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 30.0


@register_judge("anthropic")
class AnthropicJudge:
    """LLM judge using Anthropic's native Messages API."""

    def __init__(self, uri: str = "", config_str: str = "", **kwargs: Any) -> None:
        del uri, config_str
        self._model = kwargs.get("model", "")
        self._api_key = kwargs.get("api_key", "") or self._get_env_api_key()
        self._temperature = kwargs.get("temperature", 0.0)
        self._judge_runs = int(kwargs.get("judge_runs", 1))

    @staticmethod
    def _get_env_api_key() -> str:
        import os

        return os.environ.get("ANTHROPIC_API_KEY", "")

    async def evaluate(self, prompt: str, context: dict[str, Any]) -> JudgeResult:
        if self._judge_runs > 1:
            return await self._evaluate_multi(prompt, context)
        return await self._evaluate_single(prompt, context)

    async def _evaluate_multi(self, prompt: str, context: dict[str, Any]) -> JudgeResult:
        tasks = [self._evaluate_single(prompt, context) for _ in range(self._judge_runs)]
        results = await asyncio.gather(*tasks)
        valid = [result for result in results if result.score > 0 or result.passed]
        if not valid:
            return results[0]

        median_score = statistics.median(result.score for result in valid)
        best = min(valid, key=lambda result: abs(result.score - median_score))
        return JudgeResult(
            passed=best.passed,
            score=median_score,
            reasoning=f"[median of {len(valid)}/{self._judge_runs} runs] {best.reasoning}",
            raw_output=best.raw_output,
        )

    async def _evaluate_single(self, prompt: str, context: dict[str, Any]) -> JudgeResult:
        if not self._api_key:
            return JudgeResult(
                passed=False,
                score=0.0,
                reasoning="Anthropic API key is not configured.",
            )

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self._model,
            "max_tokens": 1024,
            "temperature": self._temperature,
            "system": JUDGE_SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": build_prompt(prompt, context),
                }
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Anthropic judge API error: %s", exc)
            return JudgeResult(
                passed=False,
                score=0.0,
                reasoning=f"Anthropic judge API error: {exc.response.status_code}",
                raw_output=str(exc),
            )
        except httpx.HTTPError as exc:
            logger.error("Anthropic judge transport error: %s", exc)
            return JudgeResult(
                passed=False,
                score=0.0,
                reasoning=f"Anthropic judge transport error: {exc}",
                raw_output=str(exc),
            )

        data = response.json()
        try:
            raw_output = "\n".join(
                block["text"]
                for block in data["content"]
                if isinstance(block, dict) and block.get("type") == "text"
            )
        except (KeyError, TypeError) as exc:
            return JudgeResult(
                passed=False,
                score=0.0,
                reasoning=f"Invalid Anthropic judge response format: {exc}",
            )
        return parse_judge_response(raw_output)

    async def close(self) -> None:
        return None
