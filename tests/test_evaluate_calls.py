
import pytest

from decibench.config import DecibenchConfig
from decibench.evaluators.hallucination import HallucinationEvaluator
from decibench.models import AgentEvent, CallTrace, EventType, TranscriptSegment
from decibench.replay.evaluate import ImportedCallEvaluator


@pytest.mark.asyncio
async def test_evaluate_imported_call():
    trace = CallTrace(
        id="trace-123",
        source="vapi",
        target="demo",
        events=[
            AgentEvent(type=EventType.TOOL_CALL, timestamp_ms=100.0, data={"tool": "get_weather"}),
        ],
        transcript=[
            TranscriptSegment(role="caller", text="What is the weather?", start_ms=0, end_ms=100),
            TranscriptSegment(role="agent", text="It is 75 degrees.", start_ms=150, end_ms=250),
        ]
    )

    config = DecibenchConfig()
    evaluators = [HallucinationEvaluator()]

    # We pass no judge, hallucination should skip without raising errors
    service = ImportedCallEvaluator(evaluators, config, judge=None)
    result = await service.evaluate_trace(trace)

    # Missing judge means hallucination evaluator will skip.
    # Therefore it should just pass with base metrics.
    assert result.scenario_id.startswith("imported-")
    assert result.passed
