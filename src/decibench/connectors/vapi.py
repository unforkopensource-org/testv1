"""Vapi native connector.

Same architecture as the Retell connector — a thin wrapper around
`BridgeConnector` that delegates the actual browser-SDK work to the
`decibench-bridge` Node sidecar.

Status: **Experimental**. Use the generic `ws://` connector for raw Vapi
WebSocket endpoints until the sidecar's Vapi adapter has a green gated
integration test.
"""

from __future__ import annotations

import os
from typing import Any

from decibench.connectors._bridge_base import BridgeConnector
from decibench.connectors.registry import register_connector


@register_connector("vapi")
class VapiConnector(BridgeConnector):
    """Connect to a native Vapi agent via the Decibench bridge sidecar."""

    platform_name = "vapi"
    target_uri_prefix = "vapi://"

    def extract_credentials(self, target: str, config: dict[str, Any]) -> dict[str, Any]:
        # The Vapi Web SDK takes a public_key (web key), not the server API key.
        public_key = (
            config.get("vapi_public_key")
            or config.get("vapi_api_key")  # accept either name for convenience
            or os.environ.get("VAPI_PUBLIC_KEY")
            or os.environ.get("VAPI_API_KEY", "")
        )
        return {"public_key": public_key} if public_key else {}
