"""Offline behavior checks; no Home Assistant install or real HTTP is used."""

import importlib
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_NAME = "smartdaily_readonly_test"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(ROOT / "custom_components" / "smartdaily_postal_ha")]
sys.modules[PACKAGE_NAME] = package
api = importlib.import_module(PACKAGE_NAME + ".api")
model = importlib.import_module(PACKAGE_NAME + ".model")
tv = importlib.import_module(PACKAGE_NAME + ".tv")


class FakeResponse:
    def __init__(self, payload=None, status=200, error=None):
        self.payload = payload
        self.status = status
        self.error = error

    async def __aenter__(self):
        if self.error:
            raise self.error
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self, **kwargs):
        return self.payload


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def record(identifier, status=1):
    return {"pd_id": identifier, "p_status": status, "postal_typeText": "包裹"}


class ModelTests(unittest.TestCase):
    def test_malformed_snapshot_is_not_empty_success(self):
        for invalid in (None, {}, "", [{"p_status": 1}], [record("x", True)]):
            with self.subTest(invalid=invalid), self.assertRaises(model.InvalidSnapshot):
                model.normalize_packages(invalid)
        self.assertEqual(model.normalize_packages([]), ())

    def test_provider_ids_deduplicate_and_conflicts_fail(self):
        self.assertEqual(len(model.normalize_packages([record(1), record("1")])), 1)
        with self.assertRaises(model.InvalidSnapshot):
            model.normalize_packages([record(1, 1), record("1", 2)])

    def test_initial_active_packages_are_due_without_silent_baseline(self):
        ledger = model.DailyDeliveryLedger()
        self.assertEqual(ledger.due(model.normalize_packages([record("a")]), "2026-11-08"), ("a",))

    def test_same_day_restart_next_day_and_new_id(self):
        ledger = model.DailyDeliveryLedger()
        ledger.acknowledge({"a"}, "2026-11-08")
        restored = model.DailyDeliveryLedger.from_storage(ledger.ack_dates)
        packages = model.normalize_packages([record("a"), record("b")])
        self.assertEqual(restored.due(packages, "2026-11-08"), ("b",))
        self.assertEqual(restored.due(packages, "2026-11-09"), ("a", "b"))

    def test_failure_without_ack_retries_and_claimed_status_never_due(self):
        ledger = model.DailyDeliveryLedger()
        packages = model.normalize_packages([record("a"), record("b", 2), record("c", 9)])
        self.assertEqual(ledger.due(packages, "2026-11-08"), ("a",))
        self.assertEqual(ledger.due(packages, "2026-11-08"), ("a",))

    def test_disappearing_then_returning_id_stays_acknowledged_same_day(self):
        ledger = model.DailyDeliveryLedger({"a": "2026-11-08"})
        self.assertEqual(ledger.due((), "2026-11-08"), ())
        self.assertEqual(ledger.due(model.normalize_packages([record("a")]), "2026-11-08"), ())

    def test_invalid_saved_dates_are_not_treated_as_ack(self):
        ledger = model.DailyDeliveryLedger.from_storage({"a": "invalid", "b": "2026-11-08"})
        self.assertEqual(ledger.ack_dates, {"b": "2026-11-08"})


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_host_get_parameters_and_authorization(self):
        code = "FAKE-CODE+WITH/&?URL-CHARS"
        token = "FAKE-TOKEN"
        session = FakeSession(
            FakeResponse({"Data": {"token": token}}),
            FakeResponse({"Data": [record("p1")]}),
        )
        packages = await api.SmartdailyClient(session, code).packages("community1")
        self.assertEqual(packages[0].package_id, "p1")
        self.assertEqual(session.calls[0][0], api.BASE_URL + api.TOKEN_PATH)
        self.assertEqual(session.calls[0][1]["params"], {"code": code})
        self.assertNotIn("KingnetAuth", session.calls[0][1]["headers"])
        self.assertEqual(session.calls[1][0], api.BASE_URL + api.PACKAGES_PATH)
        self.assertEqual(session.calls[1][1]["headers"]["KingnetAuth"], "CommunityUser " + token)
        self.assertEqual(session.calls[1][1]["params"], {"com_id": "community1"})
        for _, kwargs in session.calls:
            self.assertIs(kwargs["allow_redirects"], False)
            self.assertEqual(kwargs["timeout"].total, 15)
            self.assertEqual(kwargs["timeout"].connect, 5)

    async def test_authorized_communities_normalize_ids(self):
        session = FakeSession(
            FakeResponse({"Data": {"token": "FAKE"}}),
            FakeResponse({"Data": [{"id": 12, "community": "測試社區"}]}),
        )
        self.assertEqual(
            await api.SmartdailyClient(session, "FAKE").communities(),
            {"12": "測試社區"},
        )

    async def test_http_auth_rejection_is_explicit(self):
        client = api.SmartdailyClient(FakeSession(FakeResponse(status=401)), "FAKE")
        with self.assertRaises(api.SmartdailyAuthError):
            await client.communities()

    async def test_malformed_token_stays_retryable_not_auth_failure(self):
        for data in (None, [], {}, {"token": ""}):
            client = api.SmartdailyClient(FakeSession(FakeResponse({"Data": data})), "FAKE")
            with self.assertRaises(api.SmartdailyResponseError):
                await client.communities()

    async def test_null_package_data_is_not_empty_mailbox(self):
        client = api.SmartdailyClient(
            FakeSession(
                FakeResponse({"Data": {"token": "FAKE"}}),
                FakeResponse({"Data": None}),
            ),
            "FAKE",
        )
        with self.assertRaises(api.SmartdailyResponseError):
            await client.packages("c1")

    async def test_transport_exception_never_echoes_secret_url(self):
        secret = "FAKE-SENSITIVE-CODE"
        session = FakeSession(
            FakeResponse(error=api.aiohttp.ClientError("https://provider/?code=" + secret))
        )
        with self.assertRaises(api.SmartdailyError) as caught:
            await api.SmartdailyClient(session, secret).communities()
        self.assertNotIn(secret, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    async def test_redirect_is_not_followed(self):
        session = FakeSession(FakeResponse(status=302))
        with self.assertRaises(api.SmartdailyError):
            await api.SmartdailyClient(session, "FAKE").communities()
        self.assertEqual(len(session.calls), 1)

    async def test_unlisted_endpoint_is_never_requested(self):
        session = FakeSession()
        with self.assertRaises(api.SmartdailyError):
            await api.SmartdailyClient(session, "FAKE")._get("/api/Postal/pickup")
        self.assertEqual(session.calls, [])

    async def test_tv_off_blocks_every_cloud_request(self):
        session = FakeSession()

        async def off():
            return False

        client = api.SmartdailyClient(session, "FAKE", request_guard=off)
        with self.assertRaises(api.SmartdailyPollingSkipped):
            await client.packages("community")
        self.assertEqual(session.calls, [])

    async def test_tv_turning_off_between_token_and_list_blocks_list(self):
        checks = iter((True, False))

        async def power():
            return next(checks)

        session = FakeSession(FakeResponse({"Data": {"token": "FAKE"}}))
        client = api.SmartdailyClient(session, "FAKE", request_guard=power)
        with self.assertRaises(api.SmartdailyPollingSkipped):
            await client.packages("community")
        self.assertEqual([url for url, _ in session.calls], [api.BASE_URL + api.TOKEN_PATH])


class TVGuardTests(unittest.IsolatedAsyncioTestCase):
    def test_only_literal_rfc1918_hosts_are_accepted(self):
        for host in ("192.168.10.20", "10.0.0.1", "172.31.255.1"):
            self.assertEqual(tv.private_tv_host(host), host)
        for host in ("127.0.0.1", "169.254.1.1", "8.8.8.8", "tv.local", "192.168.1.1:8001", "http://192.168.1.1", "::1"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                tv.private_tv_host(host)

    async def test_only_explicit_on_permits_cloud_and_no_credentials_sent_to_tv(self):
        for payload, expected in (({"device": {"PowerState": "on"}}, True), ({"device": {"PowerState": "off"}}, False), ({"device": {}}, False), ({}, False), ([], False), ({"device": {"PowerState": "On"}}, False)):
            session = FakeSession(FakeResponse(payload))
            self.assertIs(await tv.TVPowerGuard(session, "192.168.10.20").is_on(), expected)
            url, kwargs = session.calls[0]
            self.assertEqual(url, "http://192.168.10.20:8001/api/v2/")
            self.assertIs(kwargs["allow_redirects"], False)
            self.assertNotIn("KingnetAuth", kwargs["headers"])
            self.assertEqual(kwargs["timeout"].total, 3)

    async def test_unreachable_or_redirect_does_not_permit_cloud(self):
        for response in (FakeResponse(status=302), FakeResponse(error=api.aiohttp.ClientError("offline"))):
            self.assertIs(await tv.TVPowerGuard(FakeSession(response), "192.168.10.20").is_on(), False)


if __name__ == "__main__":
    unittest.main()
