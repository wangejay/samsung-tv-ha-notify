"""Small read-only client for the provider endpoints identified by upstream.

These are undocumented provider endpoints, not an official integration contract.
Never log request URLs, headers, DeviceCodes, token responses, or response bodies.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .model import InvalidSnapshot, Package, normalize_packages

BASE_URL = "https://api.smartdaily.com.tw"
TOKEN_PATH = "/api/Valid/getHashCodeV2"
COMMUNITIES_PATH = "/api/Community/GetUserCommunityList"
PACKAGES_PATH = "/api/Postal/getUserPostalList"
ALLOWED_PATHS = frozenset((TOKEN_PATH, COMMUNITIES_PATH, PACKAGES_PATH))
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5)


class SmartdailyError(Exception):
    """Sanitized provider error: no upstream exception text or body is retained."""


class SmartdailyAuthError(SmartdailyError):
    """DeviceCode or community authorization was rejected."""


class SmartdailyResponseError(SmartdailyError):
    """A provider response did not match the expected schema."""


class SmartdailyPollingSkipped(Exception):
    """The configured TV is not explicitly on; no cloud request was made."""


class SmartdailyClient:
    """Read token, authorized communities, and package snapshots only."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        device_code: str,
        *,
        request_guard: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        self._session = session
        self._device_code = device_code
        self._request_guard = request_guard

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        if path not in ALLOWED_PATHS:
            raise SmartdailyError("unsupported_endpoint")
        # Recheck before *each* runtime token/list request. Setup and reauth
        # deliberately have no guard, allowing explicitly requested setup reads.
        if self._request_guard is not None and not await self._request_guard():
            raise SmartdailyPollingSkipped("tv_not_explicitly_on")
        headers = {"Accept": "application/json"}
        if token is not None:
            headers["KingnetAuth"] = "CommunityUser " + token
        try:
            async with self._session.get(
                BASE_URL + path,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
            ) as response:
                if response.status in (401, 403):
                    raise SmartdailyAuthError("authorization_rejected")
                if response.status != 200:
                    raise SmartdailyError("provider_http_error")
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError):
            raise SmartdailyError("provider_unreachable") from None
        except ValueError:
            raise SmartdailyResponseError("invalid_json") from None
        if not isinstance(payload, dict):
            raise SmartdailyResponseError("invalid_response_envelope")
        return payload

    async def _get_token(self) -> str:
        payload = await self._get(TOKEN_PATH, params={"code": self._device_code})
        data = payload.get("Data")
        if not isinstance(data, dict):
            raise SmartdailyResponseError("invalid_token_response")
        token = data.get("token")
        if not isinstance(token, str) or not token.strip():
            raise SmartdailyResponseError("invalid_token_response")
        return token

    async def communities(self) -> dict[str, str]:
        token = await self._get_token()
        payload = await self._get(COMMUNITIES_PATH, token=token)
        data = payload.get("Data")
        if not isinstance(data, list):
            raise SmartdailyResponseError("invalid_community_list")
        result: dict[str, str] = {}
        for community in data:
            if not isinstance(community, dict):
                raise SmartdailyResponseError("invalid_community_record")
            identifier = community.get("id")
            name = community.get("community")
            if (
                isinstance(identifier, bool)
                or not isinstance(identifier, (str, int))
                or not str(identifier).strip()
                or not isinstance(name, str)
                or not name.strip()
            ):
                raise SmartdailyResponseError("invalid_community_record")
            result[str(identifier)] = name
        return result

    async def packages(self, community_id: str) -> tuple[Package, ...]:
        # Like upstream, obtain a fresh short-lived token per polling cycle.
        token = await self._get_token()
        payload = await self._get(
            PACKAGES_PATH, params={"com_id": community_id}, token=token
        )
        try:
            return normalize_packages(payload.get("Data"))
        except InvalidSnapshot:
            raise SmartdailyResponseError("invalid_package_snapshot") from None
