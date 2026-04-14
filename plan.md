# Decibench v1.0 Last-Mile Plan

Updated: 2026-04-15

Goal: finish the last three product tracks that matter and make Decibench:

- **10/10 as an open-source voice-agent QA product**
- **9/10 against paid competitors**

This file intentionally replaces the broader roadmap with a tighter launch plan.

Everything below assumes the earlier foundation work is already done and does
not get reopened unless one of the three remaining tracks truly requires it.

---

## Current Verified State

Latest local verification:

| Check | Status |
| --- | --- |
| Ruff | Passing |
| Mypy | Passing |
| Tests | Passing |
| Tests count | 138 passed |
| Versioning | 1.0.0 aligned |
| Store | SQLite + migrations + privacy redaction shipped |
| Importers | JSONL + Vapi + Retell shipped |
| Imported-call evaluation | CLI + API + persistence shipped |
| Replay/regression generation | Shipped |
| API | Shipped |
| Local dashboard | Shipped, but basic |
| Native Vapi connector | Stubbed, not end to end |
| Native Retell connector | Stubbed, not end to end |

## What Is Already Considered Done

For v1.0 scope, the following are treated as complete enough and should not
be reopened unless they block one of the final three tracks:

- package version alignment
- local-first SQLite store
- schema migrations
- privacy redaction
- JSONL import
- Vapi import
- Retell import
- imported-call evaluation
- imported-call evaluation persistence
- replay to regression scenario generation
- CLI run/import/replay/evaluate/runs/serve flows
- API base for runs, calls, evaluations, and scenario generation
- quality gate: Ruff, mypy, tests

That means the release is no longer blocked by “more foundation.”

The release is blocked by the final product gap between:

- **good code**
- and **a complete open-source product people trust immediately**

---

## Scope Lock

Only these three tracks remain in scope for the current push:

1. **Finish one real native connector end to end**
2. **Turn the dashboard into a real failure-analysis workbench**
3. **Bring README and product claims down to exact truth**

Everything else is subordinate to one of those three tracks.

If a task does not directly help one of them, it is not part of this plan.

---

## Why These Three Are The Right Final Tracks

### 1. Native connector

This is the biggest remaining gap versus Hamming, Roark, Cekura, and Coval.

Right now Decibench has:

- a strong core engine
- a good local store
- production import and replay
- a credible CLI/API story

But the native Vapi and Retell connectors still stop at the exact point where a
serious team expects the product to take over.

Until one of those connectors works end to end, Decibench still looks partly
like a framework and partly like a product.

### 2. Failure workbench

The current dashboard proves the storage and API layers are real.

It does **not** yet give a QA or product user the fastest path from:

- “this call failed”
- to “I know why”
- to “I can turn it into a regression”

Paid tools win here because they make failure inspection easy and fast.

### 3. README truth

Open-source trust is fragile.

If the code is more truthful than the README, users feel baited.
If the README is more truthful than the code, users feel safe.

For open source, this is not polish. It is part of the product.

---

## Track 1: Ship One Real Native Connector End To End

## Decision

**Ship Retell first. Reuse the same bridge architecture for Vapi second.**

Reason:

- Retell’s web-call flow is a cleaner first target for a supported browser-side
  connector path.
- The current code already has a Retell importer and connector scaffold.
- A shared browser/WebRTC bridge can be adapted to Vapi after the first one is
  real.

We are **not** trying to finish both platforms at once.

v1.0 only needs one native connector to be truly real. The second one can reuse
 the same architecture immediately after.

## Best Technical Approach

### Keep

- **Python** as the main product runtime
- existing orchestrator
- existing connector model
- existing store and evaluation pipeline

### Add

- a **small Node 20 + TypeScript sidecar**
- **Playwright + headless Chromium**
- the **official browser SDK** for the target platform
- a **local WebSocket bridge** between Python and the sidecar

### Why This Stack Is Best

The official native voice SDKs are usually browser/WebRTC-first.

Trying to force a pure-Python custom WebRTC implementation for v1.0 would be a
high-risk detour:

- more protocol reverse engineering
- more transport bugs
- harder audio debugging
- less confidence that the path matches the supported vendor path

The best v1.0 move is:

1. use the vendor’s official browser-side flow
2. run it in a reproducible headless browser
3. bridge PCM audio and events cleanly back to Python

This keeps Decibench honest and dramatically lowers the “works in docs, breaks
in reality” risk.

## Recommended Stack

### Runtime

- **Python 3.11+** stays as the main Decibench runtime
- **Node 20 LTS** only for the native bridge sidecar

### Browser layer

- **Playwright** for launching and controlling Chromium reliably
- **Headless Chromium** for browser-only SDK and WebRTC APIs

### Platform adapter

- **Retell official browser/web SDK**
- Later: **Vapi official browser/web SDK**

### Audio bridge

- **AudioWorklet** in the browser page for low-latency PCM push/pull
- local **WebSocket control channel** between Python and sidecar
- explicit support for:
  - PCM16 mono
  - sample-rate conversion
  - end-of-turn signaling
  - transcript events
  - metadata/tool-call events when available

### Local process model

- Python CLI starts the sidecar on demand
- sidecar lifecycle is fully owned by the connector
- no long-running external daemon required

## Architecture

```text
Python Orchestrator
  -> RetellConnector
    -> local WebSocket bridge
      -> Node/TS sidecar
        -> Playwright Chromium page
          -> official browser SDK
            -> vendor native call
```

## What We Must Build

### Phase 1A: Generic native bridge protocol

Build a platform-neutral bridge contract first:

- `connect`
- `send_audio_chunk`
- `end_turn`
- `receive_event`
- `disconnect`
- `health`
- `capabilities`

Every message should be structured JSON with explicit event types.

Do not start with one-off Retell-specific wire messages.

### Phase 1B: Retell adapter

Implement the Retell bridge adapter against the generic contract:

- token acquisition / web-call session bootstrap
- browser page session start
- PCM in -> browser track
- browser audio/transcript/events -> Decibench events
- clean teardown
- timeout handling
- failure diagnostics

### Phase 1C: Connector integration

Wire the current Python connector to the sidecar:

- remove `NotImplementedError`
- stream audio from orchestrator
- persist events and metadata into the existing store
- make sure imported and live-native runs look similar in downstream analysis

### Phase 1D: Integration tests

Add guarded tests:

- mocked sidecar protocol tests
- end-to-end bridge tests with fixture audio
- real Retell integration test behind environment flags

### Phase 1E: Vapi reuse

After Retell is working, adapt the same bridge architecture for Vapi:

- keep the same local bridge contract
- swap only the browser SDK adapter layer

## What We Must Not Do

- do **not** build a custom pure-Python WebRTC stack for v1.0
- do **not** implement Retell and Vapi in parallel before one is real
- do **not** claim native support in README until the end-to-end test passes
- do **not** hide failures behind vague “experimental” wording if the path is
  still not usable

## Definition Of Done

Retell native support is done when all of the following are true:

- `decibench run --target retell://... --suite quick` works against a real agent
- real audio goes in and real audio/events come back
- transcript/events show up in stored run data
- failures are debuggable from logs and stored metadata
- integration tests exist
- docs show exact prerequisites and limitations

Vapi support is done for this release only if it reaches the same bar.
If not, it stays explicitly marked **planned next**, not implied.

---

## Track 2: Turn The Dashboard Into A Failure Workbench

## Decision

Keep the backend stack.
Upgrade the frontend stack.

### Keep

- **FastAPI** as the API server
- **SQLite** as the local data source
- existing API endpoints where they already fit

### Replace

Replace the current inline CDN prototype page with a real built frontend:

- **Vue 3**
- **TypeScript**
- **Vite**
- **Tailwind CSS**
- **Vue Router**
- **TanStack Query** for API state
- **Apache ECharts** for score, latency, and span timeline visuals

## Why This Stack Is Best

The current dashboard already uses Vue, so a React rewrite would just create
stack churn without user benefit.

The problem is not Vue.
The problem is that the current page is still a prototype:

- CDN scripts
- no routing
- no failure inbox
- no real call-analysis flow

Vue 3 + TypeScript + Vite is the right upgrade because it:

- keeps continuity with the existing UI
- adds strong typing for complex run/evaluation data
- is easy to ship as static assets from FastAPI
- is friendly to open-source contributors

## Product Goal

The dashboard should answer this in under one minute:

1. Which calls failed?
2. Why did they fail?
3. Which category failed?
4. What transcript and timing evidence supports that?
5. Can I turn this into a regression scenario right now?

If it cannot answer those questions fast, it is still a browser, not a workbench.

## Required Screens

### 2A. Failure Inbox

Primary landing view should become failures, not generic runs.

Must show:

- stored imported-call evaluations
- failed-only toggle
- source filter
- category filter
- score threshold filter
- search by call id / target / source
- newest first

### 2B. Call Detail

For one call, show:

- transcript
- source metadata
- evaluation score
- failed categories
- failed metrics
- call spans / timing timeline
- button to generate/export regression scenario

### 2C. Evaluation Detail

For one stored evaluation, show:

- failure summary
- full failure list
- metric table
- pass/fail chips
- links back to the source call

### 2D. Run Detail

Keep run inspection, but make it secondary to failure analysis.

### 2E. Regression Action

The UI must make this a first-class action:

- inspect call
- generate scenario
- copy/export YAML
- link evaluation to generated regression

## Required API Work

The frontend should not parse huge payloads client-side to discover structure.

Backend should expose first-class endpoints for:

- call evaluations list with filtering
- one call with transcript and metadata
- one evaluation with metrics and failure summary
- spans/timeline data
- regression scenario generation

If any of those are missing or awkward, add explicit endpoints instead of
forcing frontend hacks.

## UX Rules

- failure-first default
- stable links for runs, calls, and evaluations
- no hidden state
- no giant cards inside cards
- keyboard-copyable IDs
- redaction markers must remain visible and trustworthy
- call detail should work for a product/QA user without CLI knowledge

## What We Must Not Do

- do **not** build auth/multi-user org features for v1.0
- do **not** build a hosted SaaS dashboard
- do **not** keep the current one-file CDN prototype as the final UI
- do **not** optimize for pretty over debuggable

## Definition Of Done

The dashboard/workbench is done when:

- the landing view is useful for finding failed calls
- call detail makes failure reasoning obvious
- transcript + failed metrics + timing evidence are visible together
- stored evaluations are easy to inspect
- regression generation is one action, not a CLI detour
- the UI feels reliable enough for a non-engineer to use alone

---

## Track 3: Bring README And Product Claims Down To Exact Truth

## Decision

The README becomes a product contract, not a hype page.

For v1.0 we should prefer:

- **less scope claimed**
- **more trust earned**

That is the correct open-source trade.

## Best Documentation Stack

### Repo docs

- **README.md** for the product overview
- **Markdown docs in `/docs`**
- optional **MkDocs Material** for a published static docs site

### Truth guardrail

Add a small docs-validation step in CI:

- README smoke commands must actually run
- support matrix must match real code status
- unsupported connectors/features must not appear as shipped

The most important improvement is not the docs site framework.
It is the **truth model**.

## Truth Model

Every user-facing capability must be labeled as exactly one of:

- **Shipped**
- **Beta**
- **Experimental**
- **Planned**

### Shipped

Code exists, works end to end, and is covered by tests or a release smoke path.

### Beta

Usable but with known limits, and clearly documented.

### Experimental

Code exists but should not be sold as reliable.

### Planned

Not shipped yet.

## README Rewrite Rules

### Must stay

- what Decibench actually does today
- local-first story
- open-source story
- reproducibility story
- import/evaluate/replay/regression loop
- CLI-first workflow

### Must be corrected

- connector claims that imply LiveKit, ElevenLabs, Bland, SIP/PSTN are already
  first-class shipped connectors
- any phrasing that implies native Vapi/Retell are already end to end when they
  are not
- any pricing/comparison table entries that can drift without a date or source
- any “best in category” language not supported by what the product can do now

### Must be added

- exact support matrix
- exact native-connector status
- honest limitations section
- “best with WebSocket, exec, import/replay today” guidance
- “what is partial vs what is done” section

## Best Way To Keep README Honest

Create one source of truth for feature status.

Recommended approach:

- add a small status manifest in repo, for example `docs/support-matrix.yaml`
- generate the rendered support matrix from that file
- require updates there when a connector/importer/UI status changes

This is much better than hand-maintaining status in multiple places.

## Minimal Required Docs Set

Before v1.0, docs must include:

1. Install
2. Quick start with `demo`
3. Real-time testing via WebSocket
4. Local `exec:` testing
5. Production import and evaluation
6. Replay to regression scenario
7. Native connector status table
8. Dashboard/workbench guide
9. Honest limitations

## What We Must Not Do

- do **not** market future connectors as current product surface
- do **not** keep stale competitor pricing tables without sources/dates
- do **not** let README claim “supports anything” if the real support path is
  WebSocket/import only
- do **not** confuse “architecture can support” with “product ships today”

## Definition Of Done

README/docs truth is done when:

- a new user gets the right expectation from the first screenful
- every support claim maps to a tested or explicitly labeled status
- the support matrix matches the code
- there are no obvious “marketing outran implementation” gaps

---

## Exact Execution Order

This is the order to finish the release without wasting time:

1. **README truth pass now**
   - remove inflated claims
   - add support matrix
   - label native connector status exactly

2. **Native bridge protocol**
   - generic sidecar contract
   - sidecar lifecycle management
   - logs and diagnostics

3. **Retell end-to-end native connector**
   - browser bridge
   - connector integration
   - tests

4. **Dashboard failure inbox and call detail**
   - failure-first landing page
   - call/evaluation detail
   - regression action

5. **Vapi native connector on the same bridge architecture**
   - only after Retell is real

6. **Final docs truth pass**
   - update status matrix
   - publish exact supported workflows

---

## Launch Gate

Decibench can claim the launch target only when all of the following are true:

- [x] Ruff passes
- [x] Mypy passes
- [x] Tests pass
- [x] Store/import/evaluate/replay loop works
- [x] API exists
- [x] Basic local dashboard exists
- [ ] One native connector works end to end against a real vendor target
- [ ] Dashboard is useful for failed-call triage, not only run browsing
- [ ] README and docs match the true product surface exactly

---

## What 10/10 Open Source Means Here

For this release, “10/10 open source” does **not** mean:

- most integrations
- most features
- biggest website

It means:

- easiest trustworthy local install
- easiest trustworthy CI usage
- easiest trustworthy self-hosted failure analysis
- easiest trustworthy extension path
- docs that tell the truth

Open source wins when users feel:

> “This tool is honest, usable, and mine.”

That is the bar.

---

## What 9/10 Against Paid Means Here

Decibench does not need to beat every paid platform feature-for-feature.

It needs to cover the real reliability loop well enough that a serious team can:

- test before deploy
- test locally
- import real calls
- evaluate them
- inspect failures
- generate regressions
- run again

If we finish the three tracks in this file properly, that bar is realistic.
