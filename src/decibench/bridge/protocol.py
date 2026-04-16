"""Bridge protocol message types and constants.

Mirrors `docs/bridge-protocol.md`. Keep this file the single Python source of
truth for the wire format. The Node sidecar has its own copy under
`bridge_sidecar/src/protocol.ts`; the two MUST stay aligned and any change
here requires a matching change there.
"""

from __future__ import annotations

from enum import StrEnum

BRIDGE_PROTOCOL_VERSION = "1.0.0"

# Default sidecar boot timeout — how long Python waits for the sidecar to print
# `BRIDGE_LISTENING port=<n>` on stdout before giving up and killing it.
BRIDGE_BOOT_TIMEOUT_S = 20.0

# Default per-call timeouts forwarded to the sidecar in the `connect` payload.
DEFAULT_CONNECT_TIMEOUT_MS = 15_000
DEFAULT_IDLE_AUDIO_TIMEOUT_MS = 30_000


class BridgeMessageType(StrEnum):
    """Every JSON message on the bridge has one of these `type` values."""

    # Client → server
    CONNECT = "connect"
    SEND_AUDIO_CHUNK = "send_audio_chunk"
    END_TURN = "end_turn"
    DISCONNECT = "disconnect"
    HEALTH = "health"
    CAPABILITIES_QUERY = "capabilities_query"

    # Server → client
    CONNECTED = "connected"
    AGENT_AUDIO = "agent_audio"
    AGENT_TRANSCRIPT = "agent_transcript"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    INTERRUPTION = "interruption"
    TURN_END = "turn_end"
    METADATA = "metadata"
    ERROR = "error"
    DISCONNECTED = "disconnected"
    HEALTH_OK = "health_ok"
    CAPABILITIES = "capabilities"


class ErrorCode(StrEnum):
    """Stable error codes used in `error.data.code`."""

    VENDOR_AUTH_FAILED = "vendor_auth_failed"
    VENDOR_REJECTED = "vendor_rejected"
    BROWSER_CRASHED = "browser_crashed"
    TIMEOUT = "timeout"
    PROTOCOL_VIOLATION = "protocol_violation"
    INTERNAL = "internal"
