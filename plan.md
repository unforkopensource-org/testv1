# Decibench Local Product UX Plan

Updated: 2026-04-16

## 1. Purpose

This plan replaces the previous roadmap completely.

The next Decibench push is not about adding random new engine features. It is
about turning the existing codebase into a local-first product that a developer
or team can install, configure, trust, and use without reading the source.

This document defines the exact UX, architecture, distribution model, provider
strategy, and implementation order for that work.

## 2. Product Stance

Decibench is:

- local-first
- terminal-first
- open-source
- GitHub-first
- self-hosted on the user's own machine
- optionally enhanced by a local browser workbench

Decibench is not:

- a hosted SaaS
- a cloud account system
- an OAuth login product for model vendors
- a product that stores user API keys in Decibench servers
- a product that requires users to hand-edit secrets into config files

The target experience is:

1. install the CLI
2. run one setup command
3. paste keys locally if semantic judging is desired
4. pick a provider and model
5. run a suite
6. open the local workbench

## 3. Current Foundation Already Implemented

This plan starts from a real platform, not a blank page. The current codebase
already has the foundations that matter:

- strict code quality gates
- persistent local store and migrations
- imported-call ingestion
- evaluation and replay
- regression scenario generation
- local API
- local workbench
- native bridge architecture
- docs-truth validation

That means the right next move is not deeper infra. The right next move is
better first-run UX, setup trust, provider setup, and local product polish.

## 4. North Star Outcome

For v1.0, a new user should be able to do this without guesswork:

```bash
pipx install decibench
decibench doctor
decibench init
decibench run --target demo --suite quick
decibench serve
```

If they want semantic evaluation:

```bash
decibench auth set openai
decibench models use openai gpt-5-mini
decibench run --target demo --suite quick
```

If they want native browser-bridge connectors:

```bash
decibench bridge install
decibench doctor
decibench run --target retell://agent_id --suite quick
```

The product should feel like one coherent local tool, not a Python package plus
some docs plus a sidecar plus guesswork.

## 5. Product Principles

### 5.1 Local-first secret handling

- User pastes API keys locally.
- Keys are stored in the OS keychain/keyring by default.
- `decibench.toml` stores configuration, not raw secrets.
- Environment variable fallback is supported.
- Plain-text secrets in config are allowed only as an explicit escape hatch with
  a warning.

### 5.2 Deterministic-first, semantic-optional

- A user must be able to get value without any model account at all.
- Semantic judging is an optional upgrade path, not a startup blocker.
- The CLI should clearly distinguish:
  - deterministic mode
  - semantic mode

### 5.3 Opinionated defaults, manual escape hatch

- Decibench should ship curated default models.
- Decibench should fetch live model lists when keys exist.
- Decibench should always allow manual custom model entry.

### 5.4 Terminal-first, local workbench second

- Primary onboarding happens in the terminal.
- The browser workbench is launched locally by the CLI.
- The UI is a local analysis surface, not the product's identity.

### 5.5 Product truth over marketing

- Docs must reflect what is actually implemented.
- Commands must explain what they are doing.
- Status levels must be explicit: `shipped`, `beta`, `experimental`, `planned`.

## 6. Distribution Architecture

## 6.1 Source of truth

- GitHub repository is the canonical source.
- GitHub Releases are the canonical release history.
- Release notes must map to real shipped capabilities.

## 6.2 Python distribution

Primary distribution target:

- PyPI package: `decibench`

Primary install UX:

```bash
pipx install decibench
```

Why:

- `pipx` is the cleanest user-facing install path for a Python CLI
- it keeps dependencies isolated
- it matches the local-tool positioning better than asking users to manage a
  project virtualenv just to try the product

Interim fallback:

```bash
pipx install git+https://github.com/unforkopensource-org/testv1.git
```

That fallback is acceptable while PyPI is not published, but it is not the
final polished path.

## 6.3 Native bridge distribution

Primary distribution target:

- npm package: `decibench-bridge`

The bridge remains a separate distributable because:

- it needs Node.js
- it needs Playwright/Chromium
- it is not appropriate to hide browser automation inside a pure Python wheel

But the user should not have to think in npm terms during normal setup.

Decibench must provide a first-class wrapper command:

```bash
decibench bridge install
```

That command owns the bridge bootstrap UX.

## 6.4 Release channels

Required channels:

- GitHub source repo
- GitHub Releases
- PyPI for `decibench`
- npm for `decibench-bridge`

Optional later:

- Homebrew formula

Not required for v1.0.

## 7. Configuration and Secret Architecture

## 7.1 Config file

Project-local config file:

- `decibench.toml`

This file should store:

- project settings
- target URI
- suite settings
- judge provider
- judge model
- provider base URL when needed
- local workbench/API settings
- bridge behavior flags

This file should not store raw secrets by default.

## 7.2 Secret storage

Primary secret backend:

- system keyring/keychain via Python `keyring`

Fallback:

- environment variables

Explicit escape hatch:

- plain-text config secret only if the user deliberately opts into it and the
  CLI warns them

Recommended service naming:

- `decibench/openai/default`
- `decibench/anthropic/default`
- `decibench/gemini/default`

## 7.3 Auth command UX

Required command surface:

```bash
decibench auth set openai
decibench auth set anthropic
decibench auth set gemini
decibench auth list
decibench auth test openai
decibench auth remove openai
```

Behavior for `auth set`:

1. prompt for API key with hidden input
2. store in keyring by default
3. optionally verify connectivity
4. optionally ask whether to set this provider as the semantic judge default

Behavior for `auth list`:

- show providers configured
- do not print secrets
- show where the secret is coming from:
  - keyring
  - env var
  - config file

Behavior for `auth test`:

- validate the secret exists
- validate the provider endpoint is reachable
- optionally list one or more models

## 8. LLM Provider and Model Architecture

Initial semantic judge providers for v1.0:

- OpenAI
- Anthropic
- Gemini

This is intentionally narrow. The goal is a clean product, not a huge provider
matrix on day one.

## 8.1 Provider API strategy

Each provider must support three layers:

1. curated built-in recommended models
2. live model listing if a key is configured
3. manual custom model entry

That gives the user the best balance between a smooth first run and full local
control.

## 8.2 Default model choices

These defaults are Decibench product defaults for semantic evaluation. They are
chosen for availability, price/performance, latency, and low-friction first-run
UX. They are not claims that these are the strongest models overall.

| Provider | Decibench default | Why this is the default | Higher-accuracy option | Budget option |
| --- | --- | --- | --- | --- |
| OpenAI | `gpt-5-mini` | best practical balance for evaluation and CI cost | `gpt-5.1` | `gpt-5-nano` |
| Anthropic | `claude-sonnet-4-20250514` | strong quality with better speed/cost balance than Opus | `claude-opus-4-1-20250805` | `claude-3-5-haiku-20241022` |
| Gemini | `gemini-2.5-flash` | current safe default for price/performance and broad availability | `gemini-2.5-pro` | `gemini-2.5-flash-lite` |

Important Gemini decision:

- Do not use `gemini-2.0-flash` as the default.
- Treat Gemini 2.0 models as legacy/manual-only.
- Prefer `gemini-2.5-flash` for the shipped default.

Reason:

- Google's current docs position Gemini 2.5 Flash as the best price/performance
  model.
- Google's deprecations page lists Gemini 2.0 Flash with `gemini-2.5-flash` as
  the recommended replacement.

## 8.3 Provider model listing

Required commands:

```bash
decibench models list openai
decibench models list anthropic
decibench models list gemini
decibench models use openai gpt-5-mini
decibench models use anthropic claude-sonnet-4-20250514
decibench models use gemini gemini-2.5-flash
```

Live listing sources:

- OpenAI: `GET /v1/models`
- Anthropic: `GET /v1/models`
- Gemini: `GET /v1beta/models`

If live listing fails:

- fall back to Decibench's curated model catalog
- clearly tell the user that the list is a local fallback, not a live fetch

## 8.4 Provider UX presets

For each provider, expose 3 preset intents:

- `balanced`
- `quality`
- `budget`

Example resolution:

- OpenAI
  - `balanced` -> `gpt-5-mini`
  - `quality` -> `gpt-5.1`
  - `budget` -> `gpt-5-nano`
- Anthropic
  - `balanced` -> `claude-sonnet-4-20250514`
  - `quality` -> `claude-opus-4-1-20250805`
  - `budget` -> `claude-3-5-haiku-20241022`
- Gemini
  - `balanced` -> `gemini-2.5-flash`
  - `quality` -> `gemini-2.5-pro`
  - `budget` -> `gemini-2.5-flash-lite`

This matters because most users do not actually want to memorize vendor model
names on first run.

## 9. CLI UX Architecture

The CLI needs to become the real product surface.

## 9.1 `decibench init`

`init` must become an interactive setup wizard.

Questions:

1. project name
2. target type
   - demo
   - websocket
   - process
   - http
   - retell native
   - vapi native
3. evaluation mode
   - deterministic only
   - semantic with model provider
4. semantic provider if chosen
   - openai
   - anthropic
   - gemini
5. whether to paste a key now
6. whether to use the recommended default model
7. whether to run a smoke test immediately

Outputs:

- writes `decibench.toml`
- optionally stores secrets in keyring
- prints exact next commands

`init` should not dump a long config template and walk away.

## 9.2 `decibench auth`

This is the secret-management entry point.

Required subcommands:

- `set`
- `list`
- `test`
- `remove`

The auth flow must feel safe and boring.

## 9.3 `decibench models`

This is the model-selection entry point.

Required subcommands:

- `list <provider>`
- `use <provider> <model>`
- `preset <provider> <balanced|quality|budget>`
- `current`

This command should update config, not mutate secrets.

## 9.4 `decibench doctor`

`doctor` must become the trust command.

It should check:

- Python version
- package version
- config presence and validity
- store path
- keyring availability
- configured providers
- provider key presence
- optional provider connectivity
- Node presence
- npm presence
- bridge install status
- Playwright browser presence
- local dashboard assets
- native connector readiness

Output must be structured:

- PASS
- WARN
- FAIL

Every FAIL must include the next command to fix it.

## 9.5 `decibench bridge`

Required subcommands:

- `install`
- `doctor`
- `version`

`bridge install` must:

1. detect Node and npm
2. install `decibench-bridge`
3. install Playwright browser dependencies
4. verify the bridge binary is runnable
5. report the installed version

The user should not have to remember separate npm and Playwright commands.

## 9.6 `decibench serve`

`serve` must remain local-only.

Required behavior:

- starts the local API and workbench
- prints a clean local URL
- does not pretend anything is remotely hosted
- detects missing dashboard assets and tells the user how to build or install
  them

Recommended output:

```text
Decibench workbench is running locally at:
http://127.0.0.1:8000

Use Ctrl+C to stop it.
```

Optional later:

- `--open`

Not required for the first UX pass.

## 10. Local Workbench Architecture

The workbench remains a local analysis tool launched by the CLI.

Keep the existing stack:

- FastAPI local backend
- Vue 3 frontend
- TypeScript
- Vite
- Tailwind
- TanStack Query

Do not turn the workbench into a hosted product.

Required UX goal:

- a user runs `decibench serve`
- opens the local URL
- inspects runs, calls, evaluations, and regressions locally

## 11. Exact User Flows to Implement

## 11.1 Flow A: zero-key first run

```bash
pipx install decibench
decibench doctor
decibench init
decibench run --target demo --suite quick
decibench serve
```

Expected experience:

- no provider account required
- no secret setup required
- user still reaches a meaningful success state

## 11.2 Flow B: semantic first run with OpenAI

```bash
pipx install decibench
decibench init
decibench auth set openai
decibench models preset openai balanced
decibench run --target demo --suite quick
decibench serve
```

Expected experience:

- prompt for key locally
- store in keyring
- default model becomes `gpt-5-mini`

## 11.3 Flow C: semantic first run with Anthropic

```bash
decibench auth set anthropic
decibench models preset anthropic balanced
decibench run --target demo --suite quick
```

Expected experience:

- prompt for key locally
- store in keyring
- default model becomes `claude-sonnet-4-20250514`

## 11.4 Flow D: semantic first run with Gemini

```bash
decibench auth set gemini
decibench models preset gemini balanced
decibench run --target demo --suite quick
```

Expected experience:

- prompt for key locally
- store in keyring
- default model becomes `gemini-2.5-flash`
- Gemini 2.0 is not suggested as a default

## 11.5 Flow E: native connector first run

```bash
pipx install decibench
decibench bridge install
decibench doctor
decibench init
decibench run --target retell://agent_id --suite quick
```

Expected experience:

- bridge setup is wrapped by the Decibench CLI
- user is not forced to manually stitch npm and Playwright steps together

## 12. Tech Stack Choices

These are the chosen implementation technologies for this UX push.

| Area | Chosen stack | Why |
| --- | --- | --- |
| CLI | Python + Click + Rich | already aligned with the codebase and good for interactive local UX |
| Config | TOML | readable, stable, existing project fit |
| Secret storage | Python `keyring` | best local-first user trust story |
| Provider HTTP | `httpx` | async/sync friendly, clean API |
| Local API | FastAPI | already in use |
| Workbench UI | Vue 3 + TS + Vite + Tailwind + TanStack Query | already in use and appropriate |
| Native bridge | Node 20 + TypeScript + Playwright + Chromium | right toolchain for browser SDK automation |
| Python packaging | PyPI + `pipx` | best UX for a CLI product |
| Bridge packaging | npm | right distribution channel for the sidecar |
| Releases | GitHub Releases | canonical public release surface |

## 13. Step-by-Step Implementation Order

## Phase 1: auth foundation

Build:

- keyring-backed secret store
- `decibench auth set/list/test/remove`
- provider key validation

Done when:

- no raw key is required in `decibench.toml`
- a user can store and test OpenAI, Anthropic, and Gemini keys locally

## Phase 2: model catalog and provider defaults

Build:

- curated model catalog for OpenAI, Anthropic, Gemini
- `decibench models list`
- `decibench models use`
- `decibench models preset`

Done when:

- recommended defaults resolve correctly
- live listing works when keys are present
- manual custom model entry remains possible

## Phase 3: `init` wizard

Build:

- interactive project setup
- semantic vs deterministic selection
- provider + model selection
- optional auth handoff during setup

Done when:

- a first-time user can reach a valid `decibench.toml` without hand-editing it

## Phase 4: `doctor` as the trust command

Build:

- richer environment checks
- provider readiness checks
- bridge readiness checks
- actionable remediation output

Done when:

- a new user can run `decibench doctor` and know exactly what is broken and how
  to fix it

## Phase 5: bridge UX wrapper

Build:

- `decibench bridge install`
- `decibench bridge doctor`
- bridge version detection

Done when:

- a user can bootstrap native bridge support from the CLI without reading
  separate npm and Playwright instructions

## Phase 6: `serve` and workbench polish

Build:

- clearer local launch output
- clean handling of missing assets
- stronger local-only messaging

Done when:

- the workbench launch feels like a product command, not a dev-server command

## Phase 7: release and docs truth

Build:

- README rewritten around real local-first flows
- install docs for `pipx`
- bridge install docs aligned with CLI wrapper
- provider setup docs aligned with auth/model commands
- release notes and support matrix updated

Done when:

- the README matches the CLI exactly
- the docs do not require users to infer hidden setup steps

## 14. Definition of Done for This UX Push

This plan is done only when all of the following are true:

1. a new user can install Decibench with `pipx`
2. a new user can set up semantic evaluation without editing secrets into config
3. OpenAI, Anthropic, and Gemini all work through the same UX shape
4. Gemini defaults to `gemini-2.5-flash`, not Gemini 2.0
5. `decibench init` is interactive and useful
6. `decibench doctor` is actionable
7. `decibench bridge install` hides the bridge bootstrap complexity
8. `decibench serve` launches the local workbench cleanly
9. README, help text, and release docs all match the shipped behavior

## 15. What Is Explicitly Out of Scope for This Plan

Not in scope for this pass:

- hosted Decibench cloud
- browser login/account system
- OAuth login to OpenAI, Anthropic, or Google
- storing secrets in Decibench-owned infrastructure
- exploding the provider matrix beyond OpenAI, Anthropic, and Gemini
- adding unrelated new evaluators before the first-run UX is clean
- rewriting the core engine just to support the UX work

## 16. Final Product Positioning After This Plan

If this plan is implemented correctly, Decibench should feel like this:

> A serious local voice-agent testing product that installs like a CLI, stores
> secrets safely, lets the user choose deterministic or semantic evaluation,
> supports OpenAI, Claude, and Gemini out of the box, and launches a local
> workbench without any hosted dependency.

That is the right v1.0 story.

## 17. Model Decision Notes

The default model decisions in this plan were checked against official provider
docs on 2026-04-16.

Important notes:

- OpenAI docs currently present GPT-5 family models prominently, and `gpt-5-mini`
  is the strongest practical default for cost-sensitive evaluation workflows.
- Anthropic docs list `claude-sonnet-4-20250514` as the balanced Claude Sonnet 4
  API model name, while `claude-opus-4-1-20250805` is the premium accuracy tier.
- Google Gemini docs position `gemini-2.5-flash` as the best price/performance
  model, and the deprecations page recommends `gemini-2.5-flash` as the
  replacement for Gemini 2.0 Flash.

Those facts should be encoded in the product, not left as tribal knowledge.
