# Decibench

### The open standard for voice agent quality. Free, transparent, reproducible.

**Version**: 1.0.0 · **License**: Apache-2.0 · **Python**: ≥3.11 · **Status**: v1.0 launch

> *Every voice agent platform charges you to test in the dark. We test in the open.*

---

## What Decibench actually does today

Decibench is a local-first CLI for testing voice agents. You point it at an
agent that speaks PCM audio over WebSocket, a local process, or an HTTP
endpoint, and it gives you a reproducible quality score with deterministic and
statistical metrics. You can also import calls from production (Vapi or Retell
end-of-call reports, or generic JSONL), evaluate them, replay them, and
generate regression scenarios from real failures.

It is **CLI-first** and **local-first**. Nothing leaves your machine unless you
explicitly opt in to a hosted LLM judge.

The full status of every connector, importer, evaluator, and surface lives in
[`docs/support-matrix.yaml`](./docs/support-matrix.yaml). That file is the
single source of truth — this README mirrors it, not the other way round.

---

## 30 seconds to your first score

```bash
pip install decibench

# Zero config. Zero API keys. Zero cost. Works instantly.
decibench run --target demo --suite quick
```

The `demo` target ships a built-in test agent. No setup, no deployment, no
keys. Once you have seen what Decibench does, point it at your real agent.

```bash
# Test your agent over a WebSocket endpoint
decibench run --target ws://your-agent:8080 --suite quick

# Or run a local script as the agent (no deployment required)
decibench run --target 'exec:"python my_agent.py"' --suite quick
```

---

## Support matrix (Shipped / Beta / Experimental / Planned)

Every line below maps to an entry in `docs/support-matrix.yaml`. If something
is **Planned**, it does not work yet — do not size a project around it.

### Connectors

| Connector | Target URI | Status | Notes |
|---|---|---|---|
| **Demo** | `demo://` | Shipped | Built-in echo agent for the quickstart. |
| **WebSocket** | `ws://host:port/path` | Shipped | Generic WS connector. PCM16 mono. |
| **Process / exec** | `exec:"command"` | Shipped | Spawn a local process; pipe PCM via stdin/stdout. |
| **HTTP** | `http://host/endpoint` | Shipped | Batch / non-realtime agents. |
| **Retell native** | `retell://agent_id` | Experimental | Browser-bridge sidecar required (see Native Bridge). Use `ws://` to your Retell WebSocket endpoint until the bridge lands end to end. |
| **Vapi native** | `vapi://agent_id` | Experimental | Same architecture as Retell. Use `ws://` for raw Vapi WebSocket today. |
| **LiveKit** | — | Planned | Will reuse the same sidecar bridge. |
| **ElevenLabs** | — | Planned | |
| **Bland** | — | Planned | |
| **SIP / PSTN** | — | Planned | Telephony is intentionally BYO Twilio/Vonage. |

### Importers (production calls)

| Importer | Status | Notes |
|---|---|---|
| Generic JSONL | Shipped | One call per line. |
| Vapi end-of-call-report | Shipped | |
| Retell call log | Shipped | |

### Evaluators

| Layer | Evaluator | Status |
|---|---|---|
| Deterministic | WER (jiwer-based, weighted intent) | Shipped |
| Deterministic | CER (auto for CJK) | Shipped |
| Deterministic | Latency (P50/P95/P99 nearest-rank) | Shipped |
| Deterministic | Task completion (per-turn slots) | Shipped |
| Deterministic | Compliance (PII, phone, AI disclosure) | Shipped |
| Deterministic | Hallucination grounding | Shipped |
| Deterministic | Interruption / barge-in | Shipped |
| Deterministic | Silence | Shipped |
| Statistical | DNSMOS (real, with `[audio-quality]` extra) | Shipped |
| Statistical | DNSMOS heuristic fallback (clearly labeled) | Shipped |
| Statistical | STOI | Shipped |
| Composite | Decibench Score | Shipped |

### Storage and replay

| Surface | Status |
|---|---|
| SQLite local store + schema migrations | Shipped |
| Privacy redaction (phone, email, Luhn-validated cards) | Shipped |
| Imported-call evaluation + persistence | Shipped |
| Replay-to-regression scenario generation | Shipped |

### CLI / API / Dashboard

| Surface | Status |
|---|---|
| `decibench run / import / evaluate / replay / runs / serve / scenario` | Shipped |
| `decibench compare` | Beta — works for any two targets that work standalone. |
| `decibench red-team` | Planned. |
| `decibench mcp serve` | Planned. |
| Read-only API (runs, calls, evaluations, scenario generation) | Shipped |
| Failure workbench dashboard (Vue 3 + TS + Vite + Tailwind + ECharts) | Shipped — failure inbox, call detail, evaluation detail, regression action. |

If a feature is missing from this matrix, treat it as not shipped.

---

## Native Bridge (Retell and Vapi)

Native Vapi and Retell calls run over vendor-managed WebRTC stacks
(Daily.co for Vapi, LiveKit for Retell). Reverse-engineering those into a
pure-Python WebRTC client is a high-risk path that does not match the
supported vendor flow. Decibench takes a different route:

```text
Python Orchestrator
  -> RetellConnector / VapiConnector
    -> local WebSocket bridge
      -> Node 20 + TypeScript sidecar
        -> Playwright headless Chromium
          -> official browser SDK
            -> vendor native call
```

The sidecar speaks a small, **platform-neutral JSON protocol**
(`docs/bridge-protocol.md`). The Python connector launches it on demand and
streams PCM16 mono audio in and out.

Status: **Experimental**. The protocol contract is shipped, the Python
connector wiring is shipped, the Node sidecar lands behind the
`decibench-bridge` package. Until the end-to-end Retell integration test is
green, the README does not claim native Retell as Shipped.

---

## Core design principles

1. **Local-first.** Nothing leaves your machine unless you choose a hosted
   LLM judge.
2. **Pluggable, not prescribed.** TTS, STT, and LLM judge are all interface
   contracts; the framework does not care which provider you choose.
3. **Zero dependencies can still produce a useful score.** Set
   `judge = "none"` in `decibench.toml` and Decibench runs only deterministic
   and statistical metrics — no LLM, no API keys, no cost.
4. **Transparent scoring.** Every formula is in source. Same input, same
   config, same score.
5. **CLI-first.** The CLI is the product. The dashboard helps with failure
   triage; it is not the product surface.

---

## How it works

```
┌─────────────────────────────────────────────────────────┐
│                     decibench CLI                       │
│   run | import | evaluate | replay | runs | serve | …   │
├─────────────────────────────────────────────────────────┤
│                    Orchestrator                         │
│  Load scenario → Synthesize audio → Connect to agent →  │
│  Stream audio → Record response → Evaluate → Report     │
├───────────┬──────────┬───────────┬──────────┬───────────┤
│ Connectors│ Audio    │ Scenarios │Evaluators│ Reporters │
│           │ Engine   │           │          │           │
│ demo      │ TTS      │ YAML load │ wer/cer  │ JSON      │
│ websocket │ STT      │ validate  │ latency  │ HTML      │
│ exec      │ noise mix│ generate  │ task     │ CI        │
│ http      │ record   │ regression│ comply   │ Markdown  │
│ retell ✱  │          │ generation│ halluc   │ JUnit     │
│ vapi ✱    │          │           │ MOS/STOI │           │
│           │          │           │ score    │           │
└───────────┴──────────┴───────────┴──────────┴───────────┘
                                    ✱ Experimental — bridge sidecar required.
```

---

## Providers

Pluggable across TTS (caller voice), STT (transcription), and LLM judge.

```toml
[providers]
tts = "edge-tts"                              # Shipped
tts_voice = "en-US-JennyNeural"
stt = "faster-whisper:base"                    # Shipped
judge = "openai-compat://localhost:11434/v1"   # Any OpenAI-compatible endpoint, or "none"
judge_model = "llama3.2"
```

The OpenAI-compatible chat completions API is the universal LLM interface.
Ollama, vLLM, LM Studio, OpenAI, Groq, Together, OpenRouter, and Fireworks
all expose it; one adapter covers them all.

---

## Scenarios

Two modes, both Shipped: **scripted** (deterministic regression) and
**adaptive** (LLM-driven discovery, requires a configured judge).

Scenario suites live in `scenarios/`. Industry packs are community-contributed.

---

## CLI reference

```bash
decibench run           # Run test scenarios against a voice agent
decibench import        # Import production calls (Vapi / Retell / JSONL)
decibench evaluate      # Evaluate an imported call
decibench replay        # Replay → regression scenario
decibench runs          # List stored runs
decibench compare       # Side-by-side comparison (Beta)
decibench scenario      # List, validate, generate scenarios
decibench serve         # Start local dashboard
decibench init          # Create decibench.toml
decibench version       # Show version info
decibench doctor        # Diagnose your setup
```

Anything not in this list is not shipped.

---

## Configuration: `decibench.toml`

See [`decibench.toml.example`](./decibench.toml.example) for a full annotated
example. Minimum:

```toml
[project]
name = "my-voice-agent"

[target]
default = "ws://localhost:8080"

[providers]
tts = "edge-tts"
stt = "faster-whisper:base"
judge = "none"

[ci]
min_score = 80
```

---

## CI/CD

```yaml
name: Voice Agent QA
on: [push]
jobs:
  decibench:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install 'decibench[stt-whisper,tts-edge]'
      - run: decibench run --target ws://your-agent:8080 --suite quick \
                          --min-score 80 --exit-code-on-fail
```

---

## What Decibench intentionally does NOT do

| Not this | Why | Use this instead |
|---|---|---|
| Production call monitoring | Needs always-on infrastructure | Vendor monitoring or a dedicated platform |
| Hosted multi-user dashboard | Open source, not SaaS | `decibench serve` (local) |
| PSTN infrastructure | Too expensive to bundle | BYO Twilio / Vonage |
| Prescribe models | Your stack, your choice | Pluggable interfaces for everything |

---

## Honest limitations

- **Native Vapi / Retell are Experimental.** Use `ws://` to a real WebSocket
  endpoint until the sidecar bridge has an end-to-end Retell integration test
  passing.
- **Adaptive scenarios require a judge.** With `judge = "none"` they are
  skipped.
- **DNSMOS without the `[audio-quality]` extra** falls back to a heuristic
  signal-health estimate that is clearly labeled in output and capped at 4.0.
- **Compare CLI is Beta.** It works for any two targets that work standalone,
  but the report is intentionally minimal.
- **Red-team and MCP server are Planned**, not shipped. Older copy claiming
  otherwise has been removed.

---

## Documentation

The truth lives in two places:

- [`docs/support-matrix.yaml`](./docs/support-matrix.yaml) — machine-readable
  feature status (the source the README and dashboard match against).
- [`docs/`](./docs/) — Markdown docs:
  - [Install](./docs/install.md)
  - [Quick start](./docs/quickstart.md)
  - [WebSocket testing](./docs/websocket-testing.md)
  - [Local `exec:` testing](./docs/exec-testing.md)
  - [Production import + evaluation](./docs/import-and-evaluate.md)
  - [Replay to regression](./docs/replay-to-regression.md)
  - [Native connector status](./docs/native-connectors.md)
  - [Dashboard / failure workbench](./docs/dashboard.md)
  - [Bridge protocol](./docs/bridge-protocol.md)
  - [Honest limitations](./docs/limitations.md)

---

*Apache-2.0 · github.com/decibench · The open standard for voice agent quality.*
