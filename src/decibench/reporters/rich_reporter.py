"""Rich terminal reporter — screenshot-worthy output.

Designed to produce output that developers want to share.
Every table, every color, every alignment is intentional.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from decibench.models import EvalResult, SuiteResult


class RichReporter:
    """Beautiful terminal output via Rich."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def report_suite(self, result: SuiteResult) -> None:
        """Print full suite results to terminal."""
        self._console.print()

        # Header
        header = Text()
        header.append(" Decibench v0.1.0", style="bold white")
        header.append(" — Voice Agent Quality Score", style="dim")
        self._console.print(Panel(header, border_style="bright_blue"))

        # Summary info
        info_table = Table(show_header=False, box=None, padding=(0, 2))
        info_table.add_column("Key", style="dim")
        info_table.add_column("Value", style="bold")
        info_table.add_row("Target", result.target)
        info_table.add_row("Suite", f"{result.suite} ({result.total_scenarios} scenarios)")
        info_table.add_row("Duration", f"{result.duration_seconds:.1f}s")
        self._console.print(info_table)
        self._console.print()

        # Score panel
        score = result.decibench_score
        score_style = self._score_style(score)
        score_text = Text(f"DECIBENCH SCORE: {score}/100", style=f"bold {score_style}")
        self._console.print(Panel(
            score_text,
            border_style=score_style,
            title="Quality Score",
            title_align="left",
        ))
        self._console.print()

        # Score breakdown by category
        if result.score_breakdown:
            breakdown_table = Table(
                title="Score Breakdown (why this score)",
                title_style="bold",
                border_style="bright_blue",
                show_lines=True,
            )
            breakdown_table.add_column("Category", style="bold", min_width=18)
            breakdown_table.add_column("Score", justify="right", min_width=8)
            breakdown_table.add_column("Weight", justify="right", min_width=8)
            breakdown_table.add_column("Bar", min_width=20)

            weight_map = {
                "task_completion": ("Task Completion", "25%"),
                "latency": ("Latency", "20%"),
                "audio_quality": ("Audio Quality", "15%"),
                "conversation": ("Conversation", "15%"),
                "robustness": ("Robustness", "10%"),
                "interruption": ("Interruption", "10%"),
                "compliance": ("Compliance", "5%"),
            }
            for key, (name, weight) in weight_map.items():
                val = result.score_breakdown.get(key, 50.0)
                bar_len = int(val / 5)  # 0-20 chars
                style = self._score_style(val)
                bar = f"[{style}]{'█' * bar_len}{'░' * (20 - bar_len)}[/{style}]"
                breakdown_table.add_row(name, f"{val:.0f}", weight, bar)

            self._console.print(breakdown_table)

            # Judge status
            judge_str = (
                result.judge_model
                if result.judge_model and result.judge_model != "none"
                else "[dim]not configured (deterministic only)[/dim]"
            )
            self._console.print(f"  LLM Judge: {judge_str}")
            self._console.print()

        # Metrics table
        metrics_table = Table(
            title="Metric Summary",
            title_style="bold",
            border_style="bright_blue",
            show_lines=True,
        )
        metrics_table.add_column("Metric", style="bold", min_width=22)
        metrics_table.add_column("Value", justify="right", min_width=10)
        metrics_table.add_column("Status", justify="center", min_width=8)

        # Aggregate key metrics across all scenarios
        key_metrics = self._aggregate_key_metrics(result.results)
        for name, value, unit, passed in key_metrics:
            status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
            metrics_table.add_row(name, f"{value}{unit}", status)

        self._console.print(metrics_table)
        self._console.print()

        # Pass/fail summary
        pass_pct = (result.passed / result.total_scenarios * 100) if result.total_scenarios > 0 else 0
        summary = Text()
        pass_style = "bold green" if pass_pct >= 80 else "bold red"
        summary.append(
            f" {result.passed}/{result.total_scenarios} scenarios passed",
            style=pass_style,
        )
        summary.append(f" ({pass_pct:.0f}%)", style="dim")
        self._console.print(summary)

        # Failed scenarios
        failed_results = [r for r in result.results if not r.passed]
        if failed_results:
            self._console.print()
            self._console.print("[bold red]Failed Scenarios:[/bold red]")
            for r in failed_results[:10]:  # Show top 10 failures
                self._console.print(f"  [red]x[/red] {r.scenario_id}")
                for failure in r.failures[:3]:
                    self._console.print(f"    [dim]{failure}[/dim]")

        self._console.print()

    def report_compare(
        self,
        result_a: SuiteResult,
        result_b: SuiteResult,
        name_a: str = "A",
        name_b: str = "B",
    ) -> None:
        """Print side-by-side comparison — the viral mechanic."""
        self._console.print()

        header = Text()
        header.append(" DECIBENCH COMPARE", style="bold white")
        header.append(f" — {name_a} vs {name_b}", style="dim")
        self._console.print(Panel(header, border_style="bright_blue"))

        # Build comparison table
        table = Table(
            border_style="bright_blue",
            show_lines=True,
            title=f"Suite: {result_a.suite} ({result_a.total_scenarios} scenarios)",
            title_style="dim",
        )
        table.add_column("Metric", style="bold", min_width=22)
        table.add_column(self._shorten(name_a), justify="right", min_width=12)
        table.add_column(self._shorten(name_b), justify="right", min_width=12)
        table.add_column("Winner", justify="center", min_width=8)

        # Score row
        winner = self._winner_label(
            result_a.decibench_score, result_b.decibench_score,
            higher_better=True, name_a=name_a, name_b=name_b,
        )
        table.add_row(
            "Decibench Score",
            f"{result_a.decibench_score}",
            f"{result_b.decibench_score}",
            winner,
        )

        # Latency rows (lower is better)
        for key, label in [("p50_ms", "Latency P50"), ("p95_ms", "Latency P95"), ("p99_ms", "Latency P99")]:
            a_val = result_a.latency.get(key, 0)
            b_val = result_b.latency.get(key, 0)
            table.add_row(
                label,
                f"{a_val:.0f}ms",
                f"{b_val:.0f}ms",
                self._winner_label(a_val, b_val, higher_better=False, name_a=name_a, name_b=name_b),
            )

        # Metric comparisons
        a_metrics = self._aggregate_key_metrics(result_a.results)
        b_metrics = self._aggregate_key_metrics(result_b.results)
        b_metrics_dict = {name: (val, unit, passed) for name, val, unit, passed in b_metrics}

        for name, a_val, unit, _a_passed in a_metrics:
            if name in b_metrics_dict:
                b_val, b_unit, _b_passed = b_metrics_dict[name]
                lower_metrics = ("WER", "CER", "Hallucination Rate", "Silence %", "PII Violations")
                higher_better = name not in lower_metrics
                table.add_row(
                    name,
                    f"{a_val}{unit}",
                    f"{b_val}{b_unit}",
                    self._winner_label(
                        a_val, b_val, higher_better=higher_better,
                        name_a=name_a, name_b=name_b,
                    ),
                )

        self._console.print(table)
        self._console.print()

        # Verdict
        sum(1 for r in table.rows if "A" in str(r))
        sum(1 for r in table.rows if "B" in str(r))
        if result_a.decibench_score > result_b.decibench_score:
            verdict = (
                f"[bold green]{name_a}[/bold green] wins with score "
                f"{result_a.decibench_score} vs {result_b.decibench_score}"
            )
        elif result_b.decibench_score > result_a.decibench_score:
            verdict = (
                f"[bold green]{name_b}[/bold green] wins with score "
                f"{result_b.decibench_score} vs {result_a.decibench_score}"
            )
        else:
            verdict = "Tie — scores are equal"
        self._console.print(f" Verdict: {verdict}")
        self._console.print()

    @staticmethod
    def _aggregate_key_metrics(results: list[EvalResult]) -> list[tuple[str, float, str, bool]]:
        """Aggregate key metrics across scenarios for display."""
        metric_sums: dict[str, list[float]] = {}
        metric_units: dict[str, str] = {}
        metric_passed: dict[str, list[bool]] = {}

        display_order = [
            "turn_latency_p50_ms", "turn_latency_p95_ms",
            "wer", "mos_ovrl", "task_completion",
            "pii_violations", "ai_disclosure", "silence_pct",
        ]

        display_names = {
            "turn_latency_p50_ms": "Latency P50",
            "turn_latency_p95_ms": "Latency P95",
            "wer": "WER",
            "cer": "CER",
            "mos_ovrl": "Audio Quality (MOS)",
            "task_completion": "Task Completion",
            "tool_call_correctness": "Tool Accuracy",
            "pii_violations": "PII Violations",
            "ai_disclosure": "AI Disclosure",
            "compliance_score": "Compliance",
            "silence_pct": "Silence %",
            "hallucination_rate": "Hallucination Rate",
        }

        for result in results:
            for name, metric in result.metrics.items():
                if name not in metric_sums:
                    metric_sums[name] = []
                    metric_units[name] = metric.unit
                    metric_passed[name] = []
                metric_sums[name].append(metric.value)
                metric_passed[name].append(metric.passed)

        output: list[tuple[str, float, str, bool]] = []
        for key in display_order:
            if key in metric_sums:
                avg = sum(metric_sums[key]) / len(metric_sums[key])
                unit = metric_units.get(key, "")
                if unit and not unit.startswith("/") and not unit.startswith("%"):
                    unit = f" {unit}"
                passed = all(metric_passed[key])
                display_name = display_names.get(key, key)
                output.append((display_name, round(avg, 1), unit, passed))

        return output

    @staticmethod
    def _score_style(score: float) -> str:
        if score >= 90:
            return "green"
        if score >= 70:
            return "yellow"
        return "red"

    @staticmethod
    def _winner_label(
        a: float,
        b: float,
        higher_better: bool,
        name_a: str = "A",
        name_b: str = "B",
    ) -> str:
        if abs(a - b) < 0.01:
            return "[dim]Tie[/dim]"
        if higher_better:
            return f"[green]{name_a} ->[/green]" if a > b else f"[green]<- {name_b}[/green]"
        return f"[green]{name_a} ->[/green]" if a < b else f"[green]<- {name_b}[/green]"

    @staticmethod
    def _shorten(uri: str) -> str:
        """Shorten a target URI for column headers."""
        if len(uri) <= 20:
            return uri
        if "://" in uri:
            scheme, rest = uri.split("://", 1)
            return f"{scheme}://...{rest[-12:]}"
        return uri[:20]
