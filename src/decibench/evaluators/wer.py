"""WER/CER evaluator — ASR accuracy with weighted intent scoring.

Three-layer architecture:
1. Pre-processing pipeline (jiwer.Compose) — normalize text
2. Alignment engine (jiwer.process_words) — exact word-level alignment map
3. Weighted intent evaluator — penalize critical keyword misses heavily

WER_weighted = sum(errors * weight) / total_reference_words
"""

from __future__ import annotations

from typing import Any

from decibench.evaluators.base import BaseEvaluator
from decibench.models import CallSummary, MetricResult, Scenario, TranscriptResult

# Languages that should use CER instead of WER
_CJK_LANGUAGES = {"ja", "zh", "ko", "th", "km", "lo", "my"}

# Default weight for non-critical word errors
_DEFAULT_WORD_WEIGHT = 1.0

# Weight for critical keyword misses (must_include words)
_CRITICAL_WORD_WEIGHT = 10.0


class WEREvaluator(BaseEvaluator):
    """Word Error Rate and Character Error Rate evaluation.

    Uses jiwer.process_words() for full alignment metadata,
    enabling weighted scoring where critical keyword misses
    are penalized far more than filler word errors.
    """

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

        agent_text = transcript.text.strip()
        if not agent_text:
            results.append(MetricResult(
                name="wer",
                value=100.0,
                unit="%",
                passed=False,
                threshold=context.get("wer_threshold", 10.0),
                details={"reason": "No agent response transcribed"},
            ))
            return results

        language = transcript.language

        # Collect critical keywords from scenario expectations
        critical_keywords = self._collect_critical_keywords(scenario)

        # 1. Per-turn keyword presence check (turn-aware, not full-blob)
        keyword_results = self._check_keywords_per_turn(scenario, transcript)
        results.extend(keyword_results)

        # 2. WER/CER against reference texts (agent turn text if available)
        reference_texts = self._get_reference_texts(scenario)
        if reference_texts:
            if language in _CJK_LANGUAGES:
                cer_result = self._calculate_cer(reference_texts, agent_text)
                threshold = context.get("cer_threshold", 3.0)
                results.append(MetricResult(
                    name="cer",
                    value=round(cer_result["error_rate"], 2),
                    unit="%",
                    passed=cer_result["error_rate"] <= threshold,
                    threshold=threshold,
                    details={
                        "hits": cer_result["hits"],
                        "substitutions": cer_result["substitutions"],
                        "deletions": cer_result["deletions"],
                        "insertions": cer_result["insertions"],
                        "language": language,
                    },
                ))
            else:
                wer_result = self._calculate_weighted_wer(
                    reference_texts, agent_text, critical_keywords,
                )
                threshold = context.get("wer_threshold", 10.0)
                results.append(MetricResult(
                    name="wer",
                    value=round(wer_result["standard_wer"], 2),
                    unit="%",
                    passed=wer_result["standard_wer"] <= threshold,
                    threshold=threshold,
                    details={
                        "weighted_wer": round(wer_result["weighted_wer"], 2),
                        "hits": wer_result["hits"],
                        "substitutions": wer_result["substitutions"],
                        "deletions": wer_result["deletions"],
                        "insertions": wer_result["insertions"],
                        "critical_misses": wer_result["critical_misses"],
                        "language": language,
                    },
                ))

                # If weighted WER is significantly worse, flag it
                if wer_result["critical_misses"]:
                    results.append(MetricResult(
                        name="critical_word_misses",
                        value=float(len(wer_result["critical_misses"])),
                        unit="count",
                        passed=len(wer_result["critical_misses"]) == 0,
                        threshold=0.0,
                        details={"missed_words": wer_result["critical_misses"]},
                    ))

        return results

    @staticmethod
    def _build_transform() -> Any:
        """Build the jiwer pre-processing pipeline.

        Layer 1: Sanitize text before comparison.
        Eliminates noise errors (casing, punctuation, whitespace)
        that don't reflect real ASR or agent quality issues.
        """
        import jiwer

        return jiwer.Compose([
            jiwer.ToLowerCase(),
            jiwer.ExpandCommonEnglishContractions(),
            jiwer.RemoveWhiteSpace(replace_by_space=True),
            jiwer.RemoveMultipleSpaces(),
            jiwer.Strip(),
            jiwer.RemovePunctuation(),  # type: ignore[no-untyped-call]
            jiwer.RemoveMultipleSpaces(),
            jiwer.Strip(),
            jiwer.ReduceToListOfListOfWords(),
        ])

    @staticmethod
    def _calculate_weighted_wer(
        references: list[str],
        hypothesis: str,
        critical_keywords: set[str],
    ) -> dict[str, Any]:
        """Layer 2+3: Alignment engine + weighted intent scoring.

        Uses jiwer.process_words() for exact alignment, then
        applies heavy penalties for critical keyword misses.
        """
        import jiwer

        transform = WEREvaluator._build_transform()

        best_result: dict[str, Any] | None = None
        best_wer = 100.0

        for ref in references:
            if not ref.strip():
                continue

            output = jiwer.process_words(
                ref,
                hypothesis,
                reference_transform=transform,
                hypothesis_transform=transform,
            )

            if output.wer * 100 < best_wer:
                best_wer = output.wer * 100

                # Layer 3: Compute weighted WER using alignment map
                critical_misses: list[str] = []
                weighted_error_sum = 0.0
                total_ref_words = len(output.references[0]) if output.references else 0

                if total_ref_words > 0 and output.alignments:
                    ref_words = output.references[0]
                    critical_kw_lower = {kw.lower() for kw in critical_keywords}

                    for chunk in output.alignments[0]:
                        if chunk.type == "equal":
                            continue  # No error

                        # Get the reference words involved in this error
                        error_words = ref_words[chunk.ref_start_idx:chunk.ref_end_idx]

                        for word in error_words:
                            if word.lower() in critical_kw_lower:
                                weighted_error_sum += _CRITICAL_WORD_WEIGHT
                                critical_misses.append(word)
                            else:
                                weighted_error_sum += _DEFAULT_WORD_WEIGHT

                        # Insertions have no reference words but still count
                        if chunk.type == "insert":
                            ins_count = chunk.hyp_end_idx - chunk.hyp_start_idx
                            weighted_error_sum += ins_count * _DEFAULT_WORD_WEIGHT

                weighted_wer = (
                    (weighted_error_sum / total_ref_words * 100)
                    if total_ref_words > 0
                    else 0.0
                )

                best_result = {
                    "standard_wer": best_wer,
                    "weighted_wer": weighted_wer,
                    "hits": output.hits,
                    "substitutions": output.substitutions,
                    "deletions": output.deletions,
                    "insertions": output.insertions,
                    "critical_misses": critical_misses,
                }

        if best_result is None:
            return {
                "standard_wer": 100.0,
                "weighted_wer": 100.0,
                "hits": 0,
                "substitutions": 0,
                "deletions": 0,
                "insertions": 0,
                "critical_misses": [],
            }

        return best_result

    @staticmethod
    def _calculate_cer(references: list[str], hypothesis: str) -> dict[str, Any]:
        """Calculate CER for character-based languages using jiwer.process_characters()."""
        import jiwer

        best_cer = 100.0
        best_result: dict[str, Any] | None = None

        for ref in references:
            if not ref.strip():
                continue
            output = jiwer.process_characters(ref, hypothesis)
            if output.cer * 100 < best_cer:
                best_cer = output.cer * 100
                best_result = {
                    "error_rate": best_cer,
                    "hits": output.hits,
                    "substitutions": output.substitutions,
                    "deletions": output.deletions,
                    "insertions": output.insertions,
                }

        return best_result or {
            "error_rate": 100.0,
            "hits": 0,
            "substitutions": 0,
            "deletions": 0,
            "insertions": 0,
        }

    @staticmethod
    def _get_reference_texts(scenario: Scenario) -> list[str]:
        """Extract reference texts for ASR accuracy measurement.

        WER measures transcription fidelity — did the STT correctly
        transcribe what was actually said?  The only valid reference
        is the *caller's* scripted text (we know exactly what the TTS
        synthesized).  Comparing agent expected text vs agent actual
        text conflates behavioral errors (agent said the wrong thing)
        with ASR errors (STT mis-heard what was said), producing a
        metric that is neither valid WER nor a useful quality signal.

        Agent behavioral correctness is already covered by:
        - keyword_presence / keyword_absence (per-turn keyword checks)
        - task_completion evaluator (goal achievement)
        - hallucination evaluator (factual grounding)
        """
        refs: list[str] = []
        for turn in scenario.conversation:
            if turn.role == "caller" and turn.text:
                refs.append(turn.text)
        return refs

    @staticmethod
    def _collect_critical_keywords(scenario: Scenario) -> set[str]:
        """Collect all must_include keywords as critical words for weighted WER."""
        keywords: set[str] = set()
        for turn in scenario.conversation:
            if turn.role == "agent" and turn.expect:
                keywords.update(turn.expect.must_include)
        return keywords

    @staticmethod
    def _check_keywords_per_turn(
        scenario: Scenario,
        transcript: TranscriptResult,
    ) -> list[MetricResult]:
        """Check must_include and must_not_say with per-turn awareness.

        BUG-002 fix: Instead of checking the entire transcript as one blob,
        we check keywords against the transcript segment that best corresponds
        to each expected turn. Falls back to full text if segments unavailable.
        """
        results: list[MetricResult] = []

        # Build per-turn agent text from segments if available
        agent_segments = [
            seg.text.lower() for seg in transcript.segments
            if seg.text
        ] if transcript.segments else []

        full_text_lower = transcript.text.lower()

        agent_turn_idx = 0
        for turn in scenario.conversation:
            if turn.role != "agent" or not turn.expect:
                continue

            # Pick the best text to check against for this turn
            if agent_segments and agent_turn_idx < len(agent_segments):
                check_text = agent_segments[agent_turn_idx]
            else:
                # Fallback: use full transcript (less precise but still works)
                check_text = full_text_lower

            # must_include check
            if turn.expect.must_include:
                missing = [
                    kw for kw in turn.expect.must_include
                    if kw.lower() not in check_text
                ]
                total = len(turn.expect.must_include)
                results.append(MetricResult(
                    name="keyword_presence",
                    value=round((1 - len(missing) / total) * 100, 1),
                    unit="%",
                    passed=len(missing) == 0,
                    threshold=100.0,
                    details={
                        "turn_index": agent_turn_idx,
                        "required": turn.expect.must_include,
                        "missing": missing,
                    },
                ))

            # must_not_say check
            if turn.expect.must_not_say:
                found = [
                    kw for kw in turn.expect.must_not_say
                    if kw.lower() in check_text
                ]
                total = len(turn.expect.must_not_say)
                results.append(MetricResult(
                    name="keyword_absence",
                    value=round((1 - len(found) / total) * 100, 1),
                    unit="%",
                    passed=len(found) == 0,
                    threshold=100.0,
                    details={
                        "turn_index": agent_turn_idx,
                        "forbidden": turn.expect.must_not_say,
                        "found": found,
                    },
                ))

            agent_turn_idx += 1

        return results
