"""Orchestrator — the central execution engine.

CLI, MCP, and server are all thin wrappers around this.
Same input + same config = same result. Always.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from decibench.audio.recorder import AudioRecorder
from decibench.audio.synthesizer import AudioSynthesizer
from decibench.connectors.registry import get_connector
from decibench.evaluators.compliance import ComplianceEvaluator
from decibench.evaluators.hallucination import HallucinationEvaluator
from decibench.evaluators.interruption import InterruptionEvaluator
from decibench.evaluators.latency import LatencyEvaluator
from decibench.evaluators.mos import MOSEvaluator
from decibench.evaluators.score import DecibenchScorer
from decibench.evaluators.silence import SilenceEvaluator
from decibench.evaluators.stoi import STOIEvaluator
from decibench.evaluators.task import TaskCompletionEvaluator
from decibench.evaluators.wer import WEREvaluator
from decibench.models import (
    AudioBuffer,
    CallSummary,
    CostBreakdown,
    EvalResult,
    EventType,
    MetricResult,
    Scenario,
    SuiteResult,
    TraceSpan,
    TranscriptResult,
)
from decibench.providers.registry import get_judge, get_stt, get_tts
from decibench.scenarios.loader import ScenarioLoader

if TYPE_CHECKING:
    from decibench.config import DecibenchConfig
    from decibench.evaluators.base import BaseEvaluator

logger = logging.getLogger(__name__)


class Orchestrator:
    """Central execution engine for Decibench.

    Composes connectors, providers, evaluators, and scenarios into
    a complete test pipeline. Every external interface (CLI, MCP, server)
    calls this — ensuring identical behavior regardless of entry point.
    """

    # Type for progress callback: (scenario_id, passed, score, current, total)
    ProgressCallback = Any  # Callable[[str, bool, float, int, int], None]

    def __init__(self, config: DecibenchConfig) -> None:
        self._config = config
        self._scenario_loader = ScenarioLoader()
        self._scorer = DecibenchScorer()
        self._progress_callback: Any | None = None
        self._completed_count: int = 0

        # Evaluators — ordered: deterministic first, then statistical, then semantic
        self._evaluators: list[BaseEvaluator] = [
            WEREvaluator(),
            LatencyEvaluator(),
            MOSEvaluator(),
            STOIEvaluator(),
            SilenceEvaluator(),
            ComplianceEvaluator(),
            TaskCompletionEvaluator(),
            HallucinationEvaluator(),
            InterruptionEvaluator(),
        ]

    async def run_suite(
        self,
        target: str,
        suite: str = "quick",
        noise_levels: list[str] | None = None,
        accents: list[str] | None = None,
        parallel: int = 5,
        scenario_filter: str | None = None,
        on_progress: Any | None = None,
    ) -> SuiteResult:
        """Run a complete test suite against a voice agent.

        Args:
            target: Target URI (ws://, exec:, http://, demo)
            suite: Suite name (quick, standard, full)
            noise_levels: Override noise levels for variant expansion
            accents: Override accents for variant expansion
            parallel: Max concurrent scenario runs

        Returns:
            Complete suite results with Decibench Score
        """
        start_time = time.monotonic()

        # 1. Load scenarios
        scenarios = self._scenario_loader.load_suite(suite)

        # 1b. Filter to single scenario if requested
        if scenario_filter:
            scenarios = [
                s for s in scenarios
                if s.id == scenario_filter or scenario_filter in s.id
            ]
            if not scenarios:
                logger.error("No scenario matching '%s' found", scenario_filter)

        # 2. Expand variants if requested
        if noise_levels or accents:
            scenarios = self._scenario_loader.expand_variants(
                scenarios, noise_levels, accents
            )

        self._progress_callback = on_progress
        self._completed_count = 0

        # 3. Resolve providers (skip TTS/STT for demo target)
        is_demo = target in ("demo", "demo://")
        tts = None if is_demo else get_tts(self._config.providers.tts)
        stt = None if is_demo else get_stt(self._config.providers.stt)
        judge = (
            get_judge(
                self._config.providers.judge,
                model=self._config.providers.judge_model,
                api_key=self._config.providers.judge_api_key,
                temperature=self._config.evaluation.judge_temperature,
                judge_runs=self._config.evaluation.judge_runs,
            )
            if self._config.has_judge
            else None
        )

        synthesizer = (
            AudioSynthesizer(
                tts_provider=tts,
                noise_profiles_dir=self._config.audio.noise_profiles_dir,
            )
            if tts is not None
            else None
        )

        # 4. Run scenarios with concurrency control
        semaphore = asyncio.Semaphore(parallel)
        tasks = [
            self._run_scenario_with_retries(
                scenario=scenario,
                target=target,
                synthesizer=synthesizer,
                stt=stt,
                judge=judge,
                semaphore=semaphore,
            )
            for scenario in scenarios
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 5. Process results, handling any exceptions
        total = len(scenarios)
        eval_results: list[EvalResult] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.error(
                    "Scenario '%s' failed with error: %s",
                    scenarios[i].id,
                    result,
                )
                er = EvalResult(
                    scenario_id=scenarios[i].id,
                    passed=False,
                    score=0.0,
                    failures=[f"Execution error: {result}"],
                )
                eval_results.append(er)
            else:
                eval_results.append(result)

            # Fire progress callback
            if self._progress_callback:
                r = eval_results[-1]
                with contextlib.suppress(Exception):
                    self._progress_callback(r.scenario_id, r.passed, r.score, i + 1, total)

        # 6. Calculate composite score with category breakdown
        score, score_breakdown = self._scorer.calculate(
            eval_results,
            self._config.scoring.weights,
            has_judge=self._config.has_judge,
        )

        # 7. Aggregate latency stats
        latency = self._aggregate_latency(eval_results)

        # 8. Sum costs
        cost = self._aggregate_cost(eval_results)

        duration = time.monotonic() - start_time
        passed = sum(1 for r in eval_results if r.passed)

        # Determine judge model used
        judge_model = self._config.providers.judge_model if self._config.has_judge else "none"

        # Cleanup
        if synthesizer is not None:
            await synthesizer.close()
        if stt is not None and hasattr(stt, "close"):
            await stt.close()
        if judge is not None and hasattr(judge, "close"):
            await judge.close()

        return SuiteResult(
            suite=suite,
            target=target,
            decibench_score=score,
            score_breakdown=score_breakdown,
            total_scenarios=len(eval_results),
            passed=passed,
            failed=len(eval_results) - passed,
            results=eval_results,
            latency=latency,
            cost=cost,
            duration_seconds=round(duration, 1),
            judge_model=judge_model,
            config_hash=SuiteResult.compute_config_hash(
                self._config.model_dump(mode="json")
            ),
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def _run_scenario_with_retries(
        self,
        scenario: Scenario,
        target: str,
        synthesizer: AudioSynthesizer | None,
        stt: Any | None,
        judge: Any | None,
        semaphore: asyncio.Semaphore,
    ) -> EvalResult:
        """Run a single scenario with multiple runs for statistical reliability."""
        async with semaphore:
            runs: list[EvalResult] = []
            for run_idx in range(self._config.evaluation.runs_per_scenario):
                try:
                    result = await self._run_single_scenario(
                        scenario=scenario,
                        target=target,
                        synthesizer=synthesizer,
                        stt=stt,
                        judge=judge,
                        run_index=run_idx,
                    )
                    runs.append(result)
                except Exception as e:
                    logger.warning(
                        "Run %d of scenario '%s' failed: %s",
                        run_idx,
                        scenario.id,
                        e,
                    )
                    runs.append(EvalResult(
                        scenario_id=scenario.id,
                        passed=False,
                        score=0.0,
                        failures=[str(e)],
                        run_index=run_idx,
                    ))

            return self._average_runs(runs) if runs else EvalResult(
                scenario_id=scenario.id,
                passed=False,
                score=0.0,
                failures=["All runs failed"],
            )

    async def _run_single_scenario(
        self,
        scenario: Scenario,
        target: str,
        synthesizer: AudioSynthesizer | None,
        stt: Any | None,
        judge: Any | None,
        run_index: int,
    ) -> EvalResult:
        """Execute a single scenario run end-to-end."""
        start = time.monotonic()

        # 1. Get connector
        connector = get_connector(target)
        is_demo = target in ("demo", "demo://")

        # 2. Connect to agent
        auth_config = self._config.auth.model_dump()
        handle = await connector.connect(target, auth_config)

        all_metrics: dict[str, MetricResult] = {}
        transcript = TranscriptResult(text="")
        summary = CallSummary(duration_ms=0, turn_count=0)
        last_caller_audio: AudioBuffer | None = None
        spans: list[TraceSpan] = []

        try:
            # 3. For each caller turn, synthesize and send audio
            for turn_idx, turn in enumerate(scenario.caller_turns):
                if not turn.text:
                    continue

                if is_demo:
                    caller_audio = AudioBuffer(
                        data=b"\x00" * 3200,
                        sample_rate=16000,
                    )
                elif synthesizer is not None:
                    tts_start = time.monotonic()
                    caller_audio = await synthesizer.synthesize(
                        text=turn.text,
                        persona=scenario.persona,
                        target_sample_rate=connector.required_sample_rate,
                        target_encoding=connector.required_encoding,
                    )
                    tts_duration = (time.monotonic() - tts_start) * 1000
                    spans.append(TraceSpan(
                        name="tts",
                        start_ms=tts_start * 1000,
                        end_ms=tts_start * 1000 + tts_duration,
                        duration_ms=tts_duration,
                        turn_index=turn_idx
                    ))
                else:
                    caller_audio = AudioBuffer(data=b"\x00" * 3200, sample_rate=16000)

                last_caller_audio = caller_audio

                turn_start = time.monotonic()
                await connector.send_audio(handle, caller_audio)

                async for _event in connector.receive_events(handle):
                    pass

                turn_duration = (time.monotonic() - turn_start) * 1000
                spans.append(TraceSpan(
                    name="turn_latency",
                    start_ms=turn_start * 1000,
                    end_ms=turn_start * 1000 + turn_duration,
                    duration_ms=turn_duration,
                    turn_index=turn_idx
                ))

            # 4. Disconnect and get summary
            summary = await connector.disconnect(handle)

            # 5. Transcribe agent response
            if is_demo:
                transcript_parts = []
                for event in summary.events:
                    if event.type == EventType.AGENT_TRANSCRIPT:
                        transcript_parts.append(event.data.get("text", ""))
                transcript = TranscriptResult(
                    text=" ".join(transcript_parts),
                    language="en",
                    duration_ms=summary.duration_ms,
                )
            else:
                # Try agent-provided transcript from events first
                agent_transcript_parts = []
                for event in summary.events:
                    if event.type == EventType.AGENT_TRANSCRIPT and event.data:
                        text = event.data.get("text", "") or event.data.get("message", "")
                        if text:
                            agent_transcript_parts.append(text)

                if agent_transcript_parts:
                    transcript = TranscriptResult(
                        text=" ".join(agent_transcript_parts),
                        language="en",
                        duration_ms=summary.duration_ms,
                    )
                elif stt is not None and summary.agent_audio:
                    stt_start = time.monotonic()
                    agent_audio_buf = AudioBuffer(
                        data=summary.agent_audio,
                        sample_rate=connector.required_sample_rate,
                    )
                    transcript = await stt.transcribe(agent_audio_buf)
                    stt_duration = (time.monotonic() - stt_start) * 1000
                    spans.append(TraceSpan(
                        name="stt",
                        start_ms=stt_start * 1000,
                        end_ms=stt_start * 1000 + stt_duration,
                        duration_ms=stt_duration
                    ))

            # 5b. Save audio to disk if output dir configured
            output_dir = (
                self._config.evaluation.output_dir
                if hasattr(self._config.evaluation, 'output_dir')
                else None
            )
            if output_dir and summary.agent_audio:
                try:
                    from pathlib import Path
                    audio_buf = AudioBuffer(
                        data=summary.agent_audio,
                        sample_rate=connector.required_sample_rate,
                    )
                    audio_path = Path(output_dir) / f"{scenario.id}_run{run_index}.wav"
                    AudioRecorder.save_wav(audio_buf, audio_path)
                except Exception as e:
                    logger.debug("Could not save audio for %s: %s", scenario.id, e)

            # 6. Run evaluators
            eval_context: dict[str, Any] = {
                "judge": judge,
                "config": self._config,
                "p50_max_ms": (self._config.ci.max_p95_latency_ms or 1500) * 0.53,  # ~800ms
                "p95_max_ms": self._config.ci.max_p95_latency_ms or 1500,
                "p99_max_ms": (self._config.ci.max_p95_latency_ms or 1500) * 2.0,  # ~3000ms
                "ttfw_max_ms": (self._config.ci.max_p95_latency_ms or 1500) * 0.53,  # ~800ms
                # Fix #4: Pass reference audio for real STOI computation
                "reference_audio": last_caller_audio.data if last_caller_audio else None,
            }

            for evaluator in self._evaluators:
                # Skip semantic evaluators when no judge
                if evaluator.requires_judge and judge is None:
                    continue

                try:
                    metrics = await evaluator.evaluate(
                        scenario, summary, transcript, eval_context
                    )
                    for metric in metrics:
                        all_metrics[metric.name] = metric
                except Exception as e:
                    logger.warning(
                        "Evaluator '%s' failed on scenario '%s': %s",
                        evaluator.name,
                        scenario.id,
                        e,
                    )

        except TimeoutError:
            all_metrics["timeout"] = MetricResult(
                name="timeout",
                value=1.0,
                passed=False,
                details={"timeout_seconds": scenario.timeout_seconds},
            )
        except Exception as e:
            logger.error("Scenario '%s' execution error: %s", scenario.id, e)
            return EvalResult(
                scenario_id=scenario.id,
                passed=False,
                score=0.0,
                failures=[f"Execution error: {e}"],
                duration_ms=(time.monotonic() - start) * 1000,
                run_index=run_index,
            )

        # 7. Determine pass/fail
        failures = [
            f"{m.name}: {m.value} (threshold: {m.threshold})"
            for m in all_metrics.values()
            if not m.passed
        ]
        passed = len(failures) == 0

        # Build failure_summary: which categories failed
        from decibench.evaluators.score import _METRIC_CATEGORIES
        failed_categories = set()
        for m in all_metrics.values():
            if not m.passed and m.name in _METRIC_CATEGORIES:
                failed_categories.add(_METRIC_CATEGORIES[m.name])
        failure_summary = sorted(failed_categories)

        # 8. Calculate per-scenario score
        scenario_results = [EvalResult(
            scenario_id=scenario.id,
            passed=passed,
            score=0.0,
            metrics=all_metrics,
        )]
        score, _ = self._scorer.calculate(
            scenario_results,
            self._config.scoring.weights,
            self._config.has_judge,
        )

        duration_ms = (time.monotonic() - start) * 1000

        return EvalResult(
            scenario_id=scenario.id,
            passed=passed,
            score=score,
            metrics=all_metrics,
            failures=failures,
            failure_summary=failure_summary,
            latency={
                k: m.value for k, m in all_metrics.items()
                if "latency" in k or "ttfw" in k
            },
            duration_ms=round(duration_ms, 1),
            transcript=[
                {"role": seg.role, "text": seg.text}
                for seg in transcript.segments
            ],
            run_index=run_index,
            spans=spans,
        )

    @staticmethod
    def _average_runs(runs: list[EvalResult]) -> EvalResult:
        """Average metrics across multiple runs of the same scenario."""
        if len(runs) == 1:
            return runs[0]

        # Use the first run as template
        base = runs[0]

        # Average numeric metrics
        averaged_metrics: dict[str, MetricResult] = {}
        for metric_name in base.metrics:
            values = [
                r.metrics[metric_name].value
                for r in runs
                if metric_name in r.metrics
            ]
            if values:
                avg_value = sum(values) / len(values)
                template = base.metrics[metric_name]
                averaged_metrics[metric_name] = MetricResult(
                    name=template.name,
                    value=round(avg_value, 2),
                    unit=template.unit,
                    passed=template.passed,  # Re-evaluate based on avg
                    threshold=template.threshold,
                    details={"runs": len(values), "values": values},
                )

        # Re-check pass/fail with averaged values
        for metric in averaged_metrics.values():
            if metric.threshold is not None:
                lower_is_better = (
                    "latency" in metric.name
                    or "ttfw" in metric.name
                    or metric.name in ("wer", "cer", "hallucination_rate", "silence_pct")
                )
                if lower_is_better:
                    metric.passed = metric.value <= metric.threshold
                else:
                    metric.passed = metric.value >= metric.threshold

        failures = [
            f"{m.name}: {m.value} (threshold: {m.threshold})"
            for m in averaged_metrics.values()
            if not m.passed
        ]

        avg_score = sum(r.score for r in runs) / len(runs)

        return EvalResult(
            scenario_id=base.scenario_id,
            passed=len(failures) == 0,
            score=round(avg_score, 1),
            metrics=averaged_metrics,
            failures=failures,
            latency=base.latency,
            duration_ms=sum(r.duration_ms for r in runs) / len(runs),
            transcript=base.transcript,
        )

    @staticmethod
    def _aggregate_latency(results: list[EvalResult]) -> dict[str, float]:
        """Aggregate latency metrics across all scenarios."""
        p50_values = []
        p95_values = []
        p99_values = []

        for r in results:
            if "turn_latency_p50_ms" in r.metrics:
                p50_values.append(r.metrics["turn_latency_p50_ms"].value)
            if "turn_latency_p95_ms" in r.metrics:
                p95_values.append(r.metrics["turn_latency_p95_ms"].value)
            if "turn_latency_p99_ms" in r.metrics:
                p99_values.append(r.metrics["turn_latency_p99_ms"].value)

        return {
            "p50_ms": round(sum(p50_values) / len(p50_values), 1) if p50_values else 0,
            "p95_ms": round(sum(p95_values) / len(p95_values), 1) if p95_values else 0,
            "p99_ms": round(sum(p99_values) / len(p99_values), 1) if p99_values else 0,
        }

    @staticmethod
    def _aggregate_cost(results: list[EvalResult]) -> CostBreakdown:
        """Sum costs across all scenarios."""
        total = CostBreakdown()
        for r in results:
            total.tts += r.cost.get("tts", 0)
            total.stt += r.cost.get("stt", 0)
            total.judge += r.cost.get("judge", 0)
            total.platform += r.cost.get("platform", 0)
        return total
