# Dashboard / Failure Workbench

The Decibench dashboard is a **local** Vue 3 + Vite + Tailwind app served
by the FastAPI process. It is **shipped** in v1.0.

The point of the dashboard is to answer one question quickly:

> Which calls failed, why did they fail, and can I turn this into a
> regression test right now?

If a screen does not help with that question, it is not in the dashboard.

## Run it

```bash
decibench serve --port 8000
open http://127.0.0.1:8000/
```

The static assets are baked into the Python package — no Node required at
install time.

## Screens

### Failure Inbox (landing)

The default landing view is the failure list, not a generic run browser.

Filters available:

- `failed_only` toggle (on by default)
- `source` (jsonl / vapi / retell / …)
- `category` (compliance / latency / hallucination / …)
- `max_score` ceiling
- free-text `q` (matches call id, scenario, source)

Aggregate counters at the top come from a single
`GET /failure-inbox/stats` call so the page loads fast even on large
stores.

### Call Detail

For one call: source/target/duration metadata, the latest evaluation
summary, an ECharts span timeline (asr / llm / tts / tool_call), the full
transcript, and a **Generate regression** button.

Two actions on this screen:

- **Re-evaluate** — rerun the imported-call evaluators and persist a
  fresh evaluation row.
- **Generate regression** — produce the scenario YAML and let you copy
  or download it.

### Evaluation Detail

For one stored evaluation: score, pass/fail status, the failed
categories, the metric breakdown table, and the raw failure list.
Includes a "View call" link back to the source call.

### Runs (secondary)

Standard list of suite runs (`decibench run`). Click a row to see the
scenarios that ran and their pass/fail breakdown.

## API endpoints the dashboard talks to

All read-only unless noted:

```
GET  /failure-inbox/stats
GET  /call-evaluations?failed_only=...&source=...&category=...&max_score=...&q=...
GET  /call-evaluations/{evaluation_id}
GET  /calls
GET  /calls/{id}
GET  /calls/{id}/timeline
GET  /calls/{id}/evaluation
GET  /calls/{id}/evaluate          (runs evaluators; persists)
POST /calls/{id}/regression        (returns scenario id + YAML)
GET  /calls/{id}/scenario          (raw YAML, no JSON envelope)
GET  /runs
GET  /runs/{id}
```

Same endpoints are stable for CI scripts.

## Local development

If you want to hack on the UI:

```bash
cd dashboard
npm install
npm run dev      # Vite on :5173, proxies API to :8000
npm run build    # bakes into ../src/decibench/api/static/
```

See `dashboard/README.md` for the full dev contract.
