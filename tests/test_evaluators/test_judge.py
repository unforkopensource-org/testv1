"""Tests for LLM judge infrastructure — parsing, prompts, median consensus."""

from __future__ import annotations

from decibench.providers.judge.openai_compat import JUDGE_SYSTEM_PROMPT, OpenAICompatJudge

# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def test_parse_clean_json():
    """Parse clean JSON response."""
    raw = '{"passed": true, "score": 85.0, "reasoning": "All criteria met."}'
    result = OpenAICompatJudge._parse_response(raw)
    assert result.passed is True
    assert result.score == 85.0
    assert "All criteria met" in result.reasoning


def test_parse_json_in_code_block():
    """Parse JSON embedded in markdown code block."""
    raw = """Here is my evaluation:
```json
{"passed": false, "score": 30.0, "reasoning": "Major gaps."}
```"""
    result = OpenAICompatJudge._parse_response(raw)
    assert result.passed is False
    assert result.score == 30.0


def test_parse_json_with_surrounding_text():
    """Parse JSON with text before/after."""
    raw = """Let me evaluate this.
{"passed": true, "score": 92.0, "reasoning": "Excellent."}
That concludes the evaluation."""
    result = OpenAICompatJudge._parse_response(raw)
    assert result.passed is True
    assert result.score == 92.0


def test_parse_invalid_json():
    """Completely invalid response → score 0, failure."""
    raw = "This is not JSON at all. The agent did well."
    result = OpenAICompatJudge._parse_response(raw)
    assert result.passed is False
    assert result.score == 0.0
    assert "Failed to parse" in result.reasoning


def test_parse_partial_json():
    """JSON with missing fields → defaults to False/0.0."""
    raw = '{"score": 75.0}'
    result = OpenAICompatJudge._parse_response(raw)
    assert result.score == 75.0
    assert result.passed is False  # Default when missing


def test_parse_boolean_strings():
    """Handle score as int, passed as bool."""
    raw = '{"passed": true, "score": 100, "reasoning": "Perfect"}'
    result = OpenAICompatJudge._parse_response(raw)
    assert result.passed is True
    assert result.score == 100.0


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def test_build_prompt_basic():
    """Basic prompt with no context."""
    prompt = OpenAICompatJudge._build_prompt("Evaluate this.", {})
    assert "Evaluate this." in prompt


def test_build_prompt_with_transcript():
    """Transcript context added to prompt."""
    prompt = OpenAICompatJudge._build_prompt("Evaluate.", {
        "transcript": "Hello, how can I help?",
    })
    assert "Hello, how can I help?" in prompt
    assert "Conversation Transcript" in prompt


def test_build_prompt_with_all_context():
    """All context fields added."""
    prompt = OpenAICompatJudge._build_prompt("Evaluate.", {
        "transcript": "text",
        "expected": "goal",
        "tool_calls": [{"name": "book"}],
        "knowledge_base": "facts",
    })
    assert "text" in prompt
    assert "goal" in prompt
    assert "book" in prompt
    assert "facts" in prompt


# ---------------------------------------------------------------------------
# System prompt quality
# ---------------------------------------------------------------------------

def test_system_prompt_has_cot():
    """System prompt must enforce chain-of-thought."""
    assert "IDENTIFY" in JUDGE_SYSTEM_PROMPT
    assert "EVIDENCE" in JUDGE_SYSTEM_PROMPT
    assert "JUDGE" in JUDGE_SYSTEM_PROMPT


def test_system_prompt_has_rubric():
    """System prompt must have scoring rubric."""
    assert "90-100" in JUDGE_SYSTEM_PROMPT
    assert "0-24" in JUDGE_SYSTEM_PROMPT


def test_system_prompt_has_json_format():
    """System prompt must request JSON output."""
    assert '"passed"' in JUDGE_SYSTEM_PROMPT
    assert '"score"' in JUDGE_SYSTEM_PROMPT
    assert '"reasoning"' in JUDGE_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Judge initialization
# ---------------------------------------------------------------------------

def test_judge_default_url():
    """Default base URL is OpenAI API."""
    judge = OpenAICompatJudge()
    assert "api.openai.com" in judge._base_url


def test_judge_custom_url():
    """Custom URL is preserved."""
    judge = OpenAICompatJudge(config_str="http://localhost:11434/v1")
    assert "localhost:11434" in judge._base_url


def test_judge_runs_default():
    """Default judge_runs is 1 (single-shot)."""
    judge = OpenAICompatJudge()
    assert judge._judge_runs == 1


def test_judge_runs_configured():
    """judge_runs can be set via kwargs."""
    judge = OpenAICompatJudge(judge_runs=3)
    assert judge._judge_runs == 3
