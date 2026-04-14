"""Connector registry — resolves target URIs to connector instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from decibench.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

_connector_registry: dict[str, type[BaseConnector]] = {}


def register_connector(scheme: str) -> Callable[[type[BaseConnector]], type[BaseConnector]]:
    """Decorator to register a connector class for a URI scheme."""
    def decorator(cls: type[BaseConnector]) -> type[BaseConnector]:
        _connector_registry[scheme] = cls
        logger.debug("Registered connector: %s -> %s", scheme, cls.__name__)
        return cls
    return decorator


def get_connector(target: str, **kwargs: Any) -> BaseConnector:
    """Resolve a target URI to a connector instance.

    URI formats:
        ws://host:port/path       -> WebSocketConnector
        exec:command              -> ProcessConnector
        http://host:port/path     -> HTTPConnector
        demo                      -> DemoConnector
        demo://...                -> DemoConnector
    """
    scheme = _extract_scheme(target)
    if scheme not in _connector_registry:
        available = ", ".join(sorted(_connector_registry.keys())) or "none"
        msg = f"Unknown connector scheme: '{scheme}'. Available: {available}"
        raise ValueError(msg)
    return _connector_registry[scheme](**kwargs)


def _extract_scheme(target: str) -> str:
    """Extract the scheme from a target URI."""
    # Handle bare keywords like 'demo'
    if target in _connector_registry:
        return target

    # Handle 'exec:command' (no //)
    if ":" in target and "://" not in target:
        return target.split(":", 1)[0]

    # Handle standard URIs like ws://host, http://host, demo://
    if "://" in target:
        scheme = target.split("://", 1)[0]
        # Map wss -> ws, https -> http
        scheme_map = {"wss": "ws", "https": "http"}
        return scheme_map.get(scheme, scheme)

    return target
