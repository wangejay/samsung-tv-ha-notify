"""TV-gated HA polling with a persistent per-package daily delivery ledger."""

import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    SmartdailyAuthError,
    SmartdailyClient,
    SmartdailyError,
    SmartdailyPollingSkipped,
)
from .const import CONF_COMMUNITY_ID, DOMAIN, EVENT_NEW_PACKAGE, POLL_SECONDS
from .model import DailyDeliveryLedger, Package

_LOGGER = logging.getLogger(__name__)


class SmartdailyCoordinator(DataUpdateCoordinator[tuple[Package, ...] | None]):
    """Only a successful local delivery ACK marks a package notified today."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: SmartdailyClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLL_SECONDS),
        )
        self._client = client
        self._entry = entry
        self._entry_id = entry.entry_id
        self._community_id = entry.data[CONF_COMMUNITY_ID]
        self._ledger = DailyDeliveryLedger()
        self._pending: set[str] = set()
        self._state_lock = asyncio.Lock()
        self._closing = False
        self._store = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}", private=True, atomic_writes=True
        )

    def _today(self) -> str:
        return dt_util.now(self._timezone).date().isoformat()

    async def async_initialize(self) -> None:
        """Restore successful delivery dates before the first actual snapshot."""
        self._timezone = await dt_util.async_get_time_zone("Asia/Taipei")
        if self._timezone is None:
            raise ConfigEntryError("Asia/Taipei timezone is not available")
        state = await self._store.async_load()
        if isinstance(state, dict):
            self._ledger = DailyDeliveryLedger.from_storage(state.get("ack_dates"))

    async def async_acknowledge(self, package_ids: list[str]) -> None:
        """Acknowledge only IDs emitted and still pending in this HA instance."""
        async with self._state_lock:
            if self._closing:
                return
            acknowledged = self._pending.intersection(package_ids)
            if not acknowledged:
                return
            ledger = DailyDeliveryLedger(self._ledger.ack_dates)
            ledger.acknowledge(acknowledged, self._today())
            # HA Store is best-effort durable state, not a TV/bus transaction.
            await self._store.async_save({"ack_dates": ledger.ack_dates})
            self._ledger = ledger
            self._pending.difference_update(acknowledged)

    async def async_shutdown(self) -> None:
        """Prevent late events/writes and drain any already-started local ACK."""
        self._closing = True
        await super().async_shutdown()
        async with self._state_lock:
            pass

    async def _async_update_data(self) -> tuple[Package, ...] | None:
        if self._closing:
            return self.data
        try:
            packages = await self._client.packages(self._community_id)
        except SmartdailyPollingSkipped:
            # None means no actual snapshot yet, not a zero-item baseline.
            return self.data
        except SmartdailyAuthError:
            raise ConfigEntryAuthFailed("Smartdaily authorization rejected") from None
        except SmartdailyError:
            raise UpdateFailed("Smartdaily package update failed") from None
        async with self._state_lock:
            if self._closing:
                return self.data
            due = self._ledger.due(packages, self._today())
            self._pending = set(due)
        count = sum(package.status == 1 for package in packages)
        # First refresh runs before LOADED; defer its notification until a
        # normal poll so a successful TV delivery can be acknowledged safely.
        if due and self._entry.state is ConfigEntryState.LOADED:
            self.hass.bus.async_fire(
                EVENT_NEW_PACKAGE,
                {
                    "entry_id": self._entry_id,
                    "community_id": self._community_id,
                    "package_ids": list(due),
                    "due_count": len(due),
                    "unclaimed_count": count,
                },
            )
        return packages
