"""Connector registry and factory."""

from __future__ import annotations

from openpath.connectors.ashby import AshbyConnector
from openpath.connectors.base import BaseConnector
from openpath.connectors.github import GitHubConnector
from openpath.connectors.greenhouse import GreenhouseConnector
from openpath.connectors.lever import LeverConnector
from openpath.connectors.reddit import RedditConnector
from openpath.connectors.spider import CareerPageSpider
from openpath.exceptions import ConnectorError
from openpath.network.client import SafeHttpClient

_CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {
    "ats.greenhouse": GreenhouseConnector,
    "greenhouse": GreenhouseConnector,
    "ats.lever": LeverConnector,
    "lever": LeverConnector,
    "ats.ashby": AshbyConnector,
    "ashby": AshbyConnector,
    "web.career_spider": CareerPageSpider,
    "spider": CareerPageSpider,
    "vcs.github": GitHubConnector,
    "github": GitHubConnector,
    "social.reddit": RedditConnector,
    "reddit": RedditConnector,
}


def get_connector(connector_id: str, http_client: SafeHttpClient) -> BaseConnector:
    """Instantiate and return the appropriate connector."""
    conn_cls = _CONNECTOR_REGISTRY.get(connector_id)
    if not conn_cls:
        raise ConnectorError(
            f"No connector registered for '{connector_id}'. Available: {list(_CONNECTOR_REGISTRY.keys())}"
        )
    return conn_cls(http_client)
