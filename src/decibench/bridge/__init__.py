"""Decibench native bridge — Python client for the platform-neutral sidecar.

The sidecar is a Node 20 + TypeScript process that runs the official browser
SDK for a target platform (Retell, Vapi, ...) inside a headless Chromium
controlled by Playwright. Decibench's Python connectors talk to it over a
local WebSocket using the protocol defined in `docs/bridge-protocol.md`.

This package contains:
- `protocol`: dataclasses + constants for protocol messages and error codes.
- `client`: the `BridgeClient` that spawns the sidecar and exchanges messages.
"""

from decibench.bridge.client import (
    BridgeClient,
    BridgeError,
    BridgeFatalError,
    BridgeTimeoutError,
)
from decibench.bridge.protocol import (
    BRIDGE_PROTOCOL_VERSION,
    BridgeMessageType,
    ErrorCode,
)

__all__ = [
    "BRIDGE_PROTOCOL_VERSION",
    "BridgeClient",
    "BridgeError",
    "BridgeFatalError",
    "BridgeMessageType",
    "BridgeTimeoutError",
    "ErrorCode",
]
