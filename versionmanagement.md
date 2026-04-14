# Decibench — Version Management & Roadmap

**Last updated**: April 2026

---

## Release philosophy

Ship fast, ship working, ship complete within scope. Each version has a hard boundary — nothing leaks forward, nothing gets half-shipped. If it's in the checklist, it works end-to-end. If it doesn't work end-to-end, it's not in the checklist.

---

## V1.0.0 — "The Foundation" (Target: Ship it)

**Goal**: A developer can `pip install decibench`, run one command, and get a quality score for any voice agent. Zero config path works. Paid platforms should see this and realize the free alternative just arrived.

### Core framework

- [x] Project scaffolding: pyproject.toml, uv + hatch, ruff, mypy
- [x] Config system: `decibench.toml` loading + validation with Pydantic
- [x] CLI skeleton: Click-based with `run`, `compare`, `init`, `version` commands
- [x] Pydantic data models: Scenario, Persona, TurnExpectation, EvalResult, SuiteResult
- [x] YAML scenario loader + validator
- [x] Provider registry pattern (TTS, STT, Judge — all pluggable)
- [x] Orchestrator: central execution engine (CLI wraps this, MCP wraps this, everything wraps this)

### Connectors (V1.0 scope)

- [x] **WebSocket connector** (`ws://`) — universal, covers most agents
- [x] **Process connector** (`exec:`) — test local agents without deploying. The killer feature.
- [x] **HTTP connector** (`http://`) — batch/REST agents
- [x] **Demo connector** (`demo://`) — built-in demo agent, zero-config first run in 30 seconds
- [ ] Vapi connector (`vapi://`) — deferred to V1.1
- [ ] Retell connector (`retell://`) — deferred to V1.1
- [ ] LiveKit, Pipecat, ElevenLabs, Bland, SIP, PSTN — deferred to V1.1+

### Audio engine

- [x] TTS provider: edge-tts adapter (default, $0, 400+ voices)
- [x] TTS provider: OpenAI-compatible adapter (covers ElevenLabs, Azure, etc.)
- [x] Audio synthesizer: orchestrates TTS + processing pipeline
- [x] Noise mixing with librosa (clean, cafe, street, car profiles)
- [x] Audio transcoding: sample rate + encoding conversion (PCM, mulaw, opus)
- [x] Audio recorder: capture and store agent responses
- [x] STT provider: faster-whisper adapter (default, $0, CPU-friendly)
- [x] STT provider: OpenAI-compatible adapter (covers Deepgram, AssemblyAI, etc.)

### Evaluators (V1.0 scope — deterministic + statistical)

- [x] **WER / CER** via jiwer (auto-CER for CJK languages)
- [x] **Latency**: TTFW, turn latency P50/P95/P99, response gap
- [x] **DNSMOS**: no-reference MOS scoring (ONNX model, auto-download)
- [x] **STOI**: intelligibility via pystoi
- [x] **SNR**: signal-to-noise via librosa
- [x] **Slot extraction accuracy**: extracted values vs reference
- [x] **Tool call correctness**: right tool + right parameters
- [x] **PII pattern detection**: regex + patterns for SSN, CC, DOB, phone, email
- [x] **AI disclosure check**: agent identifies as AI within first N seconds
- [x] **Silence duration**: dead air detection
- [x] **Decibench Score calculator**: weighted composite score (0-100)
- [x] **`judge = "none"` mode**: full deterministic-only scoring, no LLM needed

### Semantic evaluators (requires LLM judge)

- [x] **LLM judge**: OpenAI-compatible universal interface (Ollama, vLLM, OpenAI, Groq, etc.)
- [x] **"None" judge**: no-op for deterministic-only mode
- [x] **Task completion**: LLM-judged goal achievement
- [x] **Hallucination detection**: claims not grounded in KB/tools/context
- [x] **Compliance evaluator**: HIPAA ordering, PCI echo-back, AI disclosure

### Scenarios

- [x] **Quick suite**: 10 hand-crafted scenarios (~2 min)
- [x] **Standard suite**: 50 scenarios (~10 min)
- [x] Scripted mode: pre-defined conversation turns, deterministic
- [x] Variant expansion: noise levels x accents x speeds (cross-product)
- [x] Tool mocks: configurable mock responses for agent tool calls
- [ ] Adaptive mode (LLM-driven caller) — deferred to V1.2
- [ ] Industry packs (healthcare, financial, etc.) — deferred to V1.1

### Reporters

- [x] **JSON reporter**: machine-readable, pipe into anything
- [x] **Rich terminal reporter**: beautiful CLI output, screenshot-worthy
- [x] **CI/CD reporter**: GitHub Actions annotations, `--exit-code-on-fail`
- [x] **Markdown reporter**: for GitHub PR comments
- [ ] HTML reporter with embedded audio — deferred to V1.1

### CLI commands

- [x] `decibench run` — run test suite against any agent
- [x] `decibench compare` — side-by-side comparison (screenshot-worthy output)
- [x] `decibench init` — create decibench.toml with sensible defaults
- [x] `decibench scenario list` — list available suites and scenarios
- [x] `decibench scenario validate` — validate custom YAML scenarios
- [x] `decibench version` — version + environment info
- [ ] `decibench red-team` — deferred to V1.1
- [ ] `decibench report` — HTML report generation, deferred to V1.1
- [ ] `decibench mcp serve` — MCP server, deferred to V1.1
- [ ] `decibench serve` — local web dashboard, deferred to V2.0

### First-run experience (critical for adoption)

- [x] `pip install decibench` includes demo agent responses (~2MB)
- [x] `decibench run --target demo --suite quick` works with zero config, zero keys, zero cost
- [x] Demo completes in <60 seconds on any machine
- [x] Demo shows both passing and failing metrics (not a fake perfect score)
- [x] Output is beautiful enough to screenshot and share
- [x] Cost tracking: shows $0.00 for the demo run

### CI/CD integration

- [x] `--exit-code-on-fail` flag (non-zero exit when score < threshold)
- [x] `--min-score` flag for quality gates
- [x] `--output` flag for JSON artifact export
- [x] GitHub Actions example in docs
- [x] `--profile` flag for dev/ci/benchmark presets

### Config profiles

- [x] `[profiles.dev]` — quick suite, 1 run per scenario
- [x] `[profiles.ci]` — regression suite, 3 runs, min score 80
- [x] `[profiles.benchmark]` — full suite, 5 runs

---

## V1.1 — "The Disruptor" (Target: 4-6 weeks after V1.0)

**Goal**: Platform connectors, public leaderboard, red-team module, MCP server. This is the version that makes paid platforms nervous.

### Public Leaderboard

- [ ] **decibench.dev/leaderboard** — live, community-driven platform rankings
- [ ] GitHub-native: results submitted as PRs to `decibench/results` repo
- [ ] GitHub Action validates JSON schema + reproducibility checks
- [ ] Auto-updates `LEADERBOARD.md` on merge
- [ ] GitHub Pages renders static leaderboard site
- [ ] `decibench submit --file results.json` — opens PR from CLI
- [ ] Every submission is a git commit — version-controlled, transparent, challengeable

### Platform connectors

- [ ] **Vapi connector** (`vapi://agent_id`) — WebSocket PCM/mulaw, end-of-call-report extraction
- [ ] **Retell connector** (`retell://agent_id`) — create-web-call, multi-channel audio, public_log_url
- [ ] **LiveKit connector** (`livekit://room`) — WebRTC via SDK, component-level metrics extraction
- [ ] **Pipecat connector** (`pipecat://host:port`) — frame-level pipeline traces
- [ ] **ElevenLabs connector** (`elevenlabs://agent_id`) — Simulation API, vad_score, interruption events
- [ ] **Bland connector** (`bland://agent_id`) — node test results, emotion analysis
- [ ] Bring Your Own Connector: `--connector ./my_connector.py` with registration decorator

### Red-team module

- [ ] `decibench red-team` CLI command
- [ ] **Jailbreak attacks**: role-playing escalation, authority override, multi-turn (basic/intermediate/advanced)
- [ ] **PII extraction attacks**: direct request, social engineering, incremental extraction, context confusion
- [ ] **Prompt injection via speech**: spoken instruction override
- [ ] **Bias / accent discrimination**: same scenario across 6+ accent groups, equity gap measurement
- [ ] **Scope escape**: leading agent outside intended function
- [ ] **Social engineering**: urgency, authority, sympathy tactics
- [ ] Severity classification per finding (critical / high / medium / low)
- [ ] Remediation recommendations per attack
- [ ] `--min-resistance` flag for CI/CD quality gates
- [ ] Red-team transcript export for audit
- [ ] Red-team summary report (terminal + JSON)

### MCP server

- [ ] `decibench mcp serve` — stdio transport
- [ ] `decibench_run` tool — run suite against target
- [ ] `decibench_quick_test` tool — 10-scenario quick suite
- [ ] `decibench_check_latency` tool — latency-focused testing
- [ ] `decibench_check_compliance` tool — HIPAA/PCI/AI disclosure
- [ ] `decibench_compare` tool — side-by-side comparison
- [ ] `decibench_red_team` tool — run adversarial attacks
- [ ] `decibench_explain_failure` tool — analyze specific scenario failures
- [ ] `decibench_generate_scenario` tool — generate scenarios from description
- [ ] MCP config JSON example for Claude Code, Cursor, Windsurf

### Additional evaluators

- [ ] **Barge-in evaluator**: detection time, false positive rate, context recovery
- [ ] **Interruption evaluator**: double-talk duration, response after interruption
- [ ] **Flow evaluator**: turn efficiency, repetition detection (embedding similarity), context retention across 5+ turns
- [ ] **Robustness evaluator**: noise degradation scoring, accent equity gap
- [ ] **Hallucination evaluator**: enhanced with KB grounding checks

### Scenarios

- [ ] **Full suite**: 200 scenarios (~45 min)
- [ ] **Adversarial suite**: 50 scenarios — barge-in, topic switching, silence, mumbling
- [ ] **Acoustic suite**: 30 scenarios — same conversations across noise/accent variants
- [ ] **Red-team suite**: 40 scenarios — jailbreak, PII extraction, prompt injection, bias
- [ ] **Regression suite**: auto-generated from previous failures
- [ ] **Industry pack: Healthcare** — HIPAA compliance, appointment scheduling, symptom triage
- [ ] **Industry pack: Financial** — PCI-DSS, account verification, transaction processing
- [ ] **Industry pack: Support** — escalation handling, multi-intent, returns/refunds

### Reporters

- [ ] **HTML reporter** with embedded audio playback, per-scenario drill-down
- [ ] **Compare reporter**: dedicated comparison output format

### State of Voice AI report

- [ ] Run full suite against Vapi, Retell, ElevenLabs, Bland, LiveKit
- [ ] Publish Q2 2026 "State of Voice AI Quality" report
- [ ] Head-to-head comparison across all metrics
- [ ] Red-team resistance scores per platform
- [ ] Accent equity gap analysis per platform
- [ ] Cost-per-quality analysis
- [ ] Publish on decibench.dev + GitHub + blog

---

## V1.2 — "The Standard" (Target: 8-12 weeks after V1.1)

**Goal**: Adaptive mode, telephony, multi-language. Decibench becomes the testing framework that enterprises can't ignore.

### Adaptive mode

- [ ] LLM-driven caller that pursues a goal, improvising within persona constraints
- [ ] Real-time turn-taking decision engine (when to speak, when to listen)
- [ ] Persona constraint enforcement during improvisation
- [ ] Goal achievement detection (when to stop the conversation)
- [ ] Conversation branching and recovery
- [ ] Max turns and timeout controls

### Telephony connectors

- [ ] **SIP connector** (`sip://user@host:port`) — SIP INVITE + RTP, DTMF, codec negotiation
- [ ] **PSTN connector** (`tel:+14155551234`) — BYO Twilio/Vonage, full telephony stack
- [ ] Jitter measurement, packet loss, carrier effects
- [ ] MOS via Voice Insights (Twilio) or ViSQOL

### Multi-language support

- [ ] Scenario YAML language field
- [ ] Auto-select CER vs WER based on language
- [ ] TTS voice selection per language (edge-tts: 100+ languages)
- [ ] STT model selection per language (whisper multilingual)
- [ ] LLM judge prompts in target language

### Additional TTS providers

- [ ] Piper TTS adapter (offline, GPL-3.0, optional extra)
- [ ] Coqui XTTS adapter (voice cloning, multilingual)

### Scenario generation

- [ ] `decibench scenario generate --description "..." --count 20`
- [ ] LLM-powered generation from agent description
- [ ] Auto-generate regression scenarios from previous failures

### Enhanced evaluators

- [ ] **Emotion detection**: frustration, confusion, satisfaction in agent responses
- [ ] **UTMOS/UTMOSv2**: naturalness-focused MOS (supplement DNSMOS for TTS quality)
- [ ] **Intent accuracy**: P/R/F1 per intent class
- [ ] **Context retention scoring**: information retention at increasing turn distances

---

## V2.0 — "The Platform" (Target: 6 months after V1.0)

**Goal**: Decibench is the default. If you build a voice agent and don't test it with Decibench, people ask why.

### Local web dashboard

- [ ] `decibench serve` — FastAPI + HTMX
- [ ] Browse historical results
- [ ] Interactive compare view
- [ ] Audio playback per scenario
- [ ] Trend charts (quality over time)
- [ ] Red-team finding browser

### Plugin system

- [ ] Third-party evaluator plugins (`pip install decibench-plugin-emotion`)
- [ ] Third-party connector plugins
- [ ] Third-party reporter plugins
- [ ] Plugin registry on decibench.dev

### Advanced features

- [ ] Load testing: concurrent calls to stress-test agents
- [ ] A/B testing: statistical significance testing between agent versions
- [ ] Voice cloning for consistent test personas (via Coqui XTTS)
- [ ] Webhook notifications on quality regression
- [ ] Slack/Discord integration for CI/CD notifications

### Community infrastructure

- [ ] Decibench Score badge service (decibench.dev/badge/...)
- [ ] Scenario marketplace: community-contributed and curated scenario packs
- [ ] Connector marketplace: community-contributed platform connectors
- [ ] Annual "Voice Agent Quality Awards" based on leaderboard data

---

## Version numbering convention

```
MAJOR.MINOR.PATCH

MAJOR: Breaking changes to CLI interface, config format, or scoring formula
MINOR: New features, connectors, evaluators (backward compatible)
PATCH: Bug fixes, scenario updates, metric calibration
```

Scoring formula changes always bump MINOR at minimum and are announced with migration guide. Leaderboard results always reference the Decibench version that produced them.

---

## What ships vs. what's roadmap — the hard rule

If it's checked in this document, it works end-to-end in that version. Not "partially implemented." Not "works in happy path." Not "needs manual setup." End-to-end.

If it's unchecked, it doesn't ship in that version. No exceptions. No "let me just squeeze this in." Scope creep is how frameworks ship half-broken and lose trust.

**V1.0 ships tight. V1.1 ships scary. V1.2 ships complete. V2.0 ships dominant.**

---

*The open standard for voice agent quality.*

*Apache-2.0 · github.com/decibench · decibench.dev*
