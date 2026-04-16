"""BridgeClient — Python side of the Decibench native bridge.

Spawns the Node sidecar (`decibench-bridge` package, or a path provided by
`DECIBENCH_BRIDGE_CMD`), opens a local WebSocket, and exposes an async API
for sending caller audio and receiving agent events.

The protocol is defined in `docs/bridge-protocol.md`. Every JSON message
follows the envelope `{type, id, ts_ms, data}`. Binary frames are raw PCM16
mono audio at the negotiated sample rate, and are always preceded by the
matching JSON control message (`send_audio_chunk` for client→server,
`agent_audio` for server→client).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import shutil
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from decibench.bridge.protocol import (
    BRIDGE_BOOT_TIMEOUT_S,
    BRIDGE_PROTOCOL_VERSION,
    DEFAULT_CONNECT_TIMEOUT_MS,
    DEFAULT_IDLE_AUDIO_TIMEOUT_MS,
    BridgeMessageType,
    ErrorCode,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class BridgeError(Exception):
    """Recoverable bridge-side error. The session is gone but the sidecar may live."""

    def __init__(self, code: str, message: str, *, fatal: bool = False) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.fatal = fatal


class BridgeFatalError(BridgeError):
    """Unrecoverable bridge error — the sidecar is dead, restart required."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, fatal=True)


class BridgeTimeoutError(BridgeError):
    """The bridge did not respond in the expected window."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.TIMEOUT.value, message, fatal=False)


@dataclass
class BridgeEvent:
    """Decoded server→client event."""

    type: BridgeMessageType
    ts_ms: float
    data: dict[str, Any] = field(default_factory=dict)
    audio: bytes | None = None  # populated for AGENT_AUDIO


def _resolve_sidecar_command() -> list[str]:
    """Decide how to launch the sidecar.

    Priority:
    1. `DECIBENCH_BRIDGE_CMD` env var — explicit override (shell-split).
    2. A `decibench-bridge` executable on PATH (npm-installed).
    3. `node bridge_sidecar/dist/server.js` relative to repo root, for dev.
    """
    override = os.environ.get("DECIBENCH_BRIDGE_CMD")
    if override:
        return shlex.split(override)

    on_path = shutil.which("decibench-bridge")
    if on_path:
        return [on_path]

    # Fallback to the in-repo built sidecar — used during development and CI.
    repo_root = _find_repo_root()
    if repo_root is not None:
        candidate = repo_root / "bridge_sidecar" / "dist" / "server.js"
        if candidate.exists():
            node = shutil.which("node") or "node"
            return [node, str(candidate)]

    raise BridgeFatalError(
        ErrorCode.INTERNAL.value,
        "Could not find the Decibench bridge sidecar. Install it with "
        "`npm install -g decibench-bridge`, set DECIBENCH_BRIDGE_CMD, or "
        "build the in-repo sidecar with `cd bridge_sidecar && npm run build`.",
    )


def _find_repo_root() -> Any:
    """Walk up from this file looking for a `bridge_sidecar` directory."""
    from pathlib import Path

    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "bridge_sidecar").is_dir():
            return parent
    return None


class BridgeClient:
    """Async client for the Decibench native bridge sidecar.

    Lifecycle:
        client = BridgeClient()
        await client.start()
        await client.connect("retell", "agent_id", credentials={...})
        await client.send_audio_chunk(pcm16_bytes)
        await client.end_turn()
        async for event in client.events():
            ...
        await client.disconnect()
        await client.stop()
    """

    def __init__(
        self,
        *,
        sidecar_command: list[str] | None = None,
        boot_timeout_s: float = BRIDGE_BOOT_TIMEOUT_S,
    ) -> None:
        self._sidecar_command = sidecar_command
        self._boot_timeout_s = boot_timeout_s

        self._proc: asyncio.subprocess.Process | None = None
        self._port: int | None = None
        self._ws: Any = None  # websockets.WebSocketClientProtocol — kept untyped for optional dep
        self._stderr_lines: list[str] = []
        self._stderr_task: asyncio.Task[None] | None = None
        self._event_queue: asyncio.Queue[BridgeEvent] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None
        self._pending_audio_bytes: int = 0
        self._closed = False
        self._connected_event = asyncio.Event()
        self._disconnected_event = asyncio.Event()
        self._connected_payload: dict[str, Any] = {}

    # ---------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        """Spawn the sidecar and open the WebSocket."""
        cmd = self._sidecar_command or _resolve_sidecar_command()
        # Pass port=0 so the sidecar binds to a free ephemeral port.
        env = {**os.environ, "DECIBENCH_BRIDGE_PORT": "0"}
        logger.info("Starting Decibench bridge sidecar: %s", " ".join(cmd))
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        # Capture stderr on a side task so it never blocks.
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        try:
            port = await asyncio.wait_for(self._await_listening(), timeout=self._boot_timeout_s)
        except TimeoutError as exc:
            await self._kill_proc()
            raise BridgeFatalError(
                ErrorCode.TIMEOUT.value,
                f"Bridge sidecar did not announce a listening port within "
                f"{self._boot_timeout_s}s. Last stderr: {self._tail_stderr()}",
            ) from exc

        self._port = port
        await self._open_websocket()
        self._reader_task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        """Close the WebSocket and terminate the sidecar."""
        if self._closed:
            return
        self._closed = True

        if self._ws is not None:
            with suppress(Exception):
                await self._ws.close()
            self._ws = None

        if self._reader_task is not None:
            self._reader_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._reader_task

        await self._kill_proc()

        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._stderr_task

    # ---------------------------------------------------------------- requests

    async def connect(
        self,
        platform: str,
        agent_id: str,
        *,
        credentials: dict[str, Any] | None = None,
        sample_rate: int = 16000,
        connect_timeout_ms: int = DEFAULT_CONNECT_TIMEOUT_MS,
        idle_audio_timeout_ms: int = DEFAULT_IDLE_AUDIO_TIMEOUT_MS,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Open a vendor session inside the headless browser. Returns the negotiated audio format."""
        await self._send_json(
            BridgeMessageType.CONNECT,
            {
                "platform": platform,
                "agent_id": agent_id,
                "credentials": credentials or {},
                "audio": {"sample_rate": sample_rate, "encoding": "pcm_s16le", "channels": 1},
                "options": {
                    "metadata": metadata or {},
                    "timeouts": {
                        "connect_ms": connect_timeout_ms,
                        "idle_audio_ms": idle_audio_timeout_ms,
                    },
                    "client_protocol_version": BRIDGE_PROTOCOL_VERSION,
                },
            },
        )

        try:
            await asyncio.wait_for(self._connected_event.wait(), timeout=connect_timeout_ms / 1000)
        except TimeoutError as exc:
            raise BridgeTimeoutError(
                f"Bridge did not return `connected` within {connect_timeout_ms}ms",
            ) from exc

        # The CONNECTED event payload is in the queue. Find and remove it; whatever
        # comes after stays for the caller to consume.
        return self._connected_payload

    async def send_audio_chunk(self, pcm16_mono: bytes) -> None:
        """Send one chunk of caller audio. Sends the JSON envelope then the binary frame."""
        if not pcm16_mono:
            return
        await self._send_json(BridgeMessageType.SEND_AUDIO_CHUNK, {"bytes": len(pcm16_mono)})
        await self._send_binary(pcm16_mono)

    async def end_turn(self) -> None:
        await self._send_json(BridgeMessageType.END_TURN, {})

    async def disconnect(self, reason: str = "test_complete") -> None:
        """Ask the sidecar to tear down the vendor session cleanly."""
        if self._ws is None:
            return
        await self._send_json(BridgeMessageType.DISCONNECT, {"reason": reason})
        with suppress(TimeoutError):
            await asyncio.wait_for(self._disconnected_event.wait(), timeout=10.0)

    async def health(self) -> dict[str, Any]:
        await self._send_json(BridgeMessageType.HEALTH, {})
        # The next event of type HEALTH_OK is the response. Drain until found.
        # In practice this is fine — health is only called outside of audio flow.
        while True:
            event = await self._event_queue.get()
            if event.type == BridgeMessageType.HEALTH_OK:
                return event.data

    # ------------------------------------------------------------------ events

    async def events(self) -> AsyncIterator[BridgeEvent]:
        """Yield events from the bridge until a fatal error or DISCONNECTED."""
        while True:
            event = await self._event_queue.get()
            if event.type == BridgeMessageType.ERROR and event.data.get("fatal"):
                code = event.data.get("code", ErrorCode.INTERNAL.value)
                msg = event.data.get("message", "fatal bridge error")
                raise BridgeFatalError(code, msg)
            if event.type == BridgeMessageType.DISCONNECTED:
                yield event
                return
            yield event

    @property
    def stderr_log(self) -> list[str]:
        """Captured sidecar stderr lines — useful for failure diagnostics."""
        return list(self._stderr_lines)

    # ----------------------------------------------------------------- internals

    async def _open_websocket(self) -> None:
        try:
            import websockets  # imported here so the bridge module is importable without it
        except ImportError as exc:
            raise BridgeFatalError(
                ErrorCode.INTERNAL.value,
                "The `websockets` package is required for the native bridge. "
                "Install with `pip install websockets>=14.1`.",
            ) from exc

        url = f"ws://127.0.0.1:{self._port}/"
        # Generous max size — agent audio frames can be a few KB but we never
        # expect anything larger than ~64KB per frame.
        self._ws = await websockets.connect(url, max_size=2**20, ping_interval=20)

    async def _send_json(self, msg_type: BridgeMessageType, data: dict[str, Any]) -> None:
        if self._ws is None:
            raise BridgeFatalError(ErrorCode.INTERNAL.value, "Bridge WebSocket is not open")
        envelope = {
            "type": msg_type.value,
            "id": f"msg_{uuid.uuid4().hex[:12]}",
            "ts_ms": time.monotonic() * 1000.0,
            "data": data,
        }
        await self._ws.send(json.dumps(envelope))

    async def _send_binary(self, payload: bytes) -> None:
        if self._ws is None:
            raise BridgeFatalError(ErrorCode.INTERNAL.value, "Bridge WebSocket is not open")
        await self._ws.send(payload)

    async def _read_loop(self) -> None:
        """Background task: decode incoming frames into BridgeEvent objects."""
        if self._ws is None:
            return
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    # Binary frame: this is agent audio whose envelope was
                    # already received and is awaiting `audio` bytes.
                    if self._pending_audio_bytes > 0:
                        # Re-emit the previously-queued AGENT_AUDIO with payload.
                        # We stashed an envelope-only event earlier; replace it.
                        await self._event_queue.put(
                            BridgeEvent(
                                type=BridgeMessageType.AGENT_AUDIO,
                                ts_ms=time.monotonic() * 1000.0,
                                data={"bytes": len(raw)},
                                audio=raw,
                            )
                        )
                        self._pending_audio_bytes = 0
                    else:
                        logger.warning(
                            "Received unsolicited binary frame from bridge (%d bytes)", len(raw)
                        )
                    continue

                envelope = json.loads(raw)
                msg_type_str = envelope.get("type", "")
                try:
                    msg_type = BridgeMessageType(msg_type_str)
                except ValueError:
                    logger.warning("Unknown bridge message type: %r", msg_type_str)
                    continue

                data = envelope.get("data", {})
                ts_ms = float(envelope.get("ts_ms", time.monotonic() * 1000.0))

                if msg_type == BridgeMessageType.CONNECTED:
                    self._connected_payload = data
                    self._connected_event.set()
                    continue

                if msg_type == BridgeMessageType.AGENT_AUDIO:
                    # Wait for the binary frame that follows; mark expected size.
                    self._pending_audio_bytes = int(data.get("bytes", 0))
                    continue

                if msg_type == BridgeMessageType.DISCONNECTED:
                    await self._event_queue.put(BridgeEvent(type=msg_type, ts_ms=ts_ms, data=data))
                    self._disconnected_event.set()
                    return

                await self._event_queue.put(BridgeEvent(type=msg_type, ts_ms=ts_ms, data=data))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Bridge read loop crashed: %s", exc)
            await self._event_queue.put(
                BridgeEvent(
                    type=BridgeMessageType.ERROR,
                    ts_ms=time.monotonic() * 1000.0,
                    data={
                        "code": ErrorCode.INTERNAL.value,
                        "message": f"Read loop crashed: {exc}",
                        "fatal": True,
                    },
                )
            )

    async def _await_listening(self) -> int:
        """Read sidecar stdout until we see `BRIDGE_LISTENING port=<n>`."""
        assert self._proc is not None and self._proc.stdout is not None
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                raise BridgeFatalError(
                    ErrorCode.INTERNAL.value,
                    f"Bridge sidecar exited before announcing a port. "
                    f"stderr tail: {self._tail_stderr()}",
                )
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded.startswith("BRIDGE_LISTENING"):
                # Format: BRIDGE_LISTENING port=12345
                for token in decoded.split():
                    if token.startswith("port="):
                        return int(token.split("=", 1)[1])
            # Otherwise log and keep reading.
            logger.debug("bridge stdout: %s", decoded)

    async def _drain_stderr(self) -> None:
        if self._proc is None or self._proc.stderr is None:
            return
        try:
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    return
                self._stderr_lines.append(line.decode("utf-8", errors="replace").rstrip())
                if len(self._stderr_lines) > 1000:
                    self._stderr_lines = self._stderr_lines[-1000:]
        except asyncio.CancelledError:
            return

    def _tail_stderr(self, n: int = 10) -> str:
        return " | ".join(self._stderr_lines[-n:])

    async def _kill_proc(self) -> None:
        if self._proc is None:
            return
        if self._proc.returncode is None:
            with suppress(ProcessLookupError):
                self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    self._proc.kill()
                with suppress(Exception):
                    await self._proc.wait()
        self._proc = None
