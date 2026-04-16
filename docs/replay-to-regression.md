# Replay to Regression Scenario

The replay-to-regression loop is the single feature that closes the loop
between "production failure" and "test that prevents the next one."

## What it does

For any imported call trace, Decibench can:

1. Take the actual transcript of the call.
2. Generate a scripted scenario YAML that reproduces the caller's side
   of the conversation.
3. Capture the agent's previously-successful behavior as `must_include`
   expectations so a regression catches drift.

That YAML can be checked into your repo and replayed forever via:

```bash
decibench run --target ws://your-agent --suite path/to/regression.yaml
```

## CLI

```bash
decibench replay --call-id <call_id> --out scenarios/regression-<id>.yaml
```

## Dashboard

The Call Detail screen has a **Generate regression** button. Clicking it
produces the YAML inline so you can copy it or download it as a file.
The dashboard uses the API endpoint:

```http
POST /calls/{call_id}/regression
→ { "call_id": "...", "scenario_id": "regression-...", "yaml": "..." }
```

You can also fetch the YAML directly:

```bash
curl http://127.0.0.1:8000/calls/<call_id>/scenario > regression.yaml
```

## What's in the generated scenario

- `id` and `metadata.source_call_id` link back to the original trace
- caller turns become scripted `caller` turns with the original text
- agent turns become `agent` turns with `expect.must_include` keyword
  guards extracted from the original agent reply
- conservative default success criteria (`task_completion` + a 1500ms
  p95 latency budget)

## Limits

- Generated regressions are deliberately **conservative**. They guard
  against the failure modes Decibench can prove from the trace, not
  every possible drift.
- If the original call had no transcript, the generator uses the agent's
  last response as a single guard rail.
- Tool calls in the original trace are not synthesized into mock tool
  responses today — see [Honest Limitations](limitations.md).
