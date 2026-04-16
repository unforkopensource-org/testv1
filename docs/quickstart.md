# Quick Start

Goal: go from `pip install decibench` to a real run + a real failure
inspection in under five minutes, without touching any vendor account.

## 1. Install + smoke test

```bash
pip install decibench
decibench run --target demo:// --suite quick
```

`demo://` is a built-in echo-style agent that ships with the package. The
command runs the `quick` suite (a small bundled set of scenarios) end to
end and prints a `decibench_score`.

If you see a non-zero score and no tracebacks, the install is good.

## 2. Inspect the run

The run is persisted into your local store at `.decibench/decibench.sqlite`.

```bash
decibench runs                # list recent runs
decibench runs <run_id>       # show one run's details
```

## 3. Open the dashboard

```bash
decibench serve --port 8000
```

Then open `http://127.0.0.1:8000/`. You'll land on the **Failure Inbox**,
which shows stored imported-call evaluations with filters for source,
category, score, and a free-text search. Click any row to open the
**Call Detail** view (transcript, span timeline, regression action).

## 4. Try a real WebSocket agent

If you have a WebSocket voice agent (raw Retell or Vapi WS, your own
custom one, etc.), point Decibench at it:

```bash
decibench run --target ws://127.0.0.1:8765/agent --suite quick
```

See [WebSocket Testing](websocket-testing.md) for the wire contract.

## 5. Import a real production call and evaluate it

```bash
decibench import path/to/calls.jsonl
decibench evaluate <call_id>
```

The evaluation lands in the dashboard's failure inbox and can be turned
into a regression scenario with one click ("Generate regression" in the
call-detail view).
