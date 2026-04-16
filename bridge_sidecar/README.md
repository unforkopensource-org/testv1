# decibench-bridge

Native voice-agent bridge sidecar for [Decibench](https://github.com/decibench/decibench).

The sidecar runs the **official browser SDK** for a target voice platform
(Retell, Vapi, ...) inside a headless Chromium controlled by Playwright, and
exposes that browser session to Decibench's Python orchestrator over a small
local WebSocket using the protocol defined in
[`docs/bridge-protocol.md`](../docs/bridge-protocol.md).

## Status

**Experimental.** The protocol contract is frozen for v1.0; the Retell and
Vapi adapters are wired but not yet covered by an end-to-end CI run against
real vendor accounts. Use `ws://` connectors with raw vendor WebSocket
endpoints for now.

## Why a sidecar

Native Vapi and Retell calls run on vendor-managed WebRTC stacks (Daily.co
and LiveKit respectively). The supported integration path is the official
**browser** SDK. Re-implementing the WebRTC wire protocol in Python would be
high-risk reverse engineering. Running the official SDK inside headless
Chromium gives Decibench:

- the same flow vendors test against,
- transcript/tool-call/event surfaces the SDK already exposes, and
- a single bridge architecture that future platforms can reuse.

## Install (development)

```bash
cd bridge_sidecar
npm install
npx playwright install chromium
npm run build
```

The Python `BridgeClient` will then auto-discover `dist/server.js` when
`decibench-bridge` is not on `PATH`.

For end users who install via pip:

```bash
npm install -g decibench-bridge
npx playwright install chromium
```

## Process / wire model

```
Python (decibench)  <—— local WebSocket —— Node sidecar  ←— Playwright —→  Chromium  ←— browser SDK —→  vendor
```

- Listens on `127.0.0.1`. Port = `DECIBENCH_BRIDGE_PORT` (default `0` → ephemeral).
- Prints exactly one line on stdout: `BRIDGE_LISTENING port=<n>`.
- Everything else goes to stderr as one JSON object per line.
- Single client per process; the Python connector spawns one sidecar per call.

See `docs/bridge-protocol.md` for the full message schema.

## Run

```bash
DECIBENCH_BRIDGE_PORT=0 node dist/server.js
```

You'll see `BRIDGE_LISTENING port=12345` on stdout. Connect a Decibench
Python orchestrator (or any WebSocket client speaking the protocol) to
`ws://127.0.0.1:12345/`.
