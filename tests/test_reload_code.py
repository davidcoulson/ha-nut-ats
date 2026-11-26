"""nut.reload_code loads the Python files from disk again."""

import sys
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT

from custom_components.nut.const import DOMAIN


async def test_reload_code_replaces_the_modules(hass, mock_nut_client):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "mock", CONF_PORT: 3493})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    old = sys.modules["custom_components.nut"]

    # the fixture patches the old module; patch the library so the new one gets the fake
    with patch("aionut.AIONUTClient", mock_nut_client.factory):
        await hass.services.async_call(DOMAIN, "reload_code", {}, blocking=True)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert sys.modules["custom_components.nut"] is not old
    assert hass.services.has_service(DOMAIN, "reload_code")
