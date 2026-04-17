"""decibench bridge — manage the native browser-side bridge helper."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click

# Walk up from this file to the repo root to detect a source checkout.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_LOCAL_SIDECAR_DIR = _REPO_ROOT / "bridge_sidecar"


def _has_local_sidecar() -> bool:
    """Return True when running from a repo checkout that contains the sidecar source."""
    return (_LOCAL_SIDECAR_DIR / "package.json").is_file()


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
    """Install the Decibench bridge sidecar and Chromium runtime.

    When running from a source checkout that contains ``bridge_sidecar/``,
    the sidecar is built locally instead of installing from npm.
    """
    missing = [name for name in ("node", "npm", "npx") if shutil.which(name) is None]
    if missing:
        missing_text = ", ".join(missing)
        raise click.ClickException(
            f"Missing required tools: {missing_text}. Install Node.js first."
        )

    if _has_local_sidecar():
        click.echo(f"Detected local sidecar source at {_LOCAL_SIDECAR_DIR}")
        commands: list[tuple[list[str], Path | None]] = [
            (["npm", "install"], _LOCAL_SIDECAR_DIR),
            (["npm", "run", "build"], _LOCAL_SIDECAR_DIR),
            (["npx", "playwright", "install", "chromium"], None),
        ]
    else:
        commands = [
            (["npm", "install", "-g", "decibench-bridge"], None),
            (["npx", "playwright", "install", "chromium"], None),
        ]

    for command, cwd in commands:
        label = f"(in {cwd}) " if cwd else ""
        click.echo(f"$ {label}{' '.join(command)}")
        if dry_run:
            continue
        subprocess.run(command, check=True, cwd=cwd, timeout=300)

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
        try:
            result = subprocess.run(
                ["npx", "playwright", "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if result.returncode == 0:
                click.echo(f"PASS playwright         {result.stdout.strip()}")
            else:
                click.echo("WARN playwright         Chromium runtime not verified")
        except subprocess.TimeoutExpired:
            click.echo("WARN playwright         check timed out (15s) — npx may be installing deps")


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
