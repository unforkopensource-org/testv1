# Decibench v1.0 Launch Plan

Updated: 2026-04-14

Goal: make Decibench **9/10 against paid voice-agent QA platforms** and **10/10 against open-source alternatives**.

This file is the current execution source of truth. It replaces older snapshots that were stale after recent implementation work.

## Status At A Glance

### Current Verification Snapshot

Latest local verification:

| Check | Status | Evidence |
| --- | --- | --- |
| Ruff | **Passing** | `ruff check --no-cache src/ tests/` |
| Mypy | **Passing** | `Success: no issues found in 82 source files` |
| Tests | **Passing** | `138 passed in 18.55s` |
| Version alignment | **Done** | `1.0.0` across package/report defaults |
| Run store | **Done** | SQLite store with migrations/privacy path exists |
| Importers | **Partly done** | JSONL, Vapi, Retell |
| Imported-call evaluation | **Done** | CLI + API path exists |
| Regression generation | **Done** | Replay and API scenario generation exist |
| Basic API | **Done** | runs/calls/evaluate/scenario endpoints exist |
| Basic dashboard | **Done** | local serve + static dashboard exist |
| Packaging trust | **Partly done** | wheel/sdist contents verified; clean rebuild from this env still not proven |
| Live native media-path connectors | **Not done** | Vapi/Retell connector initiation exists, audio bridge does not |

### Current Honest Standing

- Open-source position: **strong, but not final**
- Paid-platform parity: **improving, but still behind**
- Brutal summary: Decibench is now a serious open-source product foundation, but it is **not yet the finished category leader**

## Ultimate Goal

Decibench v1.0 should feel like this:

1. A developer can install it cleanly, run it locally, and trust the output.
2. A team can use it in CI to block bad deploys.
3. An organization can import production calls, evaluate them, turn failures into regressions, and inspect them locally without SaaS lock-in.
4. A QA or product person can use the local UI/API without reading the source code first.
5. A platform team can extend it with scenario packs, connectors, evaluators, and custom workflows.

The end-state is not “a benchmark script.” It is:

> The open, local-first, CI-native, self-hostable reliability stack for voice agents.

For v1.0 to deserve the target rating:

- **10/10 open-source** means easiest to audit, extend, self-host, and automate.
- **9/10 vs paid** means it covers most of the real reliability loop even if it does not ship every enterprise control or hosted workflow.

## The Product Loop We Must Fully Support

1. Simulate before deploy.
2. Run in CI before merge or release.
3. Import production calls.
4. Evaluate imported calls.
5. Convert failures into regression scenarios.
6. Replay regressions.
7. Inspect runs and calls in a local API/UI.
8. Export evidence for teams and pipelines.

If any link above is weak, the launch is not done.

## What Is Already Done

### 1. Core Product Spine

- [x] Version aligned to `1.0.0`
- [x] `CallTrace` model
- [x] SQLite-backed local store
- [x] Run persistence by default
- [x] `decibench run`, `runs`, `replay`, `doctor`
- [x] JSONL import path
- [x] Replay-to-regression scenario generation
- [x] `.gitignore`
- [x] `py.typed`

### 2. Store v2 Foundation

- [x] schema versioning path
- [x] migration runner
- [x] normalized v2 tables for run/call detail
- [x] privacy redaction layer
- [x] safer default store-path behavior
- [x] `DECIBENCH_STORE_PATH` override

Why it matters:

- This is the product spine for the API, dashboard, regression workflows, and future trends.
- The safer store-path logic removes a real reliability bug in locked-down environments.

### 3. Imported Production Loop

- [x] `decibench import jsonl`
- [x] native Vapi importer
- [x] native Retell importer
- [x] imported-call evaluator service
- [x] `decibench evaluate-calls`
- [x] replay-to-scenario flow
- [x] failure-to-regression foundation

Why it matters:

- Decibench is no longer only pre-deploy synthetic testing.
- It now has a real production-call analysis loop.

### 4. API And Local Surface Area

- [x] `decibench serve`
- [x] basic FastAPI app
- [x] basic local dashboard
- [x] `GET /health`
- [x] `GET /runs`
- [x] `GET /runs/{id}`
- [x] `GET /calls`
- [x] `GET /calls/{id}`
- [x] `GET /calls/{id}/scenario`
- [x] `GET /calls/{id}/evaluate`

Why it matters:

- The product is no longer CLI-only.
- The replay loop is now callable by the UI and by other tools.

### 5. Reporting And CI Foundations

- [x] JUnit reporter
- [x] score/failure gate path in `run`
- [x] CI workflow file exists
- [x] HTML/JSON/Markdown/Rich/CI reporting paths exist

### 6. Quality Gate

- [x] Ruff clean
- [x] Mypy clean
- [x] Full tests passing

This is a major milestone. The repo now passes its own gate again.

### 7. Package Asset Verification

- [x] Existing wheel contains `py.typed`
- [x] Existing wheel contains bundled scenario YAML
- [x] Existing sdist contains bundled scenario YAML
- [x] Offline smoke from installed wheel path worked for scenario listing outside repo tree

Important honesty:

- We **did not** prove a clean rebuild from this exact environment because `hatchling` is not installed locally and isolated build resolution is blocked by offline/network restrictions.
- That is not the same as “packaging is broken,” but it is **not fully closed** either.

## What Remains

The old plan treated many already-shipped things as undone. That is no longer useful. The remaining work below is the real backlog in the best order.

## Remaining Work In Best Order

## Phase 1: Reproducible Packaging And Install Trust

Priority: **blocker before launch**

Current state:

- Existing wheel/sdist artifacts look good.
- Package assets are present.
- Offline wheel smoke partially worked.
- Clean rebuild from current env is still unverified.

Remaining work:

- [ ] Make local build reproducible from a clean environment.
- [ ] Ensure `hatchling`/build tooling is available in the dev path or document the exact build command.
- [ ] Verify wheel install in a fresh venv with dependencies resolved.
- [ ] Verify `decibench --help`, `scenario list`, `run --target demo` from installed package outside source tree.
- [ ] Confirm source distribution excludes junk: `.venv`, caches, `results`, `.decibench`, local DBs.

Best steps:

1. Make package build deterministic on a clean machine.
2. Rebuild wheel and sdist.
3. Inspect contents.
4. Install into a fresh venv outside the repo.
5. Run smoke commands from `/tmp`.
6. Document install + smoke steps in the release checklist.

Definition of done:

- A new user can install and run Decibench without depending on the repo checkout.

## Phase 2: CI Workflow Hardening

Priority: **blocker before launch**

Current state:

- `.github/workflows/ci.yml` exists.
- It runs lint/type/tests/build/smoke in principle.

Remaining work:

- [ ] Verify the workflow matches the real verified commands.
- [ ] Fix any drift between local truth and CI truth.
- [ ] Remove or justify commands that depend on missing plugins or undeclared deps.
- [ ] Ensure package smoke path uses the built wheel and runs outside the source tree.

Important note:

- The current CI file should be reviewed carefully before release. It contains more ambition than verified reality.

Best steps:

1. Align CI commands with the exact commands used in local verification.
2. Add matrix only for versions with confirmed dependency support.
3. Keep provider/network tests opt-in.
4. Make the build/install smoke part of required checks.

Definition of done:

- Every PR and release gets the same gate we trust locally.

## Phase 3: Live Native Connectors That Actually Work End To End

Priority: **highest product gap**

Current state:

- Demo, WebSocket, HTTP, and exec connectors exist.
- Vapi and Retell connectors exist.
- Vapi and Retell can initiate web calls.
- Vapi and Retell do **not** yet implement actual audio/event media bridging.

This is the biggest gap between Decibench and paid platforms.

Remaining work:

- [ ] Implement actual end-to-end live media path for at least one major platform.
- [ ] Decide whether v1.0 ships:
  - a real Vapi bridge, or
  - a real Retell bridge, or
  - both
- [ ] Replace `NotImplementedError` media stubs with working send/receive flow.
- [ ] Add mocked unit tests plus guarded integration tests.
- [ ] Document supported target formats and limits clearly.

Best steps:

1. Pick one platform to finish first.
2. Build the audio/event bridge around the real platform transport.
3. Add robust error handling and capability metadata.
4. Add integration tests behind opt-in env flags.
5. Only then broaden to the second platform.

Definition of done:

- A developer can run a real pre-deploy test against a native Vapi or Retell target without writing glue code.

## Phase 4: Persist Imported-Call Evaluation Results

Priority: **critical**

Current state:

- Imported calls can be evaluated by CLI and API.
- Regression scenarios can be generated.
- Evaluation results are returned, but the “store as first-class imported evaluation history” loop is still thin.

Remaining work:

- [ ] Persist imported-call evaluation results, not only compute them on request.
- [ ] Add filters for failed-only, source, since, score threshold, category.
- [ ] Add explicit linkage:
  - call trace -> evaluation result
  - evaluation result -> generated regression scenario
- [ ] Add export path for imported-call evaluations.

Why it matters:

- Without persistence, production analysis does not turn into trends or repeatable triage.

Definition of done:

- A team can revisit past imported-call evaluations without re-running them every time.

## Phase 5: Dashboard From Browser To Workbench

Priority: **high**

Current state:

- Basic dashboard exists.
- API endpoints exist.

Remaining work:

- [ ] Add real filtering and search.
- [ ] Add failure-first views.
- [ ] Add per-call detail screen.
- [ ] Add per-run detail screen.
- [ ] Add “evaluate trace” action in UI.
- [ ] Add “generate regression scenario” action in UI.
- [ ] Show evaluation summary and failed categories.
- [ ] Make the UI stable and usable for non-engineers.

Definition of done:

- A product or QA teammate can inspect failures without opening the database or running multiple commands manually.

## Phase 6: Observability And Trace Timeline

Priority: **high**

Current state:

- Span models exist.
- Store tables for spans exist.

Remaining work:

- [ ] Capture richer spans consistently across flows.
- [ ] Expose spans in API/UI.
- [ ] Add latency timeline and turn timeline views.
- [ ] Add top-level metrics for:
  - turn latency
  - time to first response
  - tool latency
  - interruption recovery
  - silence/repetition
- [ ] Add export path for traces/spans.

Why it matters:

- Paid tools win because they make failures explainable, not just scorable.

Definition of done:

- Decibench can explain where a call failed, not only say that it failed.

## Phase 7: Scenario Standard v1

Priority: **high**

Current state:

- Scenario models exist.
- Bundled suites exist.
- Regression generation exists.
- JSON Schema path exists in CLI.

Remaining work:

- [ ] Finalize schema versioning story.
- [ ] Tighten validation and normalization.
- [ ] Add documented regression conventions.
- [ ] Improve persona/noise/accent/timeout semantics.
- [ ] Add interruption and DTMF support if feasible for v1.
- [ ] Add `scenario explain` / `scenario normalize` if they still materially help users.

Definition of done:

- Scenario YAML is stable enough to be the ecosystem contract.

## Phase 8: Importer Hardening And Expansion

Priority: **medium-high**

Current state:

- JSONL, Vapi, and Retell exist.

Remaining work:

- [ ] Harden pagination/retries/rate-limit handling.
- [ ] Improve platform-specific parsing fidelity.
- [ ] Add better docs and clearer auth setup.
- [ ] Add ElevenLabs importer if needed for launch claim coverage.

Definition of done:

- Imported traces are not just “good enough for demos”; they are reliable enough for teams.

## Phase 9: Load Testing And Red-Team Packs

Priority: **medium**

Current state:

- Not launch-complete.

Remaining work:

- [ ] Add curated adversarial suites.
- [ ] Add load/concurrency workflow.
- [ ] Add safety and robustness packs.

Reality check:

- This is valuable, but it should not block finishing package trust, CI, live media-path connectors, and persistent imported-call evaluations.

## Phase 10: Plugin And Extension Story

Priority: **medium**

Current state:

- The architecture is extension-friendly, but the explicit plugin experience is not yet a finished product.

Remaining work:

- [ ] Document extension points.
- [ ] Stabilize connector/importer/evaluator interfaces.
- [ ] Decide whether plugin registry ships in v1.0 or v1.1.

Definition of done:

- External contributors can extend Decibench without reading the whole codebase first.

## Phase 11: Documentation And Launch UX

Priority: **blocker before public positioning**

Remaining work:

- [ ] Rewrite docs to match actual product truth.
- [ ] Add installation guide.
- [ ] Add “quick start” for demo run.
- [ ] Add “import production calls” guide.
- [ ] Add “evaluate and convert to regression” guide.
- [ ] Add self-host/API/dashboard guide.
- [ ] Add honest limitations section.
- [ ] Clean naming/typos in repo docs.

Definition of done:

- A new user understands what works, what is partial, and how to succeed on the first try.

## What Is Done Enough For v1.0

The following are now real enough to count:

- local store
- import/replay foundation
- imported-call evaluation
- regression scenario generation
- basic API
- basic dashboard
- JUnit/reporting
- strict quality gate

## What Is Not Done Enough For v1.0 Yet

These are the real remaining launch risks:

- reproducible clean build/install from scratch
- CI truth alignment
- real native live media-path connector support
- persistent imported-call evaluation history
- dashboard/workbench depth
- trace/timeline observability depth
- final docs truthfulness and polish

## Exact Next Sprint

If work starts again tomorrow, do it in this order:

1. Close reproducible packaging/build from a clean env.
2. Make CI match the real verified commands exactly.
3. Pick one native live platform and finish its real media path.
4. Persist imported-call evaluation results.
5. Wire those stored evaluations into API and dashboard views.
6. Tighten docs and launch checklist.

## Launch Acceptance Test

Decibench is ready to call v1.0 only when all of the following are true:

- [x] Ruff passes.
- [x] Mypy passes.
- [x] Tests pass.
- [x] Run store exists and is stable.
- [x] Production calls can be imported.
- [x] Imported calls can be evaluated.
- [x] Imported calls can become regression scenarios.
- [x] API can expose runs and calls.
- [x] API can expose imported-call evaluation and scenario generation.
- [x] Package artifacts contain `py.typed` and bundled scenarios.
- [ ] Clean rebuild is reproducible from a fresh environment.
- [ ] Clean install is proven from a fresh venv with dependencies.
- [ ] CI gate is verified and trustworthy.
- [ ] At least one native live platform connector works end to end.
- [ ] Imported-call evaluations are stored and queryable as first-class data.
- [ ] Dashboard supports real triage, not just browsing.
- [ ] Docs are launch-quality and truthful.

## Launch Rating Criteria

### To earn 10/10 open-source

Decibench must be:

- easier to install than open alternatives
- easier to audit than closed platforms
- easier to extend than most internal tools
- fully usable without a hosted backend
- trustworthy in CI and self-hosted workflows

### To earn 9/10 against paid platforms

Decibench must cover enough of the reliability loop that a serious team can use it for:

- pre-deploy testing
- CI gating
- production import
- production evaluation
- regression generation
- local inspection and triage

without feeling forced into a SaaS product.

## Final Brutal Read

Decibench is no longer “just a prototype.” The repo is materially stronger than the previous plan implied.

But the launch is **not finished** until the remaining gaps above are closed, especially:

1. clean build/install trust
2. CI trust
3. real native live media-path support
4. persistent imported-call evaluation history
5. better dashboard/observability depth

That is the shortest honest path from “strong open-source project” to “best-in-class open-source voice-agent QA platform.”
