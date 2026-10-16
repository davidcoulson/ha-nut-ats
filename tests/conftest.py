"""Offline fixtures for the custom NUT integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_nut_client(enable_custom_integrations):
    """Keep every integration connection inside the fake client."""
    client = MagicMock()
    client.list_ups = AsyncMock(return_value={"ups1": "UPS 1"})
    client.list_vars = AsyncMock(return_value={"ups.status": "OL"})
    client.list_commands = AsyncMock(return_value=set())
    client.run_command = AsyncMock()
    with patch("custom_components.nut.AIONUTClient", return_value=client) as factory:
        client.factory = factory
        yield client
