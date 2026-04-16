# Decibench Native Bridge Protocol

Status: **v1 (Experimental)** — wire format frozen for v1.0; semantics may grow
in a backward-compatible way.

## Why this protocol exists

Native Retell and Vapi voice calls run over vendor WebRTC stacks (LiveKit and
Daily.co respectively). Building a pure-Python WebRTC client to talk to those
stacks is a high-risk path that does not match the supported vendor flow.

Decibench instead runs the **official browser SDK** for the target platform
inside a headless Chromium controlled by Playwright, and exposes that browser
session to Python over a tiny local WebSocket bridge.

This document defines that bridge protocol. It is platform-neutral on purpose:
the same contract serves Retell, Vapi, and any future browser-SDK platform.

## Process model

```
Python (decibench) <— local WebSocket —> Node sidecar <— Playwright —> Chromium <— browser SDK —> vendor
```

- The Python connector spawns the sidecar on demand and owns its lifecycle.
- The bridge listens on `127.0.0.1` only. The default port is **`38917`** but
  is selected dynamically when zero is passed; the chosen port is reported on
  stdout as `BRIDGE_LISTENING port=<n>` for the parent to scrape.
- All messages are **UTF-8 JSON, one message per WebSocket frame**, with a
  required `type` field. Binary audio frames are sent as raw PCM bytes inside
  the same WebSocket connection (binary opcode); the JSON `type` envelope is
  not used for audio payloads.

## Message envelope

```json
{
  "type": "connect" | "send_audio_chunk" | "end_turn" | ... ,
  "id": "msg_<uuid>",            // client-supplied request id
  "ts_ms": 1234567890.123,        // sender's monotonic timestamp in ms
  "data": { ...payload... }
}
```

Every server-initiated event uses the same envelope but `id` is server-issued
and unrelated to any request id.

## Audio format

- PCM16 little-endian, mono, **16 kHz** by default.
- The `connect` request may negotiate a different sample rate via
  `data.audio.sample_rate`; the server responds with the rate it actually
  delivers in `connected.data.audio.sample_rate` and applies SR conversion
  internally.
- Binary frames sent **client → server** are caller audio chunks.
- Binary frames sent **server → client** are agent audio chunks.

## Client → server messages

### `connect`

Open a vendor session inside the headless browser.

```json
{
  "type": "connect",
  "id": "msg_1",
  "ts_ms": 0.0,
  "data": {
    "platform": "retell" | "vapi",
    "agent_id": "agent_xxx",
    "credentials": { "api_key": "..." },
    "audio": { "sample_rate": 16000, "encoding": "pcm_s16le", "channels": 1 },
    "options": { "metadata": { ... } }
  }
}
```

Server replies with `connected` (success) or `error`.

### `send_audio_chunk`

Streamed continuously while the caller is "speaking". This is a **JSON
control message** that announces the upcoming binary frame:

```json
{ "type": "send_audio_chunk", "id": "msg_2", "ts_ms": 12.5, "data": { "bytes": 640 } }
```

It MUST be followed immediately by exactly one binary WebSocket frame
containing `data.bytes` bytes of PCM16 mono at the negotiated sample rate.

### `end_turn`

Signal that the caller has finished their turn. The bridge tells the browser
SDK to stop sending caller audio and start expecting an agent response.

```json
{ "type": "end_turn", "id": "msg_3", "ts_ms": 100.0, "data": {} }
```

### `disconnect`

Cleanly tear down the vendor session and the browser page.

```json
{ "type": "disconnect", "id": "msg_4", "ts_ms": 0.0, "data": { "reason": "test_complete" } }
```

### `health`

Lightweight liveness probe. Server replies with `health_ok`.

### `capabilities`

Ask what the bridge / browser SDK supports for this platform. Server replies
with `capabilities` listing which event types it can emit, supported sample
rates, whether it can surface tool-call events, and so on.

## Server → client messages

### `connected`

```json
{
  "type": "connected",
  "id": "evt_1",
  "ts_ms": 250.0,
  "data": {
    "session_id": "vendor-session-uuid",
    "audio": { "sample_rate": 16000, "encoding": "pcm_s16le", "channels": 1 }
  }
}
```

### `agent_audio`

Announces the upcoming binary frame of agent audio:

```json
{ "type": "agent_audio", "id": "evt_2", "ts_ms": 410.0, "data": { "bytes": 320 } }
```

Followed immediately by exactly one binary WebSocket frame of PCM16 mono.

### `agent_transcript`

```json
{
  "type": "agent_transcript",
  "id": "evt_3",
  "ts_ms": 1200.0,
  "data": { "text": "How can I help?", "is_final": true }
}
```

### `tool_call` / `tool_result` / `interruption` / `turn_end` / `metadata`

Same envelope, payload shape mirrors `decibench.models.AgentEvent.data`.
The bridge passes through whatever the browser SDK emits without inventing
data; if a platform doesn't surface a particular event, the bridge simply
doesn't emit it.

### `error`

```json
{
  "type": "error",
  "id": "evt_99",
  "ts_ms": 0.0,
  "data": {
    "code": "vendor_auth_failed" | "browser_crashed" | "timeout" | "internal",
    "message": "human-readable explanation",
    "fatal": true
  }
}
```

If `fatal: true`, the bridge will close the WebSocket and exit; the Python
side must restart the sidecar to continue.

### `disconnected`

Final message before the WebSocket closes after a clean `disconnect`:

```json
{
  "type": "disconnected",
  "id": "evt_final",
  "ts_ms": 5300.0,
  "data": { "reason": "test_complete", "vendor_session_id": "..." }
}
```

### `health_ok`

```json
{ "type": "health_ok", "id": "evt_h", "ts_ms": 0.0, "data": { "uptime_ms": 12345 } }
```

### `capabilities`

```json
{
  "type": "capabilities",
  "id": "evt_c",
  "ts_ms": 0.0,
  "data": {
    "platform": "retell",
    "supported_sample_rates": [8000, 16000, 24000],
    "events": ["agent_audio", "agent_transcript", "tool_call", "interruption", "turn_end", "metadata"],
    "browser_sdk_version": "x.y.z",
    "bridge_version": "1.0.0"
  }
}
```

## Lifecycle and timeouts

- **Connect timeout:** 15 s by default. Configurable via
  `data.options.timeouts.connect_ms` on the `connect` message.
- **Idle audio timeout:** 30 s of no agent events after `end_turn` triggers
  `error { code: "timeout" }`.
- **Sidecar boot timeout:** the Python side waits up to 20 s for
  `BRIDGE_LISTENING` on stdout; otherwise it kills the sidecar process.

## Logging and diagnostics

- All sidecar logs go to **stderr** as one JSON object per line:
  `{ "level": "info|warn|error", "msg": "...", "ts": "...", "ctx": {...} }`.
- The Python bridge client captures stderr and surfaces fatal lines as part
  of the eventual `disconnect()` `CallSummary.platform_metadata.bridge_logs`.

## Versioning

Field added in a non-breaking way? OK. Field renamed or removed? Bump the
protocol version and gate behavior with a `bridge_version` capability check.
Decibench Python keeps the v1 client around for at least one minor release
after a v2 ships.
