# Local protocol and lifecycle

The native receiver retains the upstream app ID **`SmittyOv01.overlay`** and UDP port **18110** for compatibility. It is a background-network native .NET/NUI app, not an Android APK or a W3C browser notification page.

## One message

1. HA checks `GET http://TV:8001/api/v2/` for explicit `device.PowerState == "on"` and verifies the fixed receiver is running. Optional recovery may start only that receiver.
2. HA renders the literal message in an executor with Pillow and bundled Noto Sans TC into a 1100×190 PNG.
3. HA registers a short-lived single-use in-memory image lease, restricted to the TV's direct TCP peer.
4. From an ephemeral UDP socket bound to its configured LAN IP, HA sends JSON to TV:18110:

   ```json
   {"id":"ha-random-id","url":"http://192.168.10.10:8123/api/samsung_nui_notify/image/random-token","x":1400,"y":40,"w":480,"h":83,"ms":7000}
   ```

5. The receiver requires the URL prefix `http://<UDP-source-IP>:`. It downloads the PNG and queues it, then sends **`ack <id>`** to the UDP sender's IP/ephemeral port.
6. HA completes only after **both** the image response finishes and the exact ACK arrives from the configured TV IP/port. The deadline is nine seconds. Images/sockets are cleaned on success, failure, cancellation and unload.
7. The TV main loop shows a transparent non-focusable Notification window. Retained NUI wrappers and a monotonic deadline pump hide/dispose it after at most roughly seven seconds plus main-loop scheduling granularity. The upper bound includes fade-out.

A successful service response is similar to:

```json
{"acknowledged":true,"image_served":true,"display_confirmed":false,"requested_duration_ms":7000,"request_id":"ha-random-id"}
```

**Queue/download ACK is not a compositor display receipt.** A specific test can be physically accepted, but future responses intentionally remain `display_confirmed:false` because they lack per-message visual verification. Daily package deduplication uses the transfer ACK, not a claim of mathematically exact once-only visual delivery.

## Limits

- One configured TV and one in-flight send; no hidden resend or durable notification queue.
- Fixed geometry assumes the verified TV's coordinate behavior; other models/resolutions need checking.
- The timer fallback cannot run while the entire native main loop is suspended.
- Native-app overlap, standby survival, power-cycle behavior, firmware privilege handling and protected video combinations are model-specific.
- Local REST launch is an observed TV behavior, not a claim that Samsung provides a universal public text-overlay API.

Do not add WAN forwarding to work around LAN routing issues. See [security](../SECURITY.md).
