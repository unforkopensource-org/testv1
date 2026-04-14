"""decibench scenario — list, validate, and manage test scenarios."""

from __future__ import annotations

from pathlib import Path

import click

from decibench.scenarios.loader import ScenarioLoader


@click.group("scenario")
def scenario_cmd() -> None:
    """Manage test scenarios."""
    pass


@scenario_cmd.command("list")
@click.option("--suite", "-s", default=None, help="List scenarios in a specific suite.")
def list_cmd(suite: str | None) -> None:
    """List available suites and scenarios."""
    loader = ScenarioLoader()

    if suite:
        scenarios = loader.load_suite(suite)
        click.echo(f"Suite: {suite} ({len(scenarios)} scenarios)")
        click.echo()
        for s in scenarios:
            tags = f" [{', '.join(s.tags)}]" if s.tags else ""
            click.echo(f"  {s.id}: {s.description}{tags}")
    else:
        click.echo("Available suites:")
        click.echo()
        suite_info = [
            ("quick", "~1 min", "Fast feedback during development"),
            ("standard", "~5 min", "Pre-deploy CI/CD gate"),
            ("full", "~10 min", "Comprehensive benchmark (quick + standard + acoustic + adversarial)"),
        ]
        for name, time_est, desc in suite_info:
            count = len(loader.load_suite(name))
            click.echo(f"  {name:12s} {count:3d} scenarios  {time_est:8s}  {desc}")
        click.echo()
        click.echo("Run: decibench scenario list --suite <name>")


@scenario_cmd.command("validate")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def validate_cmd(path: Path) -> None:
    """Validate a YAML scenario file."""
    loader = ScenarioLoader()

    files = sorted(path.glob("*.yaml")) if path.is_dir() else [path]

    total_issues = 0
    for file in files:
        try:
            scenario = loader.load_file(file)
            issues = loader.validate(scenario)
            if issues:
                click.echo(f"[WARN] {file.name}:")
                for issue in issues:
                    click.echo(f"  - {issue}")
                total_issues += len(issues)
            else:
                click.echo(f"[OK]   {file.name}: {scenario.id}")
        except Exception as e:
            click.echo(f"[FAIL] {file.name}: {e}")
            total_issues += 1

    click.echo()
    if total_issues == 0:
        click.echo(f"All {len(files)} scenario(s) valid.")
    else:
        click.echo(f"{total_issues} issue(s) found across {len(files)} file(s).")


@scenario_cmd.command("schema")
def schema_cmd() -> None:
    """Print the JSON Schema for Decibench scenario YAML."""
    import json

    from decibench.models import Scenario

    schema = Scenario.model_json_schema()
    # Pydantic generates draft-07 by default under $schema usually, but to be sure:
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    click.echo(json.dumps(schema, indent=2))
