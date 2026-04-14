"""decibench doctor — local environment and project health checks."""

from __future__ import annotations

from pathlib import Path

import click

from decibench import __version__
from decibench.store import default_store_path


@click.command("doctor")
def doctor_cmd() -> None:
    """Check the local Decibench environment."""
    click.echo(f"Decibench: {__version__}")
    click.echo(f"Store:     {default_store_path()}")
    click.echo(f"Python:    {_python_version()}")

    for path in (Path("decibench.toml"), Path("README.md")):
        status = "ok" if path.exists() else "missing"
        click.echo(f"{path}: {status}")

    for pkg, label in [
        ("edge_tts", "edge-tts"),
        ("faster_whisper", "faster-whisper"),
        ("onnxruntime", "onnxruntime"),
    ]:
        try:
            __import__(pkg)
            status = "installed"
        except ImportError:
            status = "not installed"
        click.echo(f"{label}: {status}")


def _python_version() -> str:
    import platform

    return platform.python_version()
