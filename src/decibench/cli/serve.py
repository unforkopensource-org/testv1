"""decibench serve — run the API server."""

from pathlib import Path

import click
import uvicorn


@click.command("serve")
@click.option("--host", default="127.0.0.1", help="Host address to bind to.")
@click.option("--port", default=8000, help="Port to bind to.")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload for development.")
def serve_cmd(host: str, port: int, reload: bool) -> None:
    """Start the local Decibench workbench."""
    static_index = Path(__file__).resolve().parents[1] / "api" / "static" / "index.html"
    if not static_index.exists():
        raise click.ClickException(
            "Workbench assets are missing. Reinstall Decibench or rebuild the dashboard before serving."
        )

    click.echo("Decibench workbench is running locally.")
    click.echo(f"URL: http://{host}:{port}")
    click.echo("Use Ctrl+C to stop it.")
    uvicorn.run("decibench.api.app:app", host=host, port=port, reload=reload)
