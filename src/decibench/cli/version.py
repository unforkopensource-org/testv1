"""decibench version — show version and environment info."""

from __future__ import annotations

import platform
import sys

import click

from decibench import __version__


@click.command("version")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed environment info.")
def version_cmd(verbose: bool) -> None:
    """Show Decibench version and environment information."""
    click.echo(f"decibench {__version__}")

    if verbose:
        click.echo()
        click.echo(f"Python:   {sys.version}")
        click.echo(f"Platform: {platform.platform()}")
        click.echo(f"Arch:     {platform.machine()}")

        # Check optional dependencies
        click.echo()
        click.echo("Providers:")

        for pkg, label in [
            ("edge_tts", "edge-tts (TTS)"),
            ("faster_whisper", "faster-whisper (STT)"),
            ("pystoi", "pystoi (STOI)"),
        ]:
            try:
                mod = __import__(pkg)
                ver = getattr(mod, "__version__", "installed")
                click.echo(f"  {label}: {ver}")
            except ImportError:
                click.echo(f"  {label}: not installed")

        # Check ONNX runtime for DNSMOS
        try:
            import onnxruntime
            click.echo(f"  onnxruntime (DNSMOS): {onnxruntime.__version__}")
        except ImportError:
            click.echo("  onnxruntime (DNSMOS): not installed (heuristic MOS fallback)")
