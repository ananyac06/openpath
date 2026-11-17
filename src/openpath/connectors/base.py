"""Base source connector abstraction for OpenPath."""

from __future__ import annotations

from abc import ABC, abstractmethod

from openpath.models.entities import Opportunity, Source
from openpath.network.client import SafeHttpClient


class BaseConnector(ABC):
    """Abstract interface for all source connectors."""

    def __init__(self, http_client: SafeHttpClient) -> None:
        self.http_client = http_client

    @abstractmethod
    async def fetch_opportunities(self, source: Source) -> list[Opportunity]:
        """Fetch and extract structured opportunities from the declared source."""
        raise NotImplementedError
