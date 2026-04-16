# Decibench

Local-first voice agent testing with a CLI you can actually live with.

**Version:** `1.0.0`  
**License:** Apache-2.0  
**Python:** 3.11+  
**Status:** v1.0 local product push

Decibench helps you test, replay, and analyze voice agents from your own
machine. It is:

- local-first
- terminal-first
- open-source
- self-hostable
- optional-LLM, not LLM-required

It is not a hosted SaaS, and it does not ask users to log into model vendors
through Decibench.

## What Decibench does today

Decibench can:

- run benchmark suites against a demo agent, a WebSocket agent, a local process,
  or an HTTP endpoint
- import calls from JSONL, Vapi, and Retell exports
- evaluate imported calls
- replay failures into regression scenarios
- store results locally
- launch a local workbench for run and failure analysis
- use OpenAI, Anthropic, or Gemini as semantic judges when you want LLM-based
  evaluation

Native Retell and Vapi bridge flows exist and are still best treated as
bridge-backed local integrations, not magic zero-dependency paths.

The detailed shipped/beta/experimental matrix lives in
[docs/support-matrix.yaml](./docs/support-matrix.yaml).

## Install

### Recommended

```bash
pipx install decibench
```

### From GitHub while the package is still moving fast

```bash
pipx install git+https://github.com/unforkopensource-org/testv1.git
```

If you prefer a project virtualenv:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## First run: zero keys, zero cost

You can start in deterministic mode with no model account at all.

```bash
decibench doctor
decibench init
decibench run --target demo --suite quick
decibench serve
```

That path gives you:

- local setup verification
- a generated `decibench.toml`
- a real suite run against the built-in demo target
- a local workbench at `http://127.0.0.1:8000`

## Semantic evaluation with OpenAI, Claude, or Gemini

Decibench supports three first-class semantic judge providers right now:

- OpenAI
- Anthropic
- Gemini

The local UX is the same for all three:

1. store a key locally
2. choose a model
3. run a suite

### OpenAI

```bash
decibench auth set openai
decibench models preset openai balanced
decibench run --target demo --suite quick
```

Default balanced model:

- `gpt-5-mini`

### Anthropic

```bash
decibench auth set anthropic
decibench models preset anthropic balanced
decibench run --target demo --suite quick
```

Default balanced model:

- `claude-sonnet-4-20250514`

### Gemini

```bash
decibench auth set gemini
decibench models preset gemini balanced
decibench run --target demo --suite quick
```

Default balanced model:

- `gemini-2.5-flash`

Important note:

- Decibench does **not** use Gemini 2.0 as the default.
- Gemini 2.5 Flash is the shipped recommendation for broad availability and
  price/performance.

## How keys are handled

Decibench is designed so users can paste keys locally without building a cloud
account layer around the product.

Default secret flow:

- `decibench auth set <provider>`
- key is stored in the local OS keyring when available
- environment variables still work as a fallback
- `decibench.toml` stores config, not secrets, by default

Useful commands:

```bash
decibench auth set openai
decibench auth list
decibench auth test openai
decibench auth remove openai
```

## Model selection

Decibench ships curated presets and also supports live model listing.

```bash
decibench models list openai
decibench models list anthropic
decibench models list gemini

decibench models preset openai balanced
decibench models preset anthropic quality
decibench models use gemini gemini-2.5-pro
decibench models current
```

Preset meanings:

- `balanced`: best default for normal evaluation work
- `quality`: strongest recommended model
- `budget`: cheapest reasonable model

## Local project setup

`decibench init` is the main onboarding command.

It helps you choose:

- project name
- target type
- deterministic vs semantic evaluation
- provider
- model
- optional key setup

Example targets:

```bash
decibench run --target demo --suite quick
decibench run --target ws://localhost:8080/ws --suite quick
decibench run --target 'exec:python my_agent.py' --suite quick
decibench run --target http://localhost:8080/invoke --suite quick
```

## Local workbench

Decibench includes a local workbench backed by the local API.

```bash
decibench serve
```

The server stays local. It does not publish your runs anywhere.

Use the workbench to inspect:

- runs
- imported calls
- evaluations
- timelines
- regressions generated from real failures

## Native bridge workflow

For native Retell or Vapi browser-SDK flows, Decibench uses a local sidecar
bridge instead of pretending those platforms are a pure Python socket problem.

Typical flow:

```bash
decibench bridge install
decibench doctor
decibench run --target retell://your_agent_id --suite quick
```

This is still a local workflow. The bridge exists to handle vendor SDK realities
cleanly.

## Command overview

```bash
decibench init
decibench doctor
decibench auth
decibench models
decibench run
decibench compare
decibench import
decibench evaluate-calls
decibench replay
decibench runs
decibench scenario
decibench serve
decibench version
```

## Minimal config

`decibench init` generates a project config, but the important pieces look like
this:

```toml
[project]
name = "my-voice-agent"

[target]
default = "demo"

[providers]
tts = "edge-tts"
stt = "faster-whisper:base"
judge = "openai-compat"
judge_model = "gpt-5-mini"
```

See [decibench.toml.example](./decibench.toml.example) for a fuller example.

## Development

```bash
pip install -e .[dev]
pytest
ruff check src/ tests/
mypy src/decibench/ --config-file pyproject.toml
```

## Product truth

If you are deciding whether to use Decibench for real work, use these files as
the source of truth:

- [README.md](./README.md)
- [docs/support-matrix.yaml](./docs/support-matrix.yaml)
- [plan.md](./plan.md)

If the README and the support matrix disagree, trust the support matrix.
