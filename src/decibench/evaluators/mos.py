"""MOS evaluator — no-reference Mean Opinion Score.

Primary: Microsoft DNSMOS via `speechmos` package (real perceptual quality).
Fallback: Heuristic estimate from signal statistics (clearly labeled).

Install real DNSMOS: pip install decibench[audio-quality]
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from decibench.evaluators.base import BaseEvaluator
from decibench.models import AudioBuffer, CallSummary, MetricResult, Scenario, TranscriptResult

logger = logging.getLogger(__name__)


class MOSEvaluator(BaseEvaluator):
    """No-reference Mean Opinion Score."""

    @property
    def name(self) -> str:
        return "mos"

    @property
    def layer(self) -> str:
        return "statistical"

    @property
    def requires_audio(self) -> bool:
        return True

    async def evaluate(
        self,
        scenario: Scenario,
        summary: CallSummary,
        transcript: TranscriptResult,
        context: dict[str, Any],
    ) -> list[MetricResult]:
        if not summary.agent_audio:
            return [MetricResult(
                name="mos_ovrl",
                value=0.0,
                unit="",
                passed=False,
                details={"reason": "No agent audio to evaluate"},
            )]

        audio = AudioBuffer(data=summary.agent_audio, sample_rate=16000)
        threshold = context.get("mos_threshold", 4.0)

        # Try real DNSMOS first, fall back to heuristic
        scores, method = await self._compute_mos(audio)
        ovrl = float(scores.get("ovrl", 0.0))

        # Use different metric name to be honest about method
        metric_name = "mos_ovrl" if method == "dnsmos" else "audio_quality_estimate"

        results = [
            MetricResult(
                name=metric_name,
                value=round(ovrl, 2),
                unit="/5.0",
                passed=ovrl >= threshold if method == "dnsmos" else True,
                threshold=threshold if method == "dnsmos" else None,
                details={**scores, "method": method},
            ),
        ]

        if method == "dnsmos":
            if "sig" in scores:
                results.append(MetricResult(
                    name="mos_sig", value=round(float(scores["sig"]), 2),
                    unit="/5.0", passed=True,
                ))
            if "bak" in scores:
                results.append(MetricResult(
                    name="mos_bak", value=round(float(scores["bak"]), 2),
                    unit="/5.0", passed=True,
                ))

        return results

    async def _compute_mos(self, audio: AudioBuffer) -> tuple[dict[str, float | str], str]:
        """Try real DNSMOS, fall back to heuristic. Returns (scores, method)."""
        # Attempt 1: speechmos package (best option)
        try:
            from speechmos import dnsmos
            signal = np.frombuffer(audio.data, dtype=np.int16).astype(np.float32) / 32768.0
            if len(signal) < 16000:  # Need at least 1 second
                return self._heuristic(audio), "heuristic"
            result = dnsmos.run(signal, sr=16000)
            return {
                "ovrl": float(result.ovrl_mos),
                "sig": float(result.sig_mos),
                "bak": float(result.bak_mos),
            }, "dnsmos"
        except ImportError:
            pass
        except Exception as e:
            logger.warning("speechmos DNSMOS failed: %s", e)

        # Attempt 2: onnxruntime with manually downloaded models
        try:
            from pathlib import Path

            import onnxruntime as ort
            model_path = Path.home() / ".cache" / "decibench" / "dnsmos" / "sig_bak_ovrl.onnx"
            if model_path.exists():
                session = ort.InferenceSession(str(model_path))
                signal = np.frombuffer(audio.data, dtype=np.int16).astype(np.float32) / 32768.0
                input_name = session.get_inputs()[0].name
                result = session.run(None, {input_name: signal.reshape(1, -1)})
                return {
                    "ovrl": float(result[0][0]),
                    "sig": float(result[1][0]),
                    "bak": float(result[2][0]),
                }, "dnsmos"
        except ImportError:
            pass
        except Exception as e:
            logger.warning("ONNX DNSMOS failed: %s", e)

        # Fallback: heuristic (clearly labeled)
        logger.info(
            "No DNSMOS available. Using heuristic audio quality estimate. "
            "Install real DNSMOS: pip install speechmos"
        )
        return self._heuristic(audio), "heuristic"

    @staticmethod
    def _heuristic(audio: AudioBuffer) -> dict[str, float | str]:
        """Heuristic audio quality estimate from signal statistics.

        NOT a real MOS. Catches: silence, clipping, extreme noise.
        Cannot judge perceptual speech quality.
        """
        signal = np.frombuffer(audio.data, dtype=np.int16).astype(np.float64)

        if len(signal) == 0:
            return {"ovrl": 1.0, "scoring_method": "heuristic", "warning": "empty_audio"}

        rms = np.sqrt(np.mean(signal ** 2))
        if rms < 10:
            return {"ovrl": 1.0, "scoring_method": "heuristic", "warning": "silence"}

        peak = np.max(np.abs(signal))
        crest_factor = peak / rms if rms > 0 else 0

        # Clipping detection
        clip_ratio = np.mean(np.abs(signal) > 32000)

        # Basic estimate — intentionally conservative
        # This is NOT perceptual quality — it's a signal health check
        sig_est = np.clip(2.0 + (crest_factor / 6.0), 1.0, 4.0)  # Cap at 4.0, not 5.0
        if clip_ratio > 0.01:
            sig_est = max(1.5, sig_est - 1.0)  # Clipping penalty

        bak_est = np.clip(3.5 - clip_ratio * 5.0, 1.0, 4.5)
        ovrl_est = sig_est * 0.6 + bak_est * 0.4

        return {
            "ovrl": round(float(np.clip(ovrl_est, 1.0, 4.0)), 2),  # Capped at 4.0 — heuristic can't claim >4
            "scoring_method": "heuristic",
        }
