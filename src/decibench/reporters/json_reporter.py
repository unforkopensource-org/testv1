"""JSON reporter — machine-readable output. Pipe into anything."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from decibench.models import SuiteResult


class JSONReporter:
    """Export results as JSON for programmatic consumption."""

    @staticmethod
    def report(result: SuiteResult, output_path: Path | None = None) -> str:
        """Generate JSON report.

        Args:
            result: Suite result to report
            output_path: Optional file path to write to

        Returns:
            JSON string
        """
        data = result.model_dump(mode="json")

        # Remove raw audio bytes from JSON (too large, not useful in text)
        for scenario_result in data.get("results", []):
            for metric in scenario_result.get("metrics", {}).values():
                if isinstance(metric, dict):
                    metric.pop("audio", None)

        json_str = json.dumps(data, indent=2, default=str)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json_str)

        return json_str
