"""One credential-free count entity; package IDs are attributes for automations."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_COMMUNITY_NAME, DOMAIN
from .coordinator import SmartdailyCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a single coordinator-backed sensor; no camera or external image URL."""
    async_add_entities([UnclaimedPackageSensor(entry.runtime_data, entry)])


class UnclaimedPackageSensor(CoordinatorEntity[SmartdailyCoordinator], SensorEntity):
    """Unclaimed count and stable IDs; never publish the DeviceCode or token."""

    _attr_has_entity_name = True
    _attr_name = "未領包裹"
    _attr_icon = "mdi:package-variant-closed"
    _attr_native_unit_of_measurement = "件"

    def __init__(self, coordinator: SmartdailyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_unclaimed"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data[CONF_COMMUNITY_NAME],
            "manufacturer": "智生活科技",
        }

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return sum(package.status == 1 for package in self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, list[str]] | None:
        if self.coordinator.data is None:
            return None
        return {
            "unclaimed_package_ids": sorted(
                package.package_id
                for package in self.coordinator.data
                if package.status == 1
            )
        }
