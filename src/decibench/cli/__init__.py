"""Decibench CLI — Click-based command interface.

All commands are thin wrappers around the Orchestrator.
The CLI never contains business logic — only argument parsing and output.
"""

from __future__ import annotations

import click

from decibench import __version__


@click.group()
@click.version_option(version=__version__, prog_name="decibench")
def main() -> None:
    """Decibench — The open standard for voice agent quality.

    Free, transparent, reproducible voice agent testing.
    """
    pass


# Import and register all subcommands
from decibench.cli.compare import compare_cmd  # noqa: E402
from decibench.cli.doctor import doctor_cmd  # noqa: E402
from decibench.cli.evaluate_cmd import evaluate_calls_cmd  # noqa: E402
from decibench.cli.import_cmd import import_cmd  # noqa: E402
from decibench.cli.init_cmd import init_cmd  # noqa: E402
from decibench.cli.replay import replay_cmd  # noqa: E402
from decibench.cli.run import run_cmd  # noqa: E402
from decibench.cli.runs import runs_cmd  # noqa: E402
from decibench.cli.scenario import scenario_cmd  # noqa: E402
from decibench.cli.serve import serve_cmd  # noqa: E402
from decibench.cli.version import version_cmd  # noqa: E402

main.add_command(run_cmd, "run")
main.add_command(compare_cmd, "compare")
main.add_command(doctor_cmd, "doctor")
main.add_command(import_cmd, "import")
main.add_command(init_cmd, "init")
main.add_command(replay_cmd, "replay")
main.add_command(runs_cmd, "runs")
main.add_command(scenario_cmd, "scenario")
main.add_command(serve_cmd, "serve")
main.add_command(version_cmd, "version")
main.add_command(evaluate_calls_cmd, "evaluate-calls")
