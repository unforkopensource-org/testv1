"""No-op judge — for deterministic-only mode.

When judge = "none", all semantic evaluators are skipped and only
deterministic + statistical metrics run. Zero cost, zero API keys.
"""

from __future__ import annotations

from typing import Any

from decibench.providers.registry import JudgeResult, register_judge


@register_judge("none")
class NoneJudge:
    """No-op judge that always returns a neutral result.

    Used when judge = "none" in config. The orchestrator checks
    config.has_judge before calling semantic evaluators, so this
    should rarely be called directly.
    """

    def __init__(self, uri: str = "", config_str: str = "", **kwargs: Any) -> None:
        pass

    async def evaluate(self, prompt: str, context: dict[str, Any]) -> JudgeResult:
        return JudgeResult(
            passed=True,
            score=0.0,
            reasoning="No LLM judge configured (judge = 'none'). Semantic evaluation skipped.",
        )

    async def close(self) -> None:
        pass
