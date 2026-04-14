"""Base connector interface for all voice agent connectors.

Every connector implements this interface. The orchestrator only talks
to BaseConnector — it never knows which platform it's testing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from decibench.models import (
    AgentEvent,
    AudioBuffer,
    AudioEncoding,
    CallSummary,
    ConnectionHandle,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class BaseConnector:
    """Abstract base for all voice agent connectors.

    Subclasses must implement connect, send_audio, receive_events,
    and disconnect. The orchestrator calls these in order.
    """

    # Audio format this connector expects. The audio engine transcodes to match.
    required_sample_rate: int = 16000
    required_encoding: AudioEncoding = AudioEncoding.PCM_S16LE
    required_channels: int = 1

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        """Establish connection to the voice agent.

        Args:
            target: Target URI (e.g., ws://host:port, exec:cmd)
            config: Auth and connection config from decibench.toml

        Returns:
            Opaque handle used for subsequent calls.
        """
        raise NotImplementedError

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        """Send caller audio to the agent.

        Args:
            handle: Connection handle from connect()
            audio: Audio data in the connector's required format
        """
        raise NotImplementedError

    async def receive_events(self, handle: ConnectionHandle) -> AsyncIterator[AgentEvent]:
        """Receive events from the agent.

        Yields AgentEvent objects as the agent responds. This is an
        async generator that yields until the agent is done or times out.
        """
        raise NotImplementedError
        yield  # pragma: no cover — makes this a generator

    async def disconnect(self, handle: ConnectionHandle) -> CallSummary:
        """Close the connection and return a call summary.

        Args:
            handle: Connection handle from connect()

        Returns:
            Complete summary of the call including audio and events.
        """
        raise NotImplementedError
