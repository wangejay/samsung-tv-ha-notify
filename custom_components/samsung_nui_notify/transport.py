"""Bounded native receiver protocol; no HA imports or persistent listener."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import ipaddress
import json
import secrets
import socket

from aiohttp import ClientError, ClientSession, ClientTimeout, web

from .const import ACK_TIMEOUT, APP_ID, IMAGE_PATH, IMAGE_TTL, OVERLAY


class DeliveryError(Exception):
    """Delivery was not confirmed. Safe message does not contain notification text."""


def private_ipv4(value: object) -> str:
    """Require a literal private IPv4 address (loopback enables local-only tests)."""
    if not isinstance(value, str):
        raise ValueError("address must be a literal string")
    address = ipaddress.IPv4Address(value)
    if not any(address in network for network in (
        ipaddress.IPv4Network("10.0.0.0/8"),
        ipaddress.IPv4Network("172.16.0.0/12"),
        ipaddress.IPv4Network("192.168.0.0/16"),
        ipaddress.IPv4Network("127.0.0.0/8"),
    )):
        raise ValueError("address must be a private LAN IPv4 address")
    return str(address)


@dataclass(frozen=True)
class Settings:
    tv_ip: str
    local_ip: str
    http_port: int = 8123
    udp_port: int = 18110

    def __post_init__(self) -> None:
        private_ipv4(self.tv_ip)
        private_ipv4(self.local_ip)
        for port in (self.http_port, self.udp_port):
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError("ports must be integers in 1..65535")


@dataclass
class ImageLease:
    png: bytes
    tv_ip: str
    expires_at: float
    served: asyncio.Future[None]
    expiry_handle: asyncio.TimerHandle | None = None


class ImageStore:
    """Short-lived in-memory images served by HA's existing HTTP server."""

    def __init__(self) -> None:
        self.images: dict[str, ImageLease] = {}

    def issue(self, png: bytes, tv_ip: str, ttl: float = IMAGE_TTL) -> tuple[str, ImageLease]:
        loop = asyncio.get_running_loop()
        token = secrets.token_urlsafe(32)
        lease = ImageLease(png, tv_ip, loop.time() + ttl, loop.create_future())
        self.images[token] = lease
        lease.expiry_handle = loop.call_later(ttl, self.remove, token)
        return token, lease

    def remove(self, token: str) -> None:
        lease = self.images.pop(token, None)
        if lease is not None and lease.expiry_handle is not None:
            lease.expiry_handle.cancel()

    async def get(self, request: web.Request, token: str) -> web.StreamResponse:
        """Only the direct TV TCP peer may consume this single-use token."""
        peer = request.transport.get_extra_info("peername") if request.transport else None
        lease = self.images.get(token)
        if (
            lease is None or len(token) > 64 or not peer
            or peer[0] != lease.tv_ip
            or asyncio.get_running_loop().time() >= lease.expires_at
        ):
            raise web.HTTPNotFound()
        # Claim synchronously before the first await; concurrent/replayed GETs fail.
        self.remove(token)
        response = web.StreamResponse(status=200, headers={
            "Content-Type": "image/png",
            "Content-Length": str(len(lease.png)),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        })
        try:
            async with asyncio.timeout(3):
                await response.prepare(request)
                await response.write(lease.png)
                await response.write_eof()
            if not lease.served.done():
                lease.served.set_result(None)
        except (ConnectionError, TimeoutError, OSError) as error:
            if not lease.served.done():
                lease.served.set_exception(DeliveryError("TV image transfer did not complete"))
            raise web.HTTPServiceUnavailable() from error
        return response


class AckProtocol(asyncio.DatagramProtocol):
    """Accept only exact request ID and configured TV IP/port."""

    def __init__(self, request_id: str, settings: Settings) -> None:
        self.expected = f"ack {request_id}".encode()
        self.peer = (settings.tv_ip, settings.udp_port)
        self.ack: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if addr == self.peer and data == self.expected and not self.ack.done():
            self.ack.set_result(None)

    def error_received(self, error: Exception) -> None:
        if not self.ack.done():
            self.ack.set_exception(DeliveryError("TV UDP socket reported a network error"))


async def _get_tv_json(session: ClientSession, url: str) -> dict:
    async with session.get(
        url, timeout=ClientTimeout(total=3), allow_redirects=False,
    ) as response:
        if response.status != 200:
            raise DeliveryError("TV state unavailable (non-200 response); nothing was sent")
        body = await response.content.read(16385)
        if len(body) > 16384:
            raise DeliveryError("TV returned an unexpected state response")
        state = json.loads(body)
        if not isinstance(state, dict):
            raise DeliveryError("TV returned an unexpected state response")
        return state


async def check_receiver_running(
    session: ClientSession, tv_ip: str, *, ensure_receiver: bool = False, port: int = 8001,
) -> None:
    """Require on + running; optional fixed-app launch, never wake/close/install."""
    try:
        async with asyncio.timeout(10):
            base = f"http://{tv_ip}:{port}/api/v2/"
            device = (await _get_tv_json(session, base)).get("device")
            if not isinstance(device, dict) or device.get("PowerState") != "on":
                raise DeliveryError("TV is off/standby or power state is unconfirmed; nothing was sent")
            app_url = base + f"applications/{APP_ID}"
            state = await _get_tv_json(session, app_url)
            if type(state.get("running")) is not bool:
                raise DeliveryError("TV returned an unexpected app-state response")
            if state["running"]:
                return
            if not ensure_receiver:
                raise DeliveryError("TV native overlay app is not running; nothing was sent")
            # Opt-in only until this TV's REST launch has been physically verified.
            # No user-supplied URL/appid, no pairing token, no power command.
            async with session.post(
                app_url, timeout=ClientTimeout(total=3), allow_redirects=False,
            ) as response:
                if response.status not in {200, 201, 202}:
                    raise DeliveryError("TV rejected native receiver launch; nothing was sent")
                await response.content.read(16385)
            # POST acceptance is not proof of launch. Recheck a bounded number of times.
            for _ in range(3):
                await asyncio.sleep(0.3)
                state = await _get_tv_json(session, app_url)
                if state.get("running") is True:
                    return
            raise DeliveryError("Native receiver was not confirmed running after launch; nothing was sent")
    except DeliveryError:
        raise
    except (ClientError, TimeoutError, OSError) as error:
        raise DeliveryError("TV is unreachable/offline; nothing was sent") from error
    except (ValueError, UnicodeError) as error:
        raise DeliveryError("TV returned invalid app-state JSON; nothing was sent") from error


class Sender:
    """One in-flight notification; ephemeral UDP closes on every exit path."""

    def __init__(self, settings: Settings, images: ImageStore) -> None:
        self.settings = settings
        self.images = images
        self.lock = asyncio.Lock()
        self.closed = False
        self.active: set[asyncio.Task] = set()

    async def send(
        self, message: str,
        render: Callable[[str], Awaitable[bytes]],
        health: Callable[[], Awaitable[None]],
        *, ack_timeout: float = ACK_TIMEOUT,
    ) -> dict:
        """Render/send once, requiring complete HTTP image and matching UDP ACK."""
        if self.closed:
            raise DeliveryError("Native TV sender is unloaded")
        if self.lock.locked():
            raise DeliveryError("A TV notification is already being sent; no duplicate was queued")
        task = asyncio.current_task()
        if task is not None:
            self.active.add(task)
        try:
            async with self.lock:
                await health()
                try:
                    async with asyncio.timeout(8):
                        png = await render(message)
                except (ValueError, OSError) as error:
                    raise DeliveryError("Notification text/font could not be rendered; shorten the message or check bundled font") from error
                except TimeoutError as error:
                    raise DeliveryError("PNG rendering exceeded its deadline") from error
                if (
                    not isinstance(png, bytes) or not 24 <= len(png) <= 1024 * 1024
                    or png[:8] != b"\x89PNG\r\n\x1a\n"
                    or int.from_bytes(png[16:20], "big") != 1100
                    or int.from_bytes(png[20:24], "big") != 190
                ):
                    raise DeliveryError("Renderer returned an unexpected PNG")
                return await self._deliver(png, ack_timeout)
        finally:
            if task is not None:
                self.active.discard(task)

    async def _deliver(self, png: bytes, ack_timeout: float) -> dict:
        loop = asyncio.get_running_loop()
        request_id = f"ha-{secrets.token_hex(16)}"
        protocol = AckProtocol(request_id, self.settings)
        transport: asyncio.DatagramTransport | None = None
        lease: ImageLease | None = None
        token: str | None = None
        try:
            try:
                async with asyncio.timeout(3):
                    transport, _ = await loop.create_datagram_endpoint(
                        lambda: protocol,
                        family=socket.AF_INET,
                        local_addr=(self.settings.local_ip, 0),
                        remote_addr=(self.settings.tv_ip, self.settings.udp_port),
                    )
            except (OSError, TimeoutError) as error:
                raise DeliveryError("Could not bind HA local IP for TV UDP; verify configured LAN address") from error
            if transport.get_extra_info("sockname")[0] != self.settings.local_ip:
                raise DeliveryError("UDP source does not match the configured HA image address")
            token, lease = self.images.issue(png, self.settings.tv_ip)
            url = (
                f"http://{self.settings.local_ip}:{self.settings.http_port}"
                + IMAGE_PATH.format(token=token)
            )
            payload = {"id": request_id, "url": url, **OVERLAY}
            transport.sendto(json.dumps(payload, separators=(",", ":")).encode())
            try:
                async with asyncio.timeout(ack_timeout):
                    await asyncio.gather(protocol.ack, lease.served)
            except TimeoutError as error:
                raise DeliveryError("No complete image transfer plus matching TV ACK before deadline; display is unconfirmed") from error
            return {
                "request_id": request_id,
                "acknowledged": True,
                "image_served": True,
                "display_confirmed": False,
                "requested_duration_ms": OVERLAY["ms"],
            }
        finally:
            if token is not None:
                self.images.remove(token)
            if lease is not None and not lease.served.done():
                lease.served.cancel()
            if not protocol.ack.done():
                protocol.ack.cancel()
            if transport is not None:
                transport.close()

    async def close(self) -> None:
        """Cancel in-flight work on config-entry unload; no TV changes."""
        self.closed = True
        current = asyncio.current_task()
        active = [task for task in self.active if task is not current]
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)
