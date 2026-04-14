"""Voice agent connectors — pluggable adapters for reaching any voice agent."""

import decibench.connectors.demo
import decibench.connectors.http
import decibench.connectors.process
import decibench.connectors.retell
import decibench.connectors.vapi

# Import all built-in connectors to trigger registration
import decibench.connectors.websocket  # noqa: F401
from decibench.connectors.base import BaseConnector
from decibench.connectors.registry import get_connector, register_connector

__all__ = ["BaseConnector", "get_connector", "register_connector"]
