# Current Bugs

This is a grounded bug ledger for the current Decibench codebase.

It focuses on issues that either:

- already failed in real runtime testing, or
- are clearly miswired in code and likely to fail in real usage

Status date: 2026-04-16

## Highest Priority

### 1. Imported-call semantic judging is wired to the model name, not the judge provider

**Severity:** P1  
**Status:** confirmed by code inspection  
**Impact:** any imported-call evaluation path that enables semantic judging is likely broken

#### Where

- `src/decibench/api/app.py:68-77`
- `src/decibench/cli/evaluate_cmd.py:43-62`
- `src/decibench/providers/registry.py:154-161`

#### Why this is a bug

Both imported-call entry points construct the judge like this:

```python
judge = get_judge(config.providers.judge_model)
```

But `get_judge()` resolves by **provider URI / scheme**, not by model name.

That means values like:

- `gpt-5-mini`
- `claude-sonnet-4-20250514`
- `gemini-2.5-flash`

are treated as provider schemes, which do not exist in the judge registry.

The benchmark orchestrator does this correctly:

```python
get_judge(
    config.providers.judge,
    model=config.providers.judge_model,
    api_key=config.providers.judge_api_key,
    ...
)
```

The imported-call flows do not.

#### Likely symptom

- semantic imported-call evaluation fails outright
- or silently falls back to no judge if wrapped upstream

#### Fix direction

Make API and `evaluate-calls` construct the judge exactly the way
`Orchestrator.run_suite()` does.

---

### 2. Connector config plumbing is broken: only `[auth]` reaches connectors

**Severity:** P1  
**Status:** confirmed by code inspection and consistent with runtime behavior  
**Impact:** connector customization is effectively broken or undocumented

#### Where

- `src/decibench/orchestrator.py:300-302`
- `src/decibench/connectors/websocket.py:67-72`
- `src/decibench/connectors/http.py:46-57`
- `src/decibench/cli/_config_file.py:54-56`

#### Why this is a bug

The orchestrator passes this into every connector:

```python
auth_config = self._config.auth.model_dump()
handle = await connector.connect(target, auth_config)
```

So connectors only receive the `[auth]` section.

But connectors read settings that are **not** part of the normal generated auth
shape:

- WebSocket connector expects:
  - `websocket_headers`
  - `sample_rate`
- HTTP connector expects:
  - `http_headers`
  - `auth_token`

At the same time, the generated config writes sample rate under `[audio]`:

```toml
[audio]
sample_rate = 16000
```

That means the generated config suggests a connector-control value exists, but
the connector never receives it through normal plumbing.

#### Real consequence

This likely contributes directly to the current WebSocket mismatch:

- user endpoint needs a specific sample rate or control data
- connector has a hardcoded default
- config override path does not actually reach the connector

#### Fix direction

Introduce a typed connector config surface and pass it explicitly, instead of
reusing `[auth]` as the whole connector configuration channel.

---

### 3. Generic WebSocket connector is too narrow for the “universal connector” claim

**Severity:** P1  
**Status:** confirmed by runtime against a real local endpoint  
**Impact:** many real WebSocket agents will connect successfully but fail at turn execution

#### Where

- `src/decibench/connectors/websocket.py:43-45`
- `src/decibench/connectors/websocket.py:96-112`
- `src/decibench/connectors/websocket.py:114-136`

#### Why this is a bug

The current connector:

- defaults to `24000` Hz
- sends only raw binary PCM chunks
- does not send any explicit end-of-turn / commit message
- assumes the agent either:
  - starts responding automatically after raw audio ends, or
  - can be inferred from silence/timeouts

That is too narrow for many real protocols, which often require:

- 16 kHz instead of 24 kHz
- JSON envelopes around audio
- explicit caller-turn commit
- separate setup/auth/session messages

#### Confirmed runtime behavior

Against a real local endpoint at `ws://127.0.0.1:8000/ws`:

- TCP connect worked
- WebSocket connect worked
- ping/pong worked
- Decibench run failed with:
  - `received 1011 (internal error) keepalive ping timeout`

Manual probing showed the server stayed alive after raw binary frames, but
Decibench never got a usable response flow.

#### Fix direction

The generic WebSocket connector needs either:

1. a configurable protocol layer
2. explicit turn-finalization hooks
3. profile-specific adapters for common WebSocket voice protocols

The current implementation is too opinionated to be called universal.

## Medium Priority

### 4. `bridge doctor` can hang indefinitely on Playwright verification

**Severity:** P2  
**Status:** confirmed by runtime  
**Impact:** local UX freezes during bridge readiness checks

#### Where

- `src/decibench/cli/bridge.py:55-65`

#### Why this is a bug

`bridge doctor` runs:

```python
subprocess.run(
    ["npx", "playwright", "--version"],
    capture_output=True,
    text=True,
    check=False,
)
```

There is no timeout.

In real testing, this command stalled instead of returning promptly. That means
`bridge doctor` can hang even though it is supposed to be a quick readiness
check.

#### Fix direction

- add a timeout
- treat timeout as `WARN`
- avoid commands that may trigger install-like behavior during doctor checks

---

### 5. `bridge install` assumes an npm-published bridge and ignores the local sidecar path

**Severity:** P2  
**Status:** confirmed by code inspection  
**Impact:** native-bridge setup is fragile in source-checkout or pre-publish workflows

#### Where

- `src/decibench/cli/bridge.py:32-40`
- `src/decibench/bridge/client.py:80-105`

#### Why this is a bug

The CLI install flow assumes:

```bash
npm install -g decibench-bridge
```

But the bridge runtime itself already supports another path:

- use `decibench-bridge` on `PATH`, or
- use an in-repo built `bridge_sidecar/dist/server.js`

The CLI bootstrap does not take advantage of that fallback. So source users can
be in an awkward state where:

- the repo contains the sidecar source
- the Python bridge client knows how to use a built local `dist/server.js`
- but `decibench bridge install` still only tries the global npm path

#### Fix direction

Make `bridge install` smart enough to:

- detect local checkout mode
- build `bridge_sidecar/` locally when appropriate
- then install Playwright Chromium

---

### 6. Store and workbench behavior drift with the current working directory

**Severity:** P2  
**Status:** confirmed by code inspection and runtime behavior  
**Impact:** users can run tests and then open an apparently empty workbench, or update the wrong config/store

#### Where

- `src/decibench/store/sqlite.py:21-31`
- `src/decibench/api/app.py:63-65`
- `src/decibench/cli/serve.py:9-24`
- `src/decibench/cli/evaluate_cmd.py:42-45`
- `src/decibench/cli/models.py:90-92`

#### Why this is a bug

The default store path depends on `Path.cwd()`:

```python
root = base_dir or Path.cwd()
return root / ".decibench" / "decibench.sqlite"
```

That means store location changes with the shell directory.

The local API always opens:

```python
RunStore(default_store_path())
```

and `serve` does not accept a `--store` option.

`evaluate-calls` also hardcodes:

```python
config = load_config(Path("decibench.toml"))
store = RunStore()
```

and `models use/preset` writes `Path.cwd() / "decibench.toml"`.

#### Real consequence

The following all depend on where the user happens to be standing:

- which SQLite DB gets read
- which config file gets read
- which config file gets overwritten
- what the workbench sees

That makes the product feel inconsistent even when the code is technically
working.

#### Fix direction

Anchor store/config resolution to:

- the discovered project root, or
- explicit `--config` / `--store` options propagated consistently

---

### 7. API evaluation endpoint mutates state on `GET`

**Severity:** P2  
**Status:** confirmed by code inspection  
**Impact:** refreshes, prefetching, or crawlers can trigger new stored evaluations unexpectedly

#### Where

- `src/decibench/api/app.py:233-243`

#### Why this is a bug

This endpoint is declared as:

```python
@app.get("/calls/{call_id}/evaluate")
```

but it also persists data:

```python
result = await evaluator.evaluate_trace(trace)
get_store().save_call_evaluation(trace, result)
```

That violates normal HTTP expectations for `GET`, which should be safe and
non-mutating.

#### Fix direction

Change it to `POST` and keep `GET /calls/{call_id}/evaluation` as the
read-only retrieval endpoint.

---

### 8. API pagination is wrong: `skip` is applied after SQL `LIMIT`

**Severity:** P2  
**Status:** confirmed by code inspection  
**Impact:** later pages can be incomplete or empty even when more rows exist

#### Where

- `src/decibench/api/app.py:139-142`
- `src/decibench/api/app.py:155-162`

#### Why this is a bug

The API does:

```python
return get_store().list_runs(limit=limit)[skip:]
return get_store().list_call_traces(limit=limit, ...)[skip:]
```

So it fetches only `limit` rows from the DB, then slices in memory.

Example:

- request page 2 with `limit=50&skip=50`
- store fetches only the first 50 rows
- slicing `[50:]` returns empty

#### Fix direction

Push `skip`/offset into the store SQL query instead of slicing after the fact.

## Lower Priority but Real

### 9. Keyring “availability” only checks importability, not a usable backend

**Severity:** P3  
**Status:** confirmed by code inspection  
**Impact:** `doctor` can report PASS while `auth set` still fails on some machines

#### Where

- `src/decibench/secrets.py:44-54`
- `src/decibench/secrets.py:80-90`
- `src/decibench/cli/auth.py:27-39`

#### Why this is a bug

Current keyring readiness is:

```python
def keyring_available() -> bool:
    return _keyring is not None
```

That only proves the module imported.

It does **not** prove:

- a backend is configured
- reads work
- writes work

`auth set` then calls `store_secret()` directly and does not convert backend
failures into a friendly `ClickException`.

#### Fix direction

Probe keyring usability, not just importability, and catch backend-specific
errors in CLI flows.

---

### 10. `decibench run` exits 0 even when every scenario failed due to configuration/runtime setup errors

**Severity:** P3  
**Status:** confirmed by runtime  
**Impact:** automation and users can mistake a fully broken run for a successful command

#### Where

- `src/decibench/cli/run.py:225-288`

#### Why this is a bug

The command only exits nonzero when a fail gate is explicitly enabled:

- `--fail-under`
- `--exit-code-on-fail`
- `--fail-on`

In runtime testing:

```bash
decibench run --target retell://... --suite quick
```

returned exit code `0` even though every scenario failed immediately because
`RETELL_API_KEY` was missing.

#### Fix direction

Return nonzero automatically when:

- all scenarios fail due to execution/configuration errors, or
- connector initialization fails before any meaningful evaluation begins

## Coverage Gaps Worth Closing

These are not bugs by themselves, but they explain why the above issues were
able to survive.

### Missing or weak coverage areas

1. imported-call semantic judging through both:
   - API evaluate endpoint
   - `evaluate-calls` CLI

2. end-to-end generic WebSocket behavior against a server that requires:
   - 16 kHz
   - explicit end-of-turn
   - JSON envelopes

3. bridge doctor/install behavior when:
   - Playwright is missing
   - `npx` stalls
   - `decibench-bridge` is not on PATH
   - repo checkout is used instead of npm install

4. cwd drift across:
   - `run`
   - `serve`
   - `evaluate-calls`
   - `models use`

## What I Would Fix First

If the goal is to stabilize real-world usage quickly, the best order is:

1. fix judge construction in API and `evaluate-calls`
2. fix connector config plumbing
3. redesign or profile the generic WebSocket connector
4. fix bridge doctor/install UX
5. anchor store/config resolution to project root, not shell cwd
6. fix GET-with-side-effects and API pagination

That order attacks the highest user-visible breakpoints first.
