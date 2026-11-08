"""Exercise coordinator state with small HA API doubles, never a live HA/TV."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
import importlib
from pathlib import Path
import sys
import types
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
TAIPEI = ZoneInfo("Asia/Taipei")
CLOCK = [datetime(2026, 11, 8, 4, 0, tzinfo=timezone.utc)]


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    sys.modules[name] = result
    return result


class EntryState(Enum):
    LOADED = "loaded"
    SETUP_IN_PROGRESS = "setup"


class FakeCoordinator:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, logger, **kwargs):
        self.hass = hass
        self.data = None
        self.update_interval = kwargs["update_interval"]

    async def async_shutdown(self):
        return


class FakeStore:
    database = {}

    def __init__(self, hass, version, key, **kwargs):
        self.key = key

    async def async_load(self):
        return deepcopy(self.database.get(self.key))

    async def async_save(self, data):
        self.database[self.key] = deepcopy(data)


async def get_timezone(name):
    return TAIPEI if name == "Asia/Taipei" else None


module("homeassistant")
module("homeassistant.config_entries", ConfigEntry=object, ConfigEntryState=EntryState)
module("homeassistant.core", HomeAssistant=object)
module("homeassistant.exceptions", ConfigEntryAuthFailed=type("AuthFailed", (Exception,), {}), ConfigEntryError=type("EntryError", (Exception,), {}))
module("homeassistant.helpers")
module("homeassistant.helpers.storage", Store=FakeStore)
module("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=FakeCoordinator, UpdateFailed=type("UpdateFailed", (Exception,), {}))
module("homeassistant.util")
module("homeassistant.util.dt", async_get_time_zone=get_timezone, now=lambda tz: CLOCK[0].astimezone(tz))
PACKAGE_NAME = "smartdaily_coordinator_test"
package = module(PACKAGE_NAME)
package.__path__ = [str(ROOT / "custom_components" / "smartdaily_postal_ha")]
coordinator_module = importlib.import_module(PACKAGE_NAME + ".coordinator")
model = importlib.import_module(PACKAGE_NAME + ".model")
api = importlib.import_module(PACKAGE_NAME + ".api")


class FakeBus:
    def __init__(self):
        self.events = []

    def async_fire(self, event, data):
        self.events.append((event, data))


class FakeClient:
    def __init__(self):
        self.result = ()
        self.started = None
        self.release = None

    async def packages(self, community_id):
        if self.started:
            self.started.set()
            await self.release.wait()
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def packages(*items):
    return model.normalize_packages([{"pd_id": identifier, "p_status": status} for identifier, status in items])


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        FakeStore.database.clear()
        CLOCK[0] = datetime(2026, 11, 8, 4, 0, tzinfo=timezone.utc)
        self.bus = FakeBus()
        self.hass = types.SimpleNamespace(bus=self.bus)
        self.entry = types.SimpleNamespace(entry_id="test-entry", data={"community_id": "test-community"}, state=EntryState.LOADED)
        self.client = FakeClient()
        self.coordinator = coordinator_module.SmartdailyCoordinator(self.hass, self.entry, self.client)
        await self.coordinator.async_initialize()

    async def poll(self):
        self.coordinator.data = await self.coordinator._async_update_data()

    async def test_interval_and_off_before_first_snapshot_never_fake_zero(self):
        self.assertEqual(self.coordinator.update_interval.total_seconds(), 900)
        self.client.result = api.SmartdailyPollingSkipped("off")
        await self.poll()
        self.assertIsNone(self.coordinator.data)
        self.assertEqual(self.bus.events, [])
        self.assertEqual(FakeStore.database, {})

    async def test_group_retry_ack_same_day_restart_and_only_new_id(self):
        self.client.result = packages(("a", 1), ("b", 1), ("collected", 2))
        await self.poll()
        self.assertEqual(self.bus.events[-1][1]["package_ids"], ["a", "b"])
        await self.poll()  # No TV acknowledgment: retry the same group.
        self.assertEqual(len(self.bus.events), 2)
        await self.coordinator.async_acknowledge(["a", "b", "unknown"])
        self.assertNotIn("unknown", self.coordinator._ledger.ack_dates)
        self.coordinator = coordinator_module.SmartdailyCoordinator(self.hass, self.entry, self.client)
        await self.coordinator.async_initialize()
        await self.poll()
        self.assertEqual(len(self.bus.events), 2)
        self.client.result = packages(("a", 1), ("b", 1), ("c", 1))
        await self.poll()
        self.assertEqual(self.bus.events[-1][1]["package_ids"], ["c"])

    async def test_taipei_midnight_makes_same_unclaimed_package_due_next_day(self):
        CLOCK[0] = datetime(2026, 11, 8, 15, 59, tzinfo=timezone.utc)
        self.client.result = packages(("a", 1))
        await self.poll()
        await self.coordinator.async_acknowledge(["a"])
        self.assertEqual(self.coordinator._ledger.ack_dates["a"], "2026-11-08")
        CLOCK[0] = datetime(2026, 11, 8, 16, 0, tzinfo=timezone.utc)
        await self.poll()
        self.assertEqual(self.bus.events[-1][1]["package_ids"], ["a"])
        self.assertEqual(self.coordinator._today(), "2026-11-09")

    async def test_collected_package_never_emits_and_off_retains_snapshot(self):
        self.client.result = packages(("a", 2))
        await self.poll()
        snapshot = self.coordinator.data
        self.client.result = api.SmartdailyPollingSkipped("off")
        await self.poll()
        self.assertIs(self.coordinator.data, snapshot)
        self.assertEqual(self.bus.events, [])

    async def test_setup_refresh_defers_notice_until_loaded_and_ack_is_possible(self):
        self.entry.state = EntryState.SETUP_IN_PROGRESS
        self.client.result = packages(("a", 1))
        await self.poll()
        self.assertEqual(self.bus.events, [])
        self.entry.state = EntryState.LOADED
        await self.poll()
        await self.coordinator.async_acknowledge(["a"])
        await self.poll()
        self.assertEqual(len(self.bus.events), 1)

    async def test_unload_during_fetch_suppresses_late_event(self):
        self.client.result = packages(("a", 1))
        self.client.started = asyncio.Event()
        self.client.release = asyncio.Event()
        update = asyncio.create_task(self.poll())
        await self.client.started.wait()
        await self.coordinator.async_shutdown()
        self.client.release.set()
        await update
        self.assertEqual(self.bus.events, [])
        self.assertIsNone(self.coordinator.data)

    async def test_ack_waiting_on_lock_does_not_write_after_shutdown(self):
        self.client.result = packages(("a", 1))
        await self.poll()
        await self.coordinator._state_lock.acquire()
        ack = asyncio.create_task(self.coordinator.async_acknowledge(["a"]))
        shutdown = asyncio.create_task(self.coordinator.async_shutdown())
        await asyncio.sleep(0)
        self.coordinator._state_lock.release()
        await asyncio.gather(ack, shutdown)
        self.assertEqual(FakeStore.database, {})


if __name__ == "__main__":
    unittest.main()
