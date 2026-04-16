"""Retell native connector.

Decibench's RetellConnector is a thin wrapper around `BridgeConnector`. The
heavy lifting — running the official Retell Web Client SDK inside headless
Chromium and bridging PCM16 audio in and out — lives in the
`decibench-bridge` Node sidecar (see `bridge_sidecar/`).

Status: **Experimental**. The protocol contract is shipped and this connector
is wired end-to-end against the sidecar; the sidecar itself depends on the
Retell Web Client SDK, Playwright, and a real Retell `agent_id` + API key.
The README and `docs/support-matrix.yaml` will not flip this to "Shipped"
until the gated integration test against a real Retell agent is green.

For raw Retell WebSocket endpoints, use the generic `ws://` connector.
"""

from __future__ import annotations

from typing import Any

from decibench.connectors._bridge_base import BridgeConnector
from decibench.connectors.registry import register_connector


@register_connector("retell")
class RetellConnector(BridgeConnector):
    """Connect to a native Retell agent via the Decibench bridge sidecar."""

    platform_name = "retell"
    target_uri_prefix = "retell://"

    def extract_credentials(self, target: str, config: dict[str, Any]) -> dict[str, Any]:
        # Retell uses a server-side API key (not a public key).
        return super().extract_credentials(target, config)
