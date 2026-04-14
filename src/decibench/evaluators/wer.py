"""WER/CER evaluator — foundational ASR accuracy metric.

WER = (Substitutions + Deletions + Insertions) / Total Reference Words x 100%
Auto-switches to CER for CJK languages.
"""

from __future__ import annotations

from typing import Any

from decibench.evaluators.base import BaseEvaluator
from decibench.models import CallSummary, MetricResult, Scenario, TranscriptResult

# Languages that should use CER instead of WER
_CJK_LANGUAGES = {"ja", "zh", "ko", "th", "km", "lo", "my"}


class WEREvaluator(BaseEvaluator):
    """Word Error Rate and Character Error Rate evaluation."""

    @property
    def name(self) -> str:
        return "wer"

    async def evaluate(
        self,
        scenario: Scenario,
        summary: CallSummary,
        transcript: TranscriptResult,
        context: dict[str, Any],
    ) -> list[MetricResult]:
        results: list[MetricResult] = []

        hypothesis = transcript.text.strip()
        if not hypothesis:
            results.append(MetricResult(
                name="wer",
                value=100.0,
                unit="%",
                passed=False,
                threshold=10.0,
                details={"reason": "No agent response transcribed"},
            ))
            return results

        language = transcript.language

        # 1. Keyword presence check (must_include / must_not_say)
        keyword_results = self._check_keywords(scenario, hypothesis)
        results.extend(keyword_results)

        # 2. WER/CER only if we have full reference text
        reference_texts = self._get_full_reference_texts(scenario)
        if reference_texts:
            if language in _CJK_LANGUAGES:
                error_rate = self._calculate_cer(reference_texts, hypothesis)
                metric_name = "cer"
                threshold = 3.0
            else:
                error_rate = self._calculate_wer(reference_texts, hypothesis)
                metric_name = "wer"
                threshold = context.get("wer_threshold", 10.0)

            results.append(MetricResult(
                name=metric_name,
                value=round(error_rate, 2),
                unit="%",
                passed=error_rate <= threshold,
                threshold=threshold,
                details={
                    "reference_sample": reference_texts[0][:100],
                    "hypothesis_sample": hypothesis[:100],
                    "language": language,
                },
            ))

        return results

    @staticmethod
    def _calculate_wer(references: list[str], hypothesis: str) -> float:
        """Calculate WER using jiwer against best-matching reference."""
        import jiwer

        # Normalize texts
        transform = jiwer.Compose([
            jiwer.ToLowerCase(),
            jiwer.RemoveMultipleSpaces(),
            jiwer.Strip(),
            jiwer.RemovePunctuation(),  # type: ignore[no-untyped-call]
        ])

        hypothesis_clean = transform(hypothesis)

        best_wer = 100.0
        for ref in references:
            ref_clean = transform(ref)
            if not ref_clean:
                continue
            wer = jiwer.wer(ref_clean, hypothesis_clean) * 100
            best_wer = min(best_wer, wer)

        return best_wer

    @staticmethod
    def _calculate_cer(references: list[str], hypothesis: str) -> float:
        """Calculate CER for character-based languages."""
        import jiwer

        best_cer = 100.0
        for ref in references:
            # Character-level: split each string into individual characters
            ref_chars = " ".join(list(ref.strip()))
            hyp_chars = " ".join(list(hypothesis.strip()))
            if not ref_chars:
                continue
            cer = jiwer.wer(ref_chars, hyp_chars) * 100
            best_cer = min(best_cer, cer)

        return best_cer

    @staticmethod
    def _get_reference_texts(scenario: Scenario) -> list[str]:
        """Extract reference texts from scenario expectations."""
        refs: list[str] = []
        for turn in scenario.conversation:
            if turn.role == "agent" and turn.expect:
                if turn.expect.must_include:
                    refs.extend(turn.expect.must_include)
                if turn.text:
                    refs.append(turn.text)
        return refs

    @staticmethod
    def _get_full_reference_texts(scenario: Scenario) -> list[str]:
        """Extract full reference texts (agent turn text) from scenario."""
        refs: list[str] = []
        for turn in scenario.conversation:
            if turn.role == "agent" and turn.text:
                refs.append(turn.text)
        return refs

    def _check_keywords(self, scenario: Scenario, hypothesis: str) -> list[MetricResult]:
        """Check must_include and must_not_say keyword constraints."""
        results: list[MetricResult] = []
        hyp_lower = hypothesis.lower()

        for turn in scenario.conversation:
            if turn.role != "agent" or not turn.expect:
                continue

            # must_include check
            if turn.expect.must_include:
                missing = [
                    kw for kw in turn.expect.must_include
                    if kw.lower() not in hyp_lower
                ]
                results.append(MetricResult(
                    name="keyword_presence",
                    value=round(
                        (1 - len(missing) / len(turn.expect.must_include)) * 100, 1
                    ),
                    unit="%",
                    passed=len(missing) == 0,
                    threshold=100.0,
                    details={
                        "required": turn.expect.must_include,
                        "missing": missing,
                    },
                ))

            # must_not_say check
            if hasattr(turn.expect, "must_not_say") and turn.expect.must_not_say:
                found = [
                    kw for kw in turn.expect.must_not_say
                    if kw.lower() in hyp_lower
                ]
                results.append(MetricResult(
                    name="keyword_absence",
                    value=round(
                        (1 - len(found) / len(turn.expect.must_not_say)) * 100, 1
                    ),
                    unit="%",
                    passed=len(found) == 0,
                    threshold=100.0,
                    details={
                        "forbidden": turn.expect.must_not_say,
                        "found": found,
                    },
                ))

        return results
