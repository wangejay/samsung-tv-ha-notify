"""Regression: HA 2025.7.1 can serialize the actual sender config form.

Only the HA ConfigFlow base is doubled. The real schema, IP validator,
voluptuous 0.15.2 and voluptuous-serialize 2.6.0 are exercised offline.
"""
import importlib
from pathlib import Path
import sys
import types

import voluptuous as vol
from voluptuous_serialize import convert


class ConfigFlow:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()


ha = types.ModuleType("homeassistant")
entries = types.ModuleType("homeassistant.config_entries")
entries.ConfigFlow = ConfigFlow
entries.ConfigFlowResult = dict
sys.modules["homeassistant"] = ha
sys.modules["homeassistant.config_entries"] = entries
package = types.ModuleType("sender_schema_test")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/samsung_nui_notify")]
sys.modules[package.__name__] = package
flow = importlib.import_module(package.__name__ + ".config_flow")
serialized = convert(flow.SCHEMA)
assert {row["name"] for row in serialized} == {"tv_ip", "local_ip", "http_port", "udp_port", "ensure_receiver"}
assert all(isinstance(row, dict) for row in serialized)
assert flow._ip("192.168.10.20") == "192.168.10.20"
# Loopback is intentionally allowed by transport for localhost-only tests.
assert flow._ip("127.0.0.1") == "127.0.0.1"
for bad in ("example.org", "https://example.org", "8.8.8.8", "::1"):
    try:
        flow._ip(bad)
    except vol.Invalid:
        pass
    else:
        raise AssertionError("non-private literal IPv4 accepted")
print("PASS: config form serializes; private IPv4 submission validation remains active")
