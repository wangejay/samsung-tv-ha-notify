#!/usr/bin/env python3
"""Bounded localhost-only tests; deliberately never import or contact live HA."""

import asyncio
import contextlib
import importlib
import json
from pathlib import Path
import socket
import sys
import types

from aiohttp import ClientSession, web

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "samsung_nui_notify"
# Import only standalone renderer/protocol, without executing HA's __init__.py.
package = types.ModuleType("samsung_nui_notify")
package.__path__ = [str(COMPONENT)]
sys.modules[package.__name__] = package
render = importlib.import_module("samsung_nui_notify.render")
protocol = importlib.import_module("samsung_nui_notify.transport")


async def expect_delivery_error(awaitable, contains):
    try:
        await awaitable
    except protocol.DeliveryError as error:
        assert contains in str(error), str(error)
    else:
        raise AssertionError("expected DeliveryError")


async def main():
    png = await asyncio.to_thread(render.render_png, "您的包裹已送達")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(png[16:20], "big") == 1100
    assert int.from_bytes(png[20:24], "big") == 190
    for invalid in ("", "line\nbreak", "\ud800", "長" * 201):
        try:
            render.validate_message(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid text accepted")
    try:
        await asyncio.to_thread(render.render_png, "寬" * 200)
    except ValueError:
        pass
    else:
        raise AssertionError("overwide message was silently rendered")

    images = protocol.ImageStore()
    state = {"on": True, "running": True, "posts": 0, "app_gets": 0}
    app = web.Application()

    async def image(request):
        return await images.get(request, request.match_info["token"])

    async def device_info(request):
        return web.json_response({"device": {"PowerState": "on" if state["on"] else "standby"}})

    async def app_info(request):
        state["app_gets"] += 1
        return web.json_response({"id": "SmittyOv01.overlay", "running": state["running"], "version": "1.0.1"})

    async def app_run(request):
        state["posts"] += 1
        state["running"] = True
        return web.json_response({"accepted": True})

    app.router.add_get("/api/samsung_nui_notify/image/{token}", image)
    app.router.add_get("/api/v2/", device_info)
    app.router.add_get("/api/v2/applications/SmittyOv01.overlay", app_info)
    app.router.add_post("/api/v2/applications/SmittyOv01.overlay", app_run)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    http_port = site._server.sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{http_port}"
    loop = asyncio.get_running_loop()
    receipt = {"localhost_only": True, "tv_contacted": False, "ha_imported_or_contacted": False, "checks": []}
    try:
        async with ClientSession() as session:
            # Direct TCP peer protection, TTL, and single-use semantics.
            token, lease = images.issue(png, "127.0.0.2", ttl=1)
            async with session.get(base + f"/api/samsung_nui_notify/image/{token}") as response:
                assert response.status == 404
            assert token in images.images, "wrong peer consumed token"
            images.remove(token); lease.served.cancel()
            token, lease = images.issue(png, "127.0.0.1", ttl=0.02)
            await asyncio.sleep(0.03)
            async with session.get(base + f"/api/samsung_nui_notify/image/{token}") as response:
                assert response.status == 404
            lease.served.cancel()
            receipt["checks"].append("direct peer restriction and expired-token 404")

            async def health():
                await protocol.check_receiver_running(session, "127.0.0.1", port=http_port)

            async def render_executor(message):
                return await asyncio.to_thread(render.render_png, message)

            async def scenario(mode):
                received = loop.create_future()
                handler_tasks = []
                sender_task = None
                local_udp = None

                class Receiver(asyncio.DatagramProtocol):
                    def connection_made(self, transport):
                        self.transport = transport

                    def datagram_received(self, packet, peer):
                        nonlocal local_udp
                        local_udp = peer
                        handler_tasks.append(asyncio.create_task(self.handle(packet, peer)))

                    async def handle(self, packet, peer):
                        try:
                            request = json.loads(packet)
                            assert request["url"].startswith(f"http://127.0.0.1:{http_port}/")
                            assert {key: request[key] for key in ("x", "y", "w", "h", "ms")} == protocol.OVERLAY
                            if not received.done():
                                received.set_result(request)
                            if mode == "idle":
                                return
                            if mode != "no-image":
                                async with session.get(request["url"]) as response:
                                    assert response.status == 200
                                    body = await response.read()
                                    assert body[:8] == png[:8]
                                async with session.get(request["url"]) as response:
                                    assert response.status == 404, "token was reusable"
                            if mode == "valid":
                                self.transport.sendto(b"ack wrong-id", peer)
                                await asyncio.sleep(0.03)
                                assert not sender_task.done(), "wrong ID was accepted"
                                self.transport.sendto(f"ack {request['id']}".encode(), peer)
                            elif mode == "no-image":
                                self.transport.sendto(f"ack {request['id']}".encode(), peer)
                            # timeout mode deliberately sends no valid ACK.
                        except Exception as error:
                            if not received.done():
                                received.set_exception(error)
                            raise

                udp, _ = await loop.create_datagram_endpoint(Receiver, local_addr=("127.0.0.1", 0))
                sender = protocol.Sender(protocol.Settings("127.0.0.1", "127.0.0.1", http_port, udp.get_extra_info("sockname")[1]), images)
                try:
                    sender_task = asyncio.create_task(sender.send("您的包裹已送達", render_executor, health, ack_timeout=0.2))
                    request = await asyncio.wait_for(received, 2)
                    if mode == "valid":
                        result = await sender_task
                        assert result["acknowledged"] and result["image_served"]
                        assert result["display_confirmed"] is False
                    elif mode == "idle":
                        await expect_delivery_error(sender.send("另一則通知", render_executor, health), "already being sent")
                        await sender.close()
                        with contextlib.suppress(asyncio.CancelledError):
                            await sender_task
                        assert sender_task.cancelled()
                    else:
                        await expect_delivery_error(sender_task, "before deadline")
                    assert not images.images, "image lease leaked"
                    async with session.get(request["url"]) as response:
                        assert response.status == 404
                    await asyncio.sleep(0)
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as check:
                        check.bind(local_udp)  # The sender's ephemeral socket was closed.
                    for task in handler_tasks:
                        await task
                finally:
                    await sender.close()
                    udp.close()

            await scenario("valid")
            receipt["checks"].append("executor render + HTTP single-use PNG + exact ACK; wrong ID ignored")
            await scenario("timeout")
            await scenario("no-image")
            receipt["checks"].append("missing ACK or image fails; assets/UDP cleaned")
            await scenario("idle")
            receipt["checks"].append("busy rejection and unload cancels in-flight work")

            state.update(on=False, running=False, posts=0, app_gets=0)
            await expect_delivery_error(protocol.check_receiver_running(session, "127.0.0.1", ensure_receiver=True, port=http_port), "off/standby")
            assert state["posts"] == 0 and state["app_gets"] == 0
            state.update(on=True, running=False)
            await expect_delivery_error(health(), "not running")
            assert state["posts"] == 0
            await protocol.check_receiver_running(session, "127.0.0.1", ensure_receiver=True, port=http_port)
            assert state["posts"] == 1 and state["running"]
            receipt["checks"].append("TV-off guard; default no launch; opt-in fixed-app POST rechecked (stub only)")
    finally:
        await runner.cleanup()

    receipt["checks"].extend(["Unicode input validation and too-wide refusal", "1100x190 Noto Sans TC PNG"])
    receipt["versions"] = {"python": sys.version.split()[0], "aiohttp": importlib.import_module("aiohttp").__version__, "Pillow": importlib.import_module("PIL").__version__}
    receipt["limitations"] = ["Not imported inside actual HA 2025.7.1", "No TV or live network test", "REST launch not physically verified", "Noto differs from Apple STHeiti"]

    print(json.dumps(receipt))


if __name__ == "__main__":
    asyncio.run(main())
