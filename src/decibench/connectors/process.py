"""Process connector — the killer feature. Test local agents without deploying.

Protocol:
    stdin  -> raw PCM audio bytes (16kHz, 16-bit, mono)
    stdout <- raw PCM audio bytes (16kHz, 16-bit, mono)
    stderr <- optional JSON metadata lines (tool calls, internal metrics)
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import time
from typing import TYPE_CHECKING, Any

from decibench.connectors.base import BaseConnector
from decibench.connectors.registry import register_connector
from decibench.models import (
    AgentEvent,
    AudioBuffer,
    CallSummary,
    ConnectionHandle,
    EventType,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

_CHUNK_BYTES = 3200  # 100ms at 16kHz 16-bit mono
_READ_TIMEOUT = 2.0  # Seconds to wait for agent output before considering done
_PROCESS_KILL_TIMEOUT = 5.0


@register_connector("exec")
class ProcessConnector(BaseConnector):
    """Test any local voice agent by spawning it as a subprocess.

    The simplest possible protocol: audio in via stdin, audio out via stdout.
    No deployment, no network, no API keys. Just run your agent.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._recorded_audio = bytearray()
        self._events: list[AgentEvent] = []
        self._stderr_data = bytearray()

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        # Parse command from target: exec:command or exec:"command with args"
        command = target
        if command.startswith("exec:"):
            command = command[5:].strip()
        # Remove surrounding quotes if present
        if command.startswith('"') and command.endswith('"'):
            command = command[1:-1]

        logger.info("Spawning process: %s", command)

        # Use shlex.split for safe argument parsing
        args = shlex.split(command)
        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._recorded_audio.clear()
        self._events.clear()
        self._stderr_data.clear()

        handle = ConnectionHandle(
            connector_type="exec",
            start_time_ns=time.monotonic_ns(),
            state={"command": command, "pid": self._process.pid},
        )

        # Start stderr reader in background
        self._stderr_task = asyncio.create_task(self._read_stderr())

        return handle

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        if self._process is None or self._process.stdin is None:
            msg = "Process not started — call connect() first"
            raise RuntimeError(msg)

        # Write audio to stdin in chunks with real-time pacing
        # Chunk duration = chunk_bytes / (sample_rate * 2 bytes_per_sample)
        sample_rate = audio.sample_rate or 16000
        chunk_duration = _CHUNK_BYTES / (sample_rate * 2)  # seconds per chunk

        data = audio.data
        for offset in range(0, len(data), _CHUNK_BYTES):
            chunk = data[offset : offset + _CHUNK_BYTES]
            self._process.stdin.write(chunk)
            await self._process.stdin.drain()
            # Pace at ~real-time so latency measurements are accurate
            await asyncio.sleep(chunk_duration * 0.5)  # 50% real-time for speed

        # Signal end of input for this turn (but don't close stdin yet)

    async def receive_events(self, handle: ConnectionHandle) -> AsyncIterator[AgentEvent]:
        if self._process is None or self._process.stdout is None:
            msg = "Process not started — call connect() first"
            raise RuntimeError(msg)

        start_ns = handle.start_time_ns
        consecutive_empty = 0
        max_empty = 3

        while consecutive_empty < max_empty:
            try:
                chunk = await asyncio.wait_for(
                    self._process.stdout.read(_CHUNK_BYTES),
                    timeout=_READ_TIMEOUT,
                )
            except TimeoutError:
                consecutive_empty += 1
                continue

            if not chunk:
                break  # EOF — process closed stdout

            consecutive_empty = 0
            self._recorded_audio.extend(chunk)

            now_ms = (time.monotonic_ns() - start_ns) / 1_000_000
            event = AgentEvent(
                type=EventType.AGENT_AUDIO,
                timestamp_ms=now_ms,
                audio=chunk,
            )
            self._events.append(event)
            yield event

    async def disconnect(self, handle: ConnectionHandle) -> CallSummary:
        duration_ms = (time.monotonic_ns() - handle.start_time_ns) / 1_000_000

        if self._process is not None:
            # Close stdin to signal we're done
            if self._process.stdin is not None:
                try:
                    self._process.stdin.close()
                    await self._process.stdin.wait_closed()
                except Exception:  # noqa: S110
                    pass  # Best-effort stdin close during teardown

            # Wait for process to finish, kill if it takes too long
            try:
                await asyncio.wait_for(
                    self._process.wait(),
                    timeout=_PROCESS_KILL_TIMEOUT,
                )
            except TimeoutError:
                logger.warning("Process did not exit in time, terminating")
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=2.0)
                except TimeoutError:
                    logger.warning("Process did not terminate, killing")
                    self._process.kill()
                    await self._process.wait()

            self._process = None

        # Parse metadata from stderr
        metadata = self._parse_stderr_metadata()

        return CallSummary(
            duration_ms=duration_ms,
            turn_count=metadata.get("turn_count", 1),
            agent_audio=bytes(self._recorded_audio),
            events=list(self._events),
            platform_metadata=metadata,
        )

    async def _read_stderr(self) -> None:
        """Read stderr in background for metadata and logging."""
        if self._process is None or self._process.stderr is None:
            return
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                self._stderr_data.extend(line)
        except Exception:  # noqa: S110
            pass  # Best-effort stderr reader — process may exit at any time

    def _parse_stderr_metadata(self) -> dict[str, Any]:
        """Parse JSON metadata lines from stderr output."""
        metadata: dict[str, Any] = {}
        stderr_text = self._stderr_data.decode("utf-8", errors="replace")

        for line in stderr_text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    metadata.update(parsed)
            except json.JSONDecodeError:
                # Non-JSON stderr lines are agent logs, not metadata
                logger.debug("Agent stderr: %s", line)

        return metadata
