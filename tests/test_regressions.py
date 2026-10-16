"""Regression coverage for review findings M3 through M7."""

from unittest.mock import patch

from aionut import NUTError
import probatio
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_ALIAS,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.nut import MAX_OUTLETS, outlet_numbers_from_status
from custom_components.nut.config_flow import PASSWORD_NOT_CHANGED
from custom_components.nut.const import DOMAIN, INTEGRATION_SUPPORTED_COMMANDS
from custom_components.nut.device_action import ACTION_SCHEMA, async_get_actions


def make_entry(hass, *, unique_id=None, password="saved-password"):
    """Register a config entry without starting real network traffic."""
    data = {CONF_HOST: "mock", CONF_PORT: 3493, CONF_USERNAME: "user"}
    if password is not None:
        data[CONF_PASSWORD] = password
    entry = MockConfigEntry(domain=DOMAIN, unique_id=unique_id, data=data)
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize("password", ["saved-password", None])
@pytest.mark.parametrize("aliases", [1, 2])
@pytest.mark.parametrize("submitted", [PASSWORD_NOT_CHANGED, "new-password"])
async def test_reconfigure_validates_resolved_password(
    hass, mock_nut_client, password, aliases, submitted
):
    """Every alias validation uses the real password and preserves storage."""
    entry = make_entry(hass, password=password)
    mock_nut_client.list_ups.return_value = {
        f"ups{number}": f"UPS {number}" for number in range(1, aliases + 1)
    }
    result = await entry.start_reconfigure_flow(hass)
    expected_password = password if submitted == PASSWORD_NOT_CHANGED else submitted
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "mock",
                CONF_PORT: 3493,
                CONF_USERNAME: "user",
                CONF_PASSWORD: submitted,
            },
        )
        assert mock_nut_client.factory.call_args.args[3] == expected_password
        if aliases > 1:
            assert result["step_id"] == "reconfigure_ups"
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_ALIAS: "ups2"}
            )
            assert mock_nut_client.factory.call_count == 2
            assert mock_nut_client.factory.call_args.args[3] == expected_password
        assert result["reason"] == "reconfigure_successful"
        assert entry.data.get(CONF_PASSWORD) == expected_password
        if expected_password is None:
            assert CONF_PASSWORD not in entry.data


async def test_reconfigure_without_password_field(hass, mock_nut_client):
    """Entries and submissions without passwords do not raise KeyError."""
    entry = make_entry(hass, password=None)
    result = await entry.start_reconfigure_flow(hass)
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "mock", CONF_PORT: 3493}
        )
    assert result["reason"] == "reconfigure_successful"
    assert CONF_PASSWORD not in entry.data


@pytest.mark.parametrize(
    "status",
    [
        {"ups.status": "OL"},
        {"ups.status": "OL", "ups.serial": "serial"},
        {"ups.status": "OL", "ups.serial": "serial", "ups.mfr": "Maker"},
        {"ups.status": "OL", "ups.serial": "serial", "ups.model": "Model"},
        {"ups.status": "OL", "ups.serial": "unknown"},
    ],
)
async def test_established_identity_survives_reload(
    hass, mock_nut_client, entity_registry, device_registry, status
):
    """Incomplete status must reuse existing devices and entities."""
    entry = make_entry(hass, unique_id="Maker_Model_serial")
    mock_nut_client.list_vars.return_value = {
        "ups.mfr": "Maker",
        "ups.model": "Model",
        "ups.serial": "serial",
        "ups.status": "OL",
    }
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    device = dr.async_entries_for_config_entry(device_registry, entry.entry_id)[0]
    mock_nut_client.list_vars.return_value = status
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.unique_id == "Maker_Model_serial"
    assert (
        er.async_entries_for_config_entry(entity_registry, entry.entry_id) == entities
    )
    assert [
        current.id
        for current in dr.async_entries_for_config_entry(
            device_registry, entry.entry_id
        )
    ] == [device.id]
    mock_nut_client.list_vars.return_value = {
        "ups.status": "OL",
        "ups.mfr": "Maker",
        "ups.model": "Model",
        "ups.serial": "serial",
    }
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert entry.runtime_data.unique_id == entry.unique_id == "Maker_Model_serial"
    assert (
        er.async_entries_for_config_entry(entity_registry, entry.entry_id) == entities
    )


async def test_legacy_entry_identity(hass, mock_nut_client, entity_registry):
    """Serial-less legacy entries keep using their entry ID after reload."""
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert entry.unique_id is None
    assert entry.runtime_data.unique_id == entry.entry_id
    mock_nut_client.list_vars.return_value = {
        "ups.status": "OL",
        "ups.serial": "newly-available-serial",
    }
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        er.async_entries_for_config_entry(entity_registry, entry.entry_id) == entities
    )
    assert entry.runtime_data.unique_id == entry.entry_id


@pytest.mark.parametrize("initial", [{}, {"ups.status": "(null)"}])
async def test_empty_initial_status_is_not_ready(hass, mock_nut_client, initial):
    """An empty snapshot retries before creating devices or entities."""
    mock_nut_client.list_vars.return_value = initial
    entry = make_entry(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    mock_nut_client.list_vars.return_value = {"ups.status": "OL"}
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize("delayed_outlets", [False, True])
async def test_late_discovery_and_command_retry(
    hass, mock_nut_client, entity_registry, delayed_outlets
):
    """Discover new sensors and controls once, even after LIST CMD failed."""
    outlet_status = {
        "outlet.1.current": "1.2",
        "outlet.1.switchable": "yes",
        "outlet.1.status": "on",
    }
    mock_nut_client.list_vars.return_value = {"ups.status": "OL"} | (
        {} if delayed_outlets else outlet_status
    )
    commands = {f"outlet.1.load.{command}" for command in ("on", "off", "cycle")}
    mock_nut_client.list_commands.side_effect = [
        NUTError("try later"),
        commands,
        commands,
    ]
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    initial = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    mock_nut_client.list_vars.return_value |= outlet_status | {
        "input.1.voltage": "230",
        "input.2.voltage": "231",
        "battery.charge": "95",
    }
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    keys = {entity.unique_id.removeprefix(f"{entry.entry_id}_") for entity in entries}
    assert {
        "input.1.voltage",
        "input.2.voltage",
        "battery.charge",
        "outlet.1.current",
        "outlet.1.load.cycle",
        "outlet.1.load.poweronoff",
    } <= keys
    assert len(entries) > len(initial)
    assert entry.runtime_data.user_available_commands == commands
    for _ in range(2):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert mock_nut_client.list_commands.await_count == 2
    assert er.async_entries_for_config_entry(entity_registry, entry.entry_id) == entries
    # Verify the controls created by the retry actually work through HA services.
    for entity in entries:
        if entity.domain == "button":
            await hass.services.async_call(
                "button", "press", {"entity_id": entity.entity_id}, blocking=True
            )
    mock_nut_client.run_command.assert_awaited_once_with("ups1", "outlet.1.load.cycle")
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not coordinator._listeners
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert er.async_entries_for_config_entry(entity_registry, entry.entry_id) == entries


async def test_retry_commands_with_unchanged_status(
    hass, mock_nut_client, entity_registry
):
    """A successful command retry notifies discovery despite identical status."""
    mock_nut_client.list_vars.return_value = {
        "ups.status": "OL",
        "outlet.count": "1",
        "outlet.1.switchable": "yes",
        "outlet.1.status": "on",
    }
    mock_nut_client.list_commands.side_effect = [
        NUTError("try later"),
        {"outlet.1.load.on", "outlet.1.load.off", "outlet.1.load.cycle"},
    ]
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.states.async_all("switch")
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(hass.states.async_all("switch")) == 1
    assert len(hass.states.async_all("button")) == 1


async def test_cached_commands_with_late_outlets(hass, mock_nut_client):
    """Commands from a successful LIST CMD become usable when outlets appear."""
    commands = {f"outlet.2.load.{command}" for command in ("on", "off", "cycle")}
    mock_nut_client.list_commands.return_value = commands
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not entry.runtime_data.user_available_commands
    mock_nut_client.list_vars.return_value = {
        "ups.status": "OL",
        "outlet.2.status": "on",
        "outlet.2.switchable": "yes",
    }
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert entry.runtime_data.user_available_commands == commands
    assert len(hass.states.async_all("switch")) == 1
    assert len(hass.states.async_all("button")) == 1
    mock_nut_client.list_commands.assert_awaited_once()


async def test_empty_command_list_is_successful(hass, mock_nut_client):
    """A genuinely empty command list is not retried on every poll."""
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await entry.runtime_data.coordinator.async_refresh()
    mock_nut_client.list_commands.assert_awaited_once()


@pytest.mark.parametrize(
    "count",
    ["-1", "1.5", "many", "1025", "9999999999", "²", "１", " 2", "+2", "9" * 5000],
)
def test_invalid_outlet_counts(count):
    """Reject invalid counts before allocating a set or converting huge integers."""
    with pytest.raises(NUTError, match="Invalid outlet.count"):
        outlet_numbers_from_status({"outlet.count": count})


@pytest.mark.parametrize("count", [0, 1, MAX_OUTLETS])
def test_bounded_outlet_counts(count):
    """Accept bounded device counts, including no outlets."""
    assert outlet_numbers_from_status({"outlet.count": str(count)}) == set(
        range(1, count + 1)
    )


def test_fallback_outlet_indices():
    """Only bounded plain ASCII decimal indices are accepted."""
    status = {
        f"outlet.{number}.status": "on"
        for number in (
            "1",
            "12",
            "²",
            "١",
            "+2",
            "-3",
            "1.5",
            " 4",
            "0",
            "1025",
            "9" * 5000,
        )
    }
    assert outlet_numbers_from_status(status) == {1, 12}


@pytest.mark.parametrize("count", ["bad", "9999999999"])
async def test_invalid_count_is_controlled_setup_retry(hass, mock_nut_client, count):
    """Bad device data must not escape as an unexpected error during setup."""
    mock_nut_client.list_vars.return_value = {"ups.status": "OL", "outlet.count": count}
    entry = make_entry(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_every_advertised_action_passes_schema(
    hass, mock_nut_client, device_registry
):
    """Numbered outlet controls must never leak into unsupported device actions."""
    mock_nut_client.list_vars.return_value = {"ups.status": "OL", "outlet.count": "2"}
    mock_nut_client.list_commands.return_value = INTEGRATION_SUPPORTED_COMMANDS | {
        "outlet.1.load.on",
        "outlet.2.load.off",
        "outlet.2.load.cycle",
        "unknown.command",
    }
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    device = dr.async_entries_for_config_entry(device_registry, entry.entry_id)[0]
    actions = await async_get_actions(hass, device.id)
    assert {action["type"] for action in actions} == {
        command.replace(".", "_") for command in INTEGRATION_SUPPORTED_COMMANDS
    }
    for action in actions:
        assert ACTION_SCHEMA(action)["type"] == action["type"]
    with pytest.raises(probatio.Invalid):
        ACTION_SCHEMA(
            {"device_id": device.id, "domain": DOMAIN, "type": "arbitrary_string"}
        )
