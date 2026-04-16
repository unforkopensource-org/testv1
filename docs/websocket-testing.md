# Real-time Testing via WebSocket (`ws://`)

The `ws://` connector is the most flexible shipped path. It is **shipped**
in the support matrix and works with any agent that speaks PCM16 mono
audio over a WebSocket.

This is the right path today for:

- raw Retell WebSocket endpoints
- raw Vapi WebSocket endpoints
- your own custom agent
- anything where you control or can wrap the wire format

For *native* Retell/Vapi (web SDK + WebRTC), see
[Native Connectors](native-connectors.md). That path is **experimental**.

## Wire contract

Decibench acts as the **client** and connects to the agent's WebSocket
endpoint. Audio frames are raw binary PCM16 mono at 16 kHz unless you
override via config. Control messages (turn end, transcript, etc.) use a
small JSON envelope.

### Frames Decibench sends

```json
{ "type": "audio.start", "sample_rate": 16000, "encoding": "pcm_s16le", "channels": 1 }
```

followed by binary frames containing PCM16 little-endian audio chunks,
followed by:

```json
{ "type": "audio.end" }
```

Then the equivalent for the next caller turn.

### Frames Decibench accepts

- Binary PCM16 frames → treated as agent audio.
- `{"type":"transcript","text":"...","is_final":true}` → agent transcript.
- `{"type":"turn_end"}` → agent finished its turn.
- `{"type":"error","code":"...","message":"..."}` → vendor-side error.

## Run

```bash
decibench run --target ws://your-agent-host:8765/path --suite quick
```

## Diagnostics

When a run fails, the captured WS frames and any vendor errors are
persisted into the SQLite store and surfaced in the dashboard's Call
Detail view. See [Honest Limitations](limitations.md) for what we
intentionally do not parse out of vendor-specific WS payloads.
