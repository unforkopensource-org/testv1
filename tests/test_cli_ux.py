"""Tests for local-product CLI flows."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from decibench.cli import main


def test_init_noninteractive_semantic_config() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            main,
            [
                "init",
                "--no-prompt",
                "--name",
                "acme-agent",
                "--target",
                "demo",
                "--provider",
                "gemini",
                "--model",
                "gemini-2.5-flash",
            ],
        )

        assert result.exit_code == 0, result.output
        config_text = Path("decibench.toml").read_text(encoding="utf-8")
        assert 'name = "acme-agent"' in config_text
        assert 'judge = "gemini"' in config_text
        assert 'judge_model = "gemini-2.5-flash"' in config_text


def test_models_preset_updates_config() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("decibench.toml").write_text(
            "[project]\nname = \"demo\"\n\n[target]\ndefault = \"demo\"\n",
            encoding="utf-8",
        )
        result = runner.invoke(main, ["models", "preset", "openai", "balanced"])

        assert result.exit_code == 0, result.output
        config_text = Path("decibench.toml").read_text(encoding="utf-8")
        assert 'judge = "openai-compat"' in config_text
        assert 'judge_model = "gpt-5-mini"' in config_text


def test_auth_list_reports_missing_by_default() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["auth", "list"])

    assert result.exit_code == 0, result.output
    assert "openai" in result.output
    assert "missing" in result.output


def test_doctor_without_config_points_to_init() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["doctor"])

        assert result.exit_code == 0, result.output
        assert "Project config" in result.output
        assert "decibench init" in result.output


def test_bridge_help_is_available() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["bridge", "--help"])

    assert result.exit_code == 0, result.output
    assert "install" in result.output
    assert "doctor" in result.output
