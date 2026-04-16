# Production Import + Evaluation

Decibench can ingest real production calls from supported platforms,
normalize them into a provider-neutral `CallTrace`, and evaluate each
call with the same evaluators used by the live `decibench run` path.

This is the path most teams should adopt first: it gives you a real
failure inbox without needing to wire up a live test target.

## Supported importers (all **shipped**)

- `jsonl` — generic; one JSON object per line, fields documented below
- `vapi` — Vapi end-of-call report payloads
- `retell` — Retell call-log payloads

## Import

```bash
decibench import path/to/calls.jsonl
decibench import path/to/vapi-report.json --source vapi
decibench import path/to/retell-export.json --source retell
```

Each row is normalized into a `CallTrace` and persisted into your local
SQLite store (`.decibench/decibench.sqlite`) with privacy redaction
applied to phone numbers, emails, and Luhn-validated card numbers.

## Generic JSONL shape

```json
{
  "id": "call-2026-04-15-001",
  "source": "jsonl",
  "started_at": "2026-04-15T18:32:11Z",
  "duration_ms": 84210,
  "transcript": [
    { "role": "caller", "text": "I want to cancel my subscription" },
    { "role": "agent",  "text": "I can help. Can you confirm your account email?" }
  ],
  "spans": [
    { "name": "asr", "start_ms": 0,    "end_ms": 320,  "duration_ms": 320, "turn_index": 0 },
    { "name": "llm", "start_ms": 320,  "end_ms": 950,  "duration_ms": 630, "turn_index": 0 },
    { "name": "tts", "start_ms": 950,  "end_ms": 1180, "duration_ms": 230, "turn_index": 0 }
  ]
}
```

`spans` and `events` are optional but power the dashboard's timeline view.

## Evaluate

```bash
decibench evaluate <call_id>
```

This runs the deterministic evaluators (compliance, hallucination, task
completion) and, if you have a judge model configured in
`decibench.toml`, the LLM judge as well. The result is persisted to the
`call_evaluations` table and shows up in the dashboard's failure inbox.

You can also re-evaluate from the dashboard (Call Detail → "Re-evaluate")
or via the API (`GET /calls/{call_id}/evaluate`).

## Where the result lives

- `decibench evaluate` prints a summary to stdout
- The full `EvalResult` is persisted into SQLite
- The dashboard's Failure Inbox shows it within a few seconds
- The API exposes the same data via `/call-evaluations` and
  `/call-evaluations/{id}` for CI scripts
