# Local Process Testing (`exec:`)

The `exec:` connector spawns a subprocess and streams PCM16 audio over
its stdin/stdout. It is **shipped**.

This is the simplest way to test a local agent that does not yet expose a
network endpoint — for example, a script you're iterating on, or a Python
function wrapped in a tiny CLI.

## Contract

The subprocess gets:

- **stdin**: raw PCM16 mono 16 kHz frames from the caller.
- **stdout**: raw PCM16 mono 16 kHz frames from the agent.
- **stderr**: free-form logging — captured by Decibench and shown in the
  call's "logs" tab in the dashboard.

The process should exit when the call is over (Decibench will close
stdin to signal end-of-call).

## Run

```bash
decibench run --target 'exec:"python -m my_agent --realtime"' --suite quick
```

## Why use this

- Zero network setup.
- The same audio path you'd test against a hosted agent — no special-case
  test harness in your code.
- Debuggable with normal stderr logs.

## When not to use this

- For agents already speaking WebSocket — use `ws://` instead.
- For batch / non-realtime endpoints — use `http://`.
