"""decibench serve — run the API server."""

import click
import uvicorn


@click.command("serve")
@click.option("--host", default="127.0.0.1", help="Host address to bind to.")
@click.option("--port", default=8000, help="Port to bind to.")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload for development.")
def serve_cmd(host: str, port: int, reload: bool) -> None:
    """Start the Decibench read-only local API."""
    click.echo(f"Starting Decibench API on http://{host}:{port}")
    uvicorn.run("decibench.api.app:app", host=host, port=port, reload=reload)
