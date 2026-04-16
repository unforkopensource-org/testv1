# Honest Limitations

Decibench is local-first, open source, and intentionally narrow in v1.0.
This page lists what the product **does not** do today, so users have
the right expectations on day one.

## Connectors

- The **native Retell** and **native Vapi** connectors are
  **experimental**. The protocol contract and Node bridge sidecar are
  shipped; the gated browser/SDK end-to-end test against real vendors is
  not on a per-PR CI run. For real Retell/Vapi work today use:
  - the **importers** (`decibench import` with `--source vapi|retell`)
  - the generic `ws://` connector for raw WebSocket endpoints
- LiveKit, ElevenLabs, Bland, SIP, and PSTN connectors are **planned**
  — not implemented.
- We do **not** host telephony. SIP/PSTN paths will always be BYO
  Twilio/Vonage.

## Evaluation

- The LLM judge is optional and falls back to deterministic +
  statistical metrics if no judge model is configured.
- MOS uses real DNSMOS only when the `decibench[mos]` extra is
  installed. Otherwise the heuristic fallback is clearly labeled in the
  output.
- Tool-call evaluation today is limited to the structured tool events
  that show up in the normalized trace. Mock tool-response synthesis
  during regression generation is **not** implemented.

## Replay / regression

- Generated regression scenarios are conservative: they catch the
  failure modes provable from the trace, not every possible drift.
- Audio-level regeneration of the original call is **not** part of
  v1.0. The replay path uses the transcript as the source of truth.

## Dashboard

- The dashboard is a **single-user local tool**. No auth, no orgs, no
  multi-tenant deployment.
- It reads the same SQLite store the CLI uses. There is no hosted
  alternative and there will not be one in v1.0.

## CLI

- `decibench compare` is **beta** — it works, but the output format may
  change.
- `decibench red-team` and `decibench mcp serve` are **planned** — the
  README does not claim them as shipped.

## Distribution

- Today: Python package on PyPI.
- Planned but not in v1.0: GitHub Releases, Homebrew formula, official
  Docker image.

## Public leaderboard

- Targeted for v1.1. Submission tooling is intentionally not in v1.0.

## Where to verify

- `docs/support-matrix.yaml` is the machine-readable source of truth.
- The README's support tables are generated from the same model.
- If you find a claim in any doc or marketing surface that this page
  contradicts, please open an issue. Trust > polish.
