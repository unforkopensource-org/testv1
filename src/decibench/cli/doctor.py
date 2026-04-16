"""decibench doctor — local environment and project health checks."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import click

from decibench import __version__
from decibench.config import find_config, load_config
from decibench.llm_catalog import get_provider_catalog, judge_provider_from_uri
from decibench.secrets import describe_secret, keyring_available
from decibench.store import default_store_path


@click.command("doctor")
def doctor_cmd() -> None:
    """Check the local Decibench environment."""
    click.echo(f"Decibench {__version__}")
    click.echo(f"Store path: {default_store_path()}")
    click.echo()

    checks: list[tuple[str, str, str]] = [
        ("PASS", "Python", _python_version()),
        ("PASS" if keyring_available() else "WARN", "Keyring", _keyring_detail()),
        ("PASS" if shutil.which("node") else "WARN", "Node.js", _command_detail("node")),
        ("PASS" if shutil.which("npm") else "WARN", "npm", _command_detail("npm")),
        (
            "PASS" if importlib.util.find_spec("uvicorn") else "WARN",
            "Workbench server",
            _package_detail("uvicorn"),
        ),
    ]

    config_path = find_config()
    if config_path is None:
        checks.append(
            (
                "WARN",
                "Project config",
                "No decibench.toml found. Run: decibench init",
            )
        )
    else:
        checks.append(("PASS", "Project config", str(config_path)))
        try:
            config = load_config(config_path)
        except Exception as exc:  # pragma: no cover - defensive
            checks.append(("FAIL", "Config parse", str(exc)))
        else:
            checks.extend(_config_checks(config, config_path))

    for status, label, detail in checks:
        click.echo(f"{status:<4} {label:<18} {detail}")


def _python_version() -> str:
    import platform

    return platform.python_version()


def _keyring_detail() -> str:
    if keyring_available():
        return "Available for local secret storage"
    return "Unavailable; use environment variables until keyring is installed"


def _command_detail(command: str) -> str:
    path = shutil.which(command)
    return path or "Not found on PATH (needed for some local workflows)"


def _package_detail(package: str) -> str:
    if importlib.util.find_spec(package):
        return "Installed"
    return "Not installed (install the server extra for the local workbench)"


def _config_checks(config: object, config_path: Path) -> list[tuple[str, str, str]]:
    from decibench.config import DecibenchConfig

    typed_config = config if isinstance(config, DecibenchConfig) else load_config(config_path)
    checks: list[tuple[str, str, str]] = [
        ("PASS", "Target", typed_config.target.default),
        (
            "PASS" if _package_installed("edge_tts") else "WARN",
            "TTS provider",
            f"{typed_config.providers.tts} ({_package_hint('edge_tts')})",
        ),
        (
            "PASS" if _package_installed("faster_whisper") else "WARN",
            "STT provider",
            f"{typed_config.providers.stt} ({_package_hint('faster_whisper')})",
        ),
    ]

    judge_provider = judge_provider_from_uri(typed_config.providers.judge)
    if judge_provider is None:
        checks.append(
            ("PASS", "Semantic judge", "Deterministic-only mode")
        )
    else:
        secret_state = describe_secret(judge_provider)
        catalog = get_provider_catalog(judge_provider)
        status = "PASS" if typed_config.providers.judge_api_key else "FAIL"
        detail = (
            f"{catalog.display_name} / {typed_config.providers.judge_model or 'no model set'} "
            f"(key source: {secret_state.source}; fix: decibench auth set {judge_provider})"
        )
        checks.append((status, "Semantic judge", detail))

    if typed_config.target.default.startswith(("retell://", "vapi://")):
        bridge_status = "PASS" if shutil.which("decibench-bridge") else "WARN"
        bridge_detail = shutil.which("decibench-bridge") or (
            "Bridge binary not found. Run: decibench bridge install"
        )
        checks.append((bridge_status, "Native bridge", bridge_detail))

    static_index = Path(__file__).resolve().parents[1] / "api" / "static" / "index.html"
    checks.append(
        (
            "PASS" if static_index.exists() else "WARN",
            "Workbench assets",
            str(static_index) if static_index.exists() else "Workbench HTML asset missing",
        )
    )
    return checks


def _package_installed(package: str) -> bool:
    return importlib.util.find_spec(package) is not None


def _package_hint(package: str) -> str:
    return "installed" if _package_installed(package) else f"{package} not installed"
