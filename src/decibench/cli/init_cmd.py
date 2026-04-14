"""decibench init — create a decibench.toml with sensible defaults."""

from __future__ import annotations

from pathlib import Path

import click

_DEFAULT_CONFIG = '''[project]
name = "my-voice-agent"

[target]
default = "demo"
# Examples:
#   default = "ws://localhost:8000/ws"      # WebSocket agent
#   default = "exec:python my_agent.py"     # Local process
#   default = "demo"                        # Built-in demo (no setup needed)

[auth]
# All auth via environment variables — never commit keys
# vapi_api_key = "${VAPI_API_KEY}"
# retell_api_key = "${RETELL_API_KEY}"

[providers]
tts = "edge-tts"
tts_voice = "en-US-JennyNeural"
stt = "faster-whisper:base"

# LLM Judge — enables semantic evaluation (task completion, hallucination detection)
# Without a judge, only deterministic metrics are scored (latency, audio, compliance)
# BYOK: bring your own key. Cost: ~$0.02-0.05 per suite run with gpt-4o-mini
judge = "none"
# Uncomment ONE of these:
# judge = "openai-compat"                         # Uses OPENAI_API_KEY env var
# judge = "openai-compat://localhost:11434/v1"     # Ollama (free, local)
# judge = "openai-compat://api.groq.com/openai/v1" # Groq (fast, free tier)
# judge_model = "gpt-4o-mini"                      # Or: llama3.2, gemma2, etc.
# judge_api_key = ""                               # Or set OPENAI_API_KEY env var

[audio]
sample_rate = 16000
noise_profiles_dir = "./noise_profiles"

[evaluation]
runs_per_scenario = 1
judge_temperature = 0.0
timeout_seconds = 120

[scoring.weights]
task_completion = 0.25
latency = 0.20
audio_quality = 0.15
conversation = 0.15
robustness = 0.10
interruption = 0.10
compliance = 0.05

[ci]
min_score = 80
max_p95_latency_ms = 1500
fail_on_compliance_violation = true

[profiles.dev]
suite = "quick"
runs_per_scenario = 1

[profiles.ci]
suite = "standard"
runs_per_scenario = 3
min_score = 80

[profiles.benchmark]
suite = "full"  # quick + standard + acoustic + adversarial
runs_per_scenario = 5
'''


@click.command("init")
@click.option(
    "--force", "-f",
    is_flag=True,
    default=False,
    help="Overwrite existing decibench.toml.",
)
def init_cmd(force: bool) -> None:
    """Create a decibench.toml configuration file."""
    config_path = Path.cwd() / "decibench.toml"

    if config_path.exists() and not force:
        click.echo("decibench.toml already exists. Use --force to overwrite.")
        raise SystemExit(1)

    config_path.write_text(_DEFAULT_CONFIG)
    click.echo(f"Created {config_path}")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. decibench run --target demo              # Try the demo (no setup)")
    click.echo("  2. Edit decibench.toml with your agent URI")
    click.echo("  3. decibench run --suite quick              # Test your agent")
    click.echo()
    click.echo("Enable LLM judge for semantic eval (optional):")
    click.echo("  export OPENAI_API_KEY=sk-...")
    click.echo("  Set judge = \"openai-compat\" in decibench.toml")
    click.echo("  Set judge_model = \"gpt-4o-mini\"    # ~$0.03/run")
