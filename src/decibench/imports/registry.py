"""Registry for call trace importers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from decibench.imports.base import BaseImporter

logger = logging.getLogger(__name__)

_importer_registry: dict[str, type[BaseImporter]] = {}


def register_importer(name: str) -> Callable[[type[BaseImporter]], type[BaseImporter]]:
    """Decorator to register an importer class."""
    def decorator(cls: type[BaseImporter]) -> type[BaseImporter]:
        _importer_registry[name] = cls
        logger.debug("Registered importer: %s -> %s", name, cls.__name__)
        return cls
    return decorator


def get_importer(provider: str, **kwargs: Any) -> BaseImporter:
    """Resolve a provider name to an importer instance."""
    if provider not in _importer_registry:
        available = ", ".join(sorted(_importer_registry.keys())) or "none"
        msg = f"Unknown importer: '{provider}'. Available: {available}"
        raise ValueError(msg)
    return _importer_registry[provider](**kwargs)
