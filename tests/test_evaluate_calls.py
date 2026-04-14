
import pytest

from decibench.config import DecibenchConfig
from decibench.evaluators.hallucination import HallucinationEvaluator
from decibench.models import AgentEvent, CallTrace, EventType, TranscriptSegment
from decibench.replay.evaluate import ImportedCallEvaluator
from decibench.store.sqlite import RunStore


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


@pytest.mark.asyncio
async def test_evaluate_imported_call_can_be_persisted(tmp_path):
    trace = CallTrace(
        id="trace-persist",
        source="jsonl",
        transcript=[
            TranscriptSegment(role="caller", text="Where is my refund?", start_ms=0, end_ms=100),
            TranscriptSegment(role="agent", text="I can check your refund status.", start_ms=120, end_ms=200),
        ],
    )

    service = ImportedCallEvaluator([HallucinationEvaluator()], DecibenchConfig(), judge=None)
    result = await service.evaluate_trace(trace)

    store = RunStore(tmp_path / "decibench.sqlite")
    evaluation_id = store.save_call_evaluation(trace, result)
    loaded = store.get_call_evaluation(evaluation_id)

    assert loaded is not None
    assert loaded.scenario_id == result.scenario_id
