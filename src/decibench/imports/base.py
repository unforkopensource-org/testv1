"""Base structures for production call importers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from decibench.models import CallTrace


class BaseImporter(ABC):
    """Abstract base class for all platform importers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the platform (e.g. 'vapi', 'retell')."""
        ...

    @abstractmethod
    async def fetch_calls(self, limit: int = 10, since: str | None = None, **kwargs: Any) -> list[CallTrace]:
        """Fetch real calls from the platform API and map to CallTrace.

        Args:
            limit: maximum number of traces to fetch.
            since: date filter (optional).
            **kwargs: Extra authentication configs (e.g. api_key) handled by registry matching.

        Returns:
            list of normalized CallTrace models ready for storage/evaluation.
        """
        ...
