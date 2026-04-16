# Native Connector Status

This page is the single source of truth for the *native* (vendor-SDK)
connector status. Anything not listed here as **shipped** should be
treated as not yet usable in production.

## Status table

| Target URI prefix | Connector | Status         | Recommended path today                   |
| ----------------- | --------- | -------------- | ---------------------------------------- |
| `demo://`         | Demo      | **Shipped**    | Quickstart                               |
| `ws://`           | WebSocket | **Shipped**    | Real-time WebSocket agents               |
| `exec:"..."`      | Process   | **Shipped**    | Local scripts / processes                |
| `http://`         | HTTP      | **Shipped**    | Batch / non-realtime endpoints           |
| `retell://`       | Retell    | **Experimental** | Use `ws://` for raw Retell WS today    |
| `vapi://`         | Vapi      | **Experimental** | Use `ws://` for raw Vapi WS today      |
| LiveKit / ElevenLabs / Bland / SIP / PSTN | — | **Planned** | Not implemented                |

The same data lives in `docs/support-matrix.yaml` (machine-readable).

## What "experimental" means here

The native Retell and Vapi connectors are wired through the
**Decibench native bridge** — a small Node 20 + TypeScript sidecar that
runs the official vendor browser SDK inside headless Chromium and
bridges PCM16 audio in and out via a WebSocket protocol. The protocol
itself (see [Bridge Protocol](bridge-protocol.md)) is shipped and
tested. The end-to-end browser bridge against real vendor agents is
gated behind an integration test that requires real credentials, and is
**not** on a per-PR CI run.

Until the gated integration test for that vendor is green on a nightly
job we keep the connector marked **experimental**. We will not flip it
to "shipped" before that.

If you want to play with the native bridge today:

```bash
cd bridge_sidecar
npm install
npx playwright install chromium     # one-time
npm run build

# In another shell:
DECIBENCH_E2E_RETELL=1 \
RETELL_API_KEY=... \
RETELL_TEST_AGENT_ID=... \
pytest tests/test_bridge_real_retell.py -q
```

## Why we don't ship pure-Python WebRTC

The vendor SDKs are browser/WebRTC-first. A pure-Python WebRTC
reimplementation would be more reverse engineering and more transport
bugs than running the actual SDK in a controlled headless browser. The
browser-bridge approach lets us follow the same code path the vendor
supports, which is the only honest "native" path.

## Roadmap

- LiveKit connector — same bridge architecture, planned next.
- ElevenLabs / Bland — similar bridge plan.
- SIP / PSTN — intentionally **bring your own** Twilio/Vonage; Decibench
  does not host telephony.
