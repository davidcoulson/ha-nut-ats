"""The NUT coordinator."""

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, override

from aionut import NUTError, NUTLoginError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, INTEGRATION_SUPPORTED_COMMANDS

if TYPE_CHECKING:
    from . import PyNUTData

_LOGGER = logging.getLogger(__name__)


@dataclass
class NutRuntimeData:
    """Runtime data definition."""

    coordinator: "NutCoordinator"
    data: PyNUTData
    unique_id: str
    user_available_commands: set[str]


type NutConfigEntry = ConfigEntry[NutRuntimeData]


class NutCoordinator(DataUpdateCoordinator[dict[str, str]]):
    """Coordinator for NUT data."""

    config_entry: NutConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        data: PyNUTData,
        config_entry: NutConfigEntry,
    ) -> None:
        """Initialize NUT coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="NUT resource status",
            update_interval=timedelta(seconds=60),
            # Command discovery may change even when the status is unchanged.
            always_update=True,
        )
        self._data = data
        self._commands: set[str] | None = None
        self.user_available_commands: set[str] = set()

    @override
    async def _async_update_data(self) -> dict[str, str]:
        """Fetch data from NUT."""
        try:
            # Import here to avoid a circular import with integration setup.
            from . import outlet_numbers_from_status

            status = await self._data.async_update()
            if not status:
                raise NUTError("Empty NUT status")
            outlet_numbers = outlet_numbers_from_status(status)
            if (
                self.config_entry.data.get(CONF_USERNAME) is not None
                and self.config_entry.data.get(CONF_PASSWORD) is not None
            ):
                # None means retrieval failed; an empty set is a successful result.
                if self._commands is None:
                    commands = await self._data.async_list_commands()
                    if commands is not None:
                        self._commands = set(commands)
                valid_commands = INTEGRATION_SUPPORTED_COMMANDS | {
                    f"outlet.{number}.load.{command}"
                    for number in outlet_numbers
                    for command in ("on", "off", "cycle")
                }
                self.user_available_commands.update(
                    (self._commands or set()) & valid_commands
                )
            return status
        except NUTLoginError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="device_authentication",
                translation_placeholders={
                    "err": str(err),
                },
            ) from err
        except NUTError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="data_fetch_error",
                translation_placeholders={
                    "err": str(err),
                },
            ) from err
