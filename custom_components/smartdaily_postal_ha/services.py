"""Local delivery acknowledgment only; no provider mutation or refresh."""

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN, SERVICE_ACKNOWLEDGE
from .coordinator import SmartdailyCoordinator


def async_setup_services(hass: HomeAssistant) -> None:
    """Register once, resolving the target entry dynamically for each call."""

    async def acknowledge(call: ServiceCall) -> None:
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError("Smartdaily entry is not available")
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError("Smartdaily entry is not loaded")
        coordinator = getattr(entry, "runtime_data", None)
        if not isinstance(coordinator, SmartdailyCoordinator):
            raise ServiceValidationError("Smartdaily entry is not loaded")
        await coordinator.async_acknowledge(call.data["package_ids"])

    hass.services.async_register(
        DOMAIN,
        SERVICE_ACKNOWLEDGE,
        acknowledge,
        schema=vol.Schema(
            {
                vol.Required("entry_id"): vol.All(str, vol.Length(min=1)),
                vol.Required("package_ids"): [vol.All(str, vol.Length(min=1))],
            }
        ),
    )
