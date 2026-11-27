"""nut.reload_code loads the Python files from disk again."""

import sys
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT

from custom_components.nut import _clear_marketplace_restart
from custom_components.nut.const import DOMAIN
from homeassistant.helpers import issue_registry as ir


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


async def test_reload_clears_only_marketplaces_nut_restart_repairs(hass) -> None:
    for domain, issue_id, issue_domain in (
        ("marketplace", "restart_required_1_tags/2026.11.27.2", DOMAIN),
        ("marketplace", "restart_required_2_tags/2026.11.26.01", "ssh"),
        ("marketplace", "critical_x", DOMAIN),
        (DOMAIN, "restart_required_x", DOMAIN),
    ):
        ir.async_create_issue(
            hass, domain, issue_id, is_fixable=False, issue_domain=issue_domain,
            severity=ir.IssueSeverity.WARNING, translation_key="x",
        )
    _clear_marketplace_restart(hass)
    assert set(ir.async_get(hass).issues) == {
        ("marketplace", "restart_required_2_tags/2026.11.26.01"),
        ("marketplace", "critical_x"),
        (DOMAIN, "restart_required_x"),
    }
