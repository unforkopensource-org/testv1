"""CI/CD reporter — GitHub Actions annotations and exit codes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decibench.models import SuiteResult


class CIReporter:
    """Annotate CI/CD builds with test results."""

    @staticmethod
    def report(result: SuiteResult, min_score: float = 0.0) -> bool:
        """Output GitHub Actions annotations and determine pass/fail.

        Returns:
            True if the suite passes the minimum score threshold.
        """
        passed = result.decibench_score >= min_score

        # GitHub Actions annotations
        if _is_github_actions():
            if passed:
                print(
                    f"::notice title=Decibench::Score {result.decibench_score}/100 "
                    f"({result.passed}/{result.total_scenarios} passed)"
                )
            else:
                print(
                    f"::error title=Decibench Quality Gate Failed::"
                    f"Score {result.decibench_score}/100 < {min_score} minimum "
                    f"({result.failed} scenarios failed)"
                )

            # Annotate individual failures
            for r in result.results:
                if not r.passed:
                    failures_str = "; ".join(r.failures[:3])
                    print(
                        f"::warning title=Failed: {r.scenario_id}::{failures_str}"
                    )

        # Summary for any CI system
        print(
            f"Decibench Score: {result.decibench_score}/100 | "
            f"Pass: {result.passed}/{result.total_scenarios} | "
            f"Duration: {result.duration_seconds:.1f}s"
        )

        return passed

    @staticmethod
    def exit_code(passed: bool) -> int:
        """Return appropriate exit code for CI."""
        return 0 if passed else 1


def _is_github_actions() -> bool:
    """Detect if running in GitHub Actions."""
    import os
    return os.environ.get("GITHUB_ACTIONS") == "true"
