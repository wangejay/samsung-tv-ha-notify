"""Locally maintained, read-only Smartdaily package integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SmartdailyClient
from .const import CONF_DEVICE_CODE, CONF_TV_HOST, DEFAULT_TV_HOST
from .coordinator import SmartdailyCoordinator
from .services import async_setup_services
from .tv import TVPowerGuard

PLATFORMS = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the local-only ACK action once, not once per community."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialize one selected, already-authorized community."""
    session = async_get_clientsession(hass)
    try:
        guard = TVPowerGuard(session, entry.data.get(CONF_TV_HOST, DEFAULT_TV_HOST))
    except ValueError:
        raise ConfigEntryError("A private IPv4 TV address is required") from None
    client = SmartdailyClient(session, entry.data[CONF_DEVICE_CODE], request_guard=guard.is_on)
    coordinator = SmartdailyCoordinator(hass, entry, client)
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload sensors; coordinator is registered for shutdown with this entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
