"""decibench bridge — manage the native browser-side bridge helper."""

from __future__ import annotations

import shutil
import subprocess

import click


@click.group("bridge")
def bridge_cmd() -> None:
    """Install and inspect the local native bridge."""


@bridge_cmd.command("install")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the commands that would run without executing them.",
)
def bridge_install_cmd(dry_run: bool) -> None:
    """Install the Decibench bridge sidecar and Chromium runtime."""
    missing = [name for name in ("node", "npm", "npx") if shutil.which(name) is None]
    if missing:
        missing_text = ", ".join(missing)
        raise click.ClickException(
            f"Missing required tools: {missing_text}. Install Node.js first."
        )

    commands = [
        ["npm", "install", "-g", "decibench-bridge"],
        ["npx", "playwright", "install", "chromium"],
    ]
    for command in commands:
        click.echo(f"$ {' '.join(command)}")
        if dry_run:
            continue
        subprocess.run(command, check=True)

    click.echo("Bridge install complete.")
    click.echo("Validate it with: decibench bridge doctor")


@bridge_cmd.command("doctor")
def bridge_doctor_cmd() -> None:
    """Check whether the native bridge prerequisites are available."""
    for command in ("node", "npm", "npx", "decibench-bridge"):
        path = shutil.which(command)
        status = "PASS" if path else "WARN"
        detail = path or f"{command} not found on PATH"
        click.echo(f"{status:<4} {command:<18} {detail}")

    if shutil.which("npx") is not None:
        result = subprocess.run(
            ["npx", "playwright", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            click.echo(f"PASS playwright         {result.stdout.strip()}")
        else:
            click.echo("WARN playwright         Chromium runtime not verified")


@bridge_cmd.command("version")
def bridge_version_cmd() -> None:
    """Print the installed bridge version if available."""
    if shutil.which("decibench-bridge") is None:
        raise click.ClickException(
            "decibench-bridge is not installed. Run: decibench bridge install"
        )

    result = subprocess.run(
        ["decibench-bridge", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise click.ClickException(result.stderr.strip() or "Failed to read bridge version.")
    click.echo(result.stdout.strip())
