# Install

Decibench is a local-first Python package. There is no hosted service to
sign up for.

## Requirements

- Python 3.11, 3.12, or 3.13
- macOS, Linux, or WSL2 on Windows
- Optional: Node 20 LTS — only required if you want to use the **native
  Retell / Vapi connectors** (which run a small browser-based bridge
  sidecar), or to develop the dashboard

## Standard install

```bash
pip install decibench
```

Verify:

```bash
decibench --version
decibench run --target demo:// --suite quick
```

`demo://` is a built-in echo agent. If the second command prints a score and
no errors, the install is good.

## Local development install

Clone and use [uv](https://docs.astral.sh/uv/) (or any venv tool):

```bash
git clone https://github.com/your-org/decibench.git
cd decibench
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
```

## Optional extras

| Extra            | What it pulls in                            | When you need it                              |
| ---------------- | ------------------------------------------- | --------------------------------------------- |
| `decibench[mos]` | `speechmos` for real DNSMOS scoring         | Speech-quality metric beyond the heuristic    |
| `decibench[stt]` | `faster-whisper`, `openai-whisper`          | Local STT for non-WebSocket connectors        |
| `decibench[dev]` | `pytest`, `mypy`, `ruff`, etc.              | Developing or contributing to Decibench       |

## Native bridge (optional, for native Retell / Vapi)

The native Retell and Vapi connectors are **experimental** today and require
a separate Node sidecar (see `docs/bridge-protocol.md` and
`docs/native-connectors.md`). For most users the recommended path is:

- `ws://` for any WebSocket-speaking agent (including raw Retell / Vapi WS)
- `exec:"..."` for local agents you can spawn as a process
- `http://` for batch / non-realtime endpoints
- The JSONL/Vapi/Retell **importers** for offline analysis of production calls

See [Honest Limitations](limitations.md) for what is and isn't shipped.
