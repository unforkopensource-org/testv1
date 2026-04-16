"""Tests for the Decibench native bridge.

These tests do NOT spawn the real Node sidecar. Instead they:

1. Stand up a tiny in-process WebSocket server that speaks the bridge
   protocol exactly like the sidecar would, and point a `BridgeClient` at it
   (skipping the real `subprocess.create_subprocess_exec` codepath by passing
   a no-op shim into the bridge client's internals).
2. Verify the wire shape against `docs/bridge-protocol.md`.
3. Exercise the `BridgeConnector` integration via the same fake sidecar.

A real-vendor end-to-end test exists separately and is gated by the
`RETELL_API_KEY` env var. See `test_bridge_real_retell.py`.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

import pytest

websockets = pytest.importorskip("websockets")

from decibench.bridge import BridgeClient, BridgeMessageType  # noqa: E402
from decibench.bridge.protocol import ErrorCode  # noqa: E402
from decibench.connectors._bridge_base import BridgeConnector  # noqa: E402
from decibench.models import AudioBuffer, EventType  # noqa: E402

# --------------------------------------------------------------------- helpers


class FakeSidecar:
    """In-process WebSocket server that mimics the Decibench bridge sidecar.

    Behavior is scripted via callbacks so individual tests can drive specific
    failure modes (auth errors, timeouts, missing audio, etc.).
    """

    def __init__(self) -> None:
        self.server: Any = None
        self.host = "127.0.0.1"
        self.port: int = 0
        self.received: list[dict[str, Any]] = []
        self.received_audio: list[bytes] = []
        self._pending_audio_bytes = 0
        self.script: list[Any] = []  # list of (delay_s, action) tuples — see _run_script
        self.connected_event = asyncio.Event()

    async def start(self) -> None:
        async def handler(ws: Any) -> None:
            await self._handle(ws)

        self.server = await websockets.serve(handler, self.host, 0)
        sock = next(iter(self.server.sockets))
        self.port = sock.getsockname()[1]

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def _handle(self, ws: Any) -> None:
        # Run the test-supplied script in parallel with the message reader so
        # the fake sidecar can emit unsolicited events the way the real one does.
        script_task = asyncio.create_task(self._run_script(ws))
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    self.received_audio.append(raw)
                    self._pending_audio_bytes = 0
                    continue
                msg = json.loads(raw)
                self.received.append(msg)
                msg_type = msg.get("type")
                if msg_type == BridgeMessageType.SEND_AUDIO_CHUNK.value:
                    self._pending_audio_bytes = int(msg["data"]["bytes"])
                elif msg_type == BridgeMessageType.CONNECT.value:
                    self.connected_event.set()
                elif msg_type == BridgeMessageType.DISCONNECT.value:
                    await ws.send(_envelope(BridgeMessageType.DISCONNECTED, {"reason": "client"}))
                    await asyncio.sleep(0.05)
                    await ws.close()
                    return
                elif msg_type == BridgeMessageType.HEALTH.value:
                    await ws.send(_envelope(BridgeMessageType.HEALTH_OK, {"uptime_ms": 1.0}))
        finally:
            script_task.cancel()

    async def _run_script(self, ws: Any) -> None:
        """Execute a test-defined sequence of actions (sleep + send)."""
        await self.connected_event.wait()
        for delay_s, action in self.script:
            await asyncio.sleep(delay_s)
            kind = action[0]
            if kind == "connected":
                await ws.send(
                    _envelope(
                        BridgeMessageType.CONNECTED,
                        {
                            "session_id": action[1],
                            "audio": {
                                "sample_rate": 16000,
                                "encoding": "pcm_s16le",
                                "channels": 1,
                            },
                        },
                    )
                )
            elif kind == "transcript":
                await ws.send(
                    _envelope(
                        BridgeMessageType.AGENT_TRANSCRIPT,
                        {"text": action[1], "is_final": True},
                    )
                )
            elif kind == "audio":
                pcm: bytes = action[1]
                await ws.send(_envelope(BridgeMessageType.AGENT_AUDIO, {"bytes": len(pcm)}))
                await ws.send(pcm)
            elif kind == "turn_end":
                await ws.send(_envelope(BridgeMessageType.TURN_END, {"reason": "agent_done"}))
            elif kind == "error":
                code, message, fatal = action[1], action[2], action[3]
                await ws.send(
                    _envelope(
                        BridgeMessageType.ERROR,
                        {"code": code, "message": message, "fatal": fatal},
                    )
                )
                if fatal:
                    await ws.close()
                    return


def _envelope(msg_type: BridgeMessageType, data: dict[str, Any]) -> str:
    return json.dumps(
        {
            "type": msg_type.value,
            "id": f"evt_{uuid.uuid4().hex[:8]}",
            "ts_ms": time.monotonic() * 1000.0,
            "data": data,
        }
    )


async def _build_client_against_fake(fake: FakeSidecar) -> BridgeClient:
    """Skip the real subprocess and point a BridgeClient at the fake server."""
    client = BridgeClient.__new__(BridgeClient)
    BridgeClient.__init__(client)
    # The constructor builds asyncio.Queue / asyncio.Event objects; it does
    # NOT actually start anything. We now manually wire the WebSocket so we
    # don't go through `start()`'s subprocess path.
    client._port = fake.port
    await client._open_websocket()
    client._reader_task = asyncio.create_task(client._read_loop())
    return client


# ------------------------------------------------------------ protocol tests


@pytest.mark.asyncio
async def test_bridge_client_round_trip_connect_audio_disconnect() -> None:
    fake = FakeSidecar()
    await fake.start()
    # Small delays between scripted agent events let the client's outbound
    # `send_audio_chunk` / `end_turn` reach the fake (via a real I/O poll)
    # before the script closes out the turn. With back-to-back 0.0 delays
    # asyncio can starve I/O by running the script to completion first.
    fake.script = [
        (0.0, ("connected", "sess-123")),
        (0.05, ("transcript", "Hello there")),
        (0.01, ("audio", b"\x01\x00" * 80)),
        (0.01, ("turn_end",)),
    ]

    client = await _build_client_against_fake(fake)
    try:
        connected = await client.connect("retell", "agent_test", credentials={"api_key": "k"})
        assert connected["session_id"] == "sess-123"
        assert connected["audio"]["sample_rate"] == 16000

        await client.send_audio_chunk(b"\x10\x00" * 160)
        await client.end_turn()

        events: list[Any] = []
        async for ev in client.events():
            events.append(ev)
            if ev.type == BridgeMessageType.TURN_END:
                break

        kinds = [e.type for e in events]
        assert BridgeMessageType.AGENT_TRANSCRIPT in kinds
        assert BridgeMessageType.AGENT_AUDIO in kinds
        assert BridgeMessageType.TURN_END in kinds

        # Verify audio was forwarded to the fake sidecar correctly: JSON
        # envelope first, raw bytes second.
        send_audio_msgs = [m for m in fake.received if m["type"] == "send_audio_chunk"]
        assert send_audio_msgs and send_audio_msgs[0]["data"]["bytes"] == 320
        assert fake.received_audio == [b"\x10\x00" * 160]

        await client.disconnect()
    finally:
        await client.stop()
        await fake.stop()


@pytest.mark.asyncio
async def test_bridge_fatal_error_propagates() -> None:
    fake = FakeSidecar()
    await fake.start()
    fake.script = [
        (0.0, ("connected", "sess-err")),
        (0.0, ("error", ErrorCode.VENDOR_AUTH_FAILED.value, "bad key", True)),
    ]

    from decibench.bridge import BridgeFatalError

    client = await _build_client_against_fake(fake)
    try:
        await client.connect("retell", "agent_test", credentials={"api_key": "k"})
        with pytest.raises(BridgeFatalError) as exc:
            async for _ev in client.events():
                pass
        assert exc.value.code == ErrorCode.VENDOR_AUTH_FAILED.value
    finally:
        await client.stop()
        await fake.stop()


# ---------------------------------------------------------- connector tests


@pytest.mark.asyncio
async def test_retell_connector_full_call_via_fake_sidecar(monkeypatch: Any) -> None:
    """Exercise RetellConnector end-to-end against the fake sidecar."""
    from decibench.connectors.retell import RetellConnector

    fake = FakeSidecar()
    await fake.start()
    fake.script = [
        (0.0, ("connected", "sess-retell-1")),
        (0.05, ("transcript", "Hi, how can I help?")),
        (0.0, ("audio", b"\xaa\x00" * 200)),
        (0.0, ("turn_end",)),
    ]

    # Patch BridgeClient.start so the connector uses the fake server instead
    # of spawning the real Node sidecar.
    async def fake_start(self: BridgeClient) -> None:
        self._port = fake.port
        await self._open_websocket()
        self._reader_task = asyncio.create_task(self._read_loop())

    monkeypatch.setattr(BridgeClient, "start", fake_start)

    connector = RetellConnector()
    handle = await connector.connect("retell://agent_xyz", {"retell_api_key": "fake"})
    assert handle.state["session_id"] == "sess-retell-1"

    # Send caller audio.
    await connector.send_audio(handle, AudioBuffer(data=b"\x01\x00" * 160, sample_rate=16000))

    events: list[Any] = []
    async for ev in connector.receive_events(handle):
        events.append(ev)

    summary = await connector.disconnect(handle)

    types = [e.type for e in events]
    assert EventType.AGENT_TRANSCRIPT in types
    assert EventType.AGENT_AUDIO in types
    assert EventType.TURN_END in types
    assert summary.platform_metadata["retell_session_id"] == "sess-retell-1"
    assert len(summary.agent_audio) == 400  # 200 samples * 2 bytes

    await fake.stop()


@pytest.mark.asyncio
async def test_vapi_connector_passes_public_key(monkeypatch: Any) -> None:
    from decibench.connectors.vapi import VapiConnector

    fake = FakeSidecar()
    await fake.start()
    fake.script = [
        (0.0, ("connected", "sess-vapi-1")),
        (0.0, ("turn_end",)),
    ]

    async def fake_start(self: BridgeClient) -> None:
        self._port = fake.port
        await self._open_websocket()
        self._reader_task = asyncio.create_task(self._read_loop())

    monkeypatch.setattr(BridgeClient, "start", fake_start)

    connector = VapiConnector()
    handle = await connector.connect("vapi://assistant_abc", {"vapi_public_key": "pk_test"})
    assert handle.state["session_id"] == "sess-vapi-1"

    async for _ in connector.receive_events(handle):
        pass

    summary = await connector.disconnect(handle)
    assert summary.platform_metadata["vapi_session_id"] == "sess-vapi-1"

    # Confirm the connect envelope contained credentials.public_key, not api_key.
    connect_msgs = [m for m in fake.received if m["type"] == "connect"]
    assert connect_msgs
    assert connect_msgs[0]["data"]["credentials"] == {"public_key": "pk_test"}
    assert connect_msgs[0]["data"]["platform"] == "vapi"

    await fake.stop()


@pytest.mark.asyncio
async def test_retell_connector_rejects_missing_credentials() -> None:
    from decibench.connectors.retell import RetellConnector

    connector = RetellConnector()
    with pytest.raises(ValueError, match="API key"):
        await connector.connect("retell://agent_no_key", {})


@pytest.mark.asyncio
async def test_bridge_connector_parse_agent_id() -> None:
    class _Probe(BridgeConnector):
        platform_name = "retell"
        target_uri_prefix = "retell://"

    probe = _Probe()
    assert probe.parse_agent_id("retell://abc_123") == "abc_123"
    with pytest.raises(ValueError):
        probe.parse_agent_id("vapi://abc")
