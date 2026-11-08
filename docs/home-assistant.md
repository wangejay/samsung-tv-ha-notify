# Home Assistant sender installation

## Prerequisites

- Native TV receiver `SmittyOv01.overlay` 1.0.1 installed and running; see [TV build/install](../tv/README.md).
- Tested HA Core **2025.7.1**, Python **3.13**. Newer or older versions are not automatically considered verified.
- One TV per sender integration. Both HA and TV use literal private IPv4 addresses and direct LAN communication.
- HA must already expose a **plain HTTP LAN endpoint**, normally port 8123. External HTTPS via a reverse proxy can remain unchanged. A TLS-only HA listener is not supported by this sender; do not simply point it at a HTTPS hostname or disable your existing TLS configuration.

## Install

1. Copy the complete `custom_components/samsung_nui_notify/` directory into your HA config directory's `custom_components/`. Include the font, OFL and provenance files. HA OS typically calls this directory `/config`; some File Editor environments expose it as `/homeassistant`.
2. Check configuration and restart **HA Core** so the new Python integration can load.
3. Open Settings → Devices & services → Add integration → **Samsung Native TV Overlay**.
4. Set these fields (addresses below are examples only):

   | Field | Example | Meaning |
   | --- | --- | --- |
   | TV IPv4 | `192.168.10.20` | The receiver's TV |
   | HA LAN IPv4 | `192.168.10.10` | HA's real UDP source and directly reachable image host |
   | HTTP port | `8123` | Existing HA plain HTTP listener |
   | UDP port | `18110` | Receiver's fixed port; normally leave unchanged |
   | Ensure receiver | off initially | Optional fixed-app launch, only when TV reports on |

   The address fields must be changed to your own LAN addresses. Setup saves configuration without contacting or waking the TV. There is currently no options flow: remove/re-add the entry to change addresses.
5. With the TV already on, test the service while watching the upper right corner:

   ```yaml
   action: samsung_nui_notify.send
   data:
     message: "你有包裹通知"
   response_variable: tv_delivery
   ```

   In an automation/script, the optional response variable contains `acknowledged`, `image_served`, `request_id`, `requested_duration_ms` and `display_confirmed`.

## Launch and error behavior

`ensure_receiver` is **off by default**. Enable it only after checking this receiver can start without affecting playback on your model. If enabled, the sender GETs the TV power state, GETs only the fixed receiver's app status, and POSTs only `SmittyOv01.overlay` if missing from the running state. It never powers on the TV, closes another app, installs anything, or sends an arbitrary app ID.

The service accepts one `message` field: a nonempty single Unicode line, maximum 200 characters. Oversized text is shrunk within a minimum font size, then explicitly refused if it still cannot fit; no silent truncation. Geometry is fixed in `const.py`: 480×83 at x1400/y40, 7000 ms. The subtitle is currently `Claire 傳來的訊息`; modify the renderer if you want another label.

TV off/unreachable, receiver unavailable, wrong network address, download/ACK timeout, or an in-flight notification raises an HA error. There is no hidden queue and no automatic retransmit. Separate automations own retry/deduplication policy.

## Troubleshooting

- **HA action succeeds but no visible banner:** ACK means download and queue acceptance, not proof the display compositor rendered it. Confirm physically; inspect receiver running status, model/API compatibility and manifest privileges. Never infer visibility from an HTTP 200 alone.
- **Timeout:** verify HA's configured LAN IP is its actual UDP source, the TV can directly GET that IP's HTTP port, and UDP 18110 is allowed. Guest isolation, VLAN filtering, HA containers/NAT or proxies can break source-IP matching.
- **TV is on but app is not running:** launch the fixed receiver via the supported developer path, or opt into the verified-on-your-TV REST launch option. Full standby/power-cycle persistence is not established.
- **Font missing:** copy all of `fonts/`, not only Python files. Noto Sans TC ships under OFL; no Apple font or OS-specific font is needed.
- **Integration absent:** restart Core after copying files, and confirm the directory name and manifest. Do not replace unrelated integrations.

To uninstall, remove the integration in HA and delete only its component directory after stopping/restarting as appropriate. The native TV receiver is separate; removing the HA entry does not stop or uninstall it.
