"""Read-only power guard; never launch, wake, pair, or control the TV."""

from ipaddress import IPv4Address, IPv4Network

import aiohttp

PRIVATE_NETWORKS = tuple(
    IPv4Network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
TV_TIMEOUT = aiohttp.ClientTimeout(total=3, connect=2)


def private_tv_host(value: str) -> str:
    """Allow literal RFC1918 IPv4 only, with no port, hostname, or URL."""
    if not isinstance(value, str):
        raise ValueError("invalid_tv_host")
    try:
        address = IPv4Address(value.strip())
    except ValueError:
        raise ValueError("invalid_tv_host") from None
    if not any(address in network for network in PRIVATE_NETWORKS):
        raise ValueError("invalid_tv_host")
    return str(address)


class TVPowerGuard:
    """Only an explicit PowerState 'on' permits a provider request."""

    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        self._session = session
        self._url = f"http://{private_tv_host(host)}:8001/api/v2/"

    async def is_on(self) -> bool:
        try:
            async with self._session.get(
                self._url,
                timeout=TV_TIMEOUT,
                allow_redirects=False,
                headers={"Accept": "application/json"},
            ) as response:
                if response.status != 200:
                    return False
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return False
        return (
            isinstance(payload, dict)
            and isinstance(payload.get("device"), dict)
            and payload["device"].get("PowerState") == "on"
        )
