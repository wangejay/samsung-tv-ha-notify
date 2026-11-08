# 智生活包裹通知 / Smartdaily parcel reminders

Optional Home Assistant integration for 智生活 resident parcel records. Everything
runs in HA: no Mac daemon, phone notification bridge, or additional hardware.

`Smartdaily read-only HTTPS → HA daily reminder → Samsung TV notification → local ACK`

The provider endpoints are **undocumented and unofficial**. This is not endorsed
by 智生活; provider changes may require an update.

## Status and license

- Tested with HA Core 2025.7.1 / Python 3.13 and a Samsung Tizen 9 TV.
- A controlled HA-triggered notification was visually confirmed and disappeared
  after approximately seven seconds. A **real new-parcel arrival has not yet been
  observed end to end**.
- Sender fields `acknowledged` and `image_served` mean a matching receiver ACK and
  an image fetch, not proof of pixels visible on screen. `display_confirmed` stays
  false; visual confirmation was a separate test.
- This optional component retains its own [MIT LICENSE](../custom_components/smartdaily_postal_ha/LICENSE)
  and [upstream attribution](../custom_components/smartdaily_postal_ha/PROVENANCE.md).

## Install and configure

1. Configure this repository's `samsung_nui_notify` sender and native TV receiver
   first. Confirm `samsung_nui_notify.send` works from HA.
2. Copy `custom_components/smartdaily_postal_ha/` into HA's
   `/config/custom_components/`, preserving its LICENSE. Restart HA after adding
   the new custom integration.
3. Open **Settings → Devices & services → Add integration → 智生活包裹追蹤**.
4. Enter the decoded **DeviceSn / DeviceCode from your own resident pickup
   barcode** and the TV's private IPv4 address, then select an authorized community.
   Example addresses: HA `192.168.10.10`, TV `192.168.10.20`; replace them with your
   own. The TV field accepts literal RFC1918 IPv4, not a hostname, URL, or port.
5. Append [examples/smartdaily-parcels.yaml](../examples/smartdaily-parcels.yaml)
   to your HA automations and reload automations.

The pickup barcode is available in the 智生活 app. Its decoded payload is not a
Samsung credential, account password, or tracking number. Enter it only in HA's
password field, not a public YAML file, issue, screenshot, or chat. If an image
needs decoding, do so locally, not on a third-party barcode website. The resident
device must already have community/household access.

DeviceCode is stored in the HA config entry; API tokens stay in memory. Entity and
device identities use the HA config entry ID, never DeviceCode. No credential,
token, response body, recipient name, photo, or tracking number is logged or
included in notification events.

## Request and reminder rules

- The scheduled interval is **900 seconds / 15 minutes**. Setup also performs an
  initial guarded refresh to populate the sensor.
- Before **each runtime cloud GET**, HA reads
  `http://<tv_ipv4>:8001/api/v2/`. Only `device.PowerState == "on"` permits the cloud
  request. This GET issues no wake, launch, pairing, or remote-control command.
- TV off, unreachable, ambiguous state, redirect, or malformed response means
  **no runtime Smartdaily requests**. HA retains the last genuine snapshot, which
  can be stale while skipped. Before any snapshot the sensor is unavailable, not zero.
- Explicit setup and reauthentication can read the provider token/community
  endpoints even while the TV is off.
- Only `p_status == 1` is uncollected. Status 2 is collected and never notified;
  other statuses are not assumed to be uncollected.
- A stable `pd_id` is due if uncollected and not successfully acknowledged **today
  in Asia/Taipei**. The timezone is intentional, not the host's UTC date.
- Each poll groups due IDs into one event and one TV popup. If A was acknowledged
  today and B arrives, only B is due. If A remains uncollected tomorrow, A is due
  again. Collected parcels stop appearing in reminders.
- First installation has no silent lifetime baseline: existing uncollected IDs
  are eligible. Setup refresh defers delivery until the entry is loaded and a
  normal scheduled poll runs, so the delivery can be acknowledged.
- Failed sends or missing ACKs do not mark IDs delivered; they retry on the next
  successful TV-on poll. Successful dates persist in HA Store across restarts.
  Store and TV delivery are not atomic: disk failure or a process crash can still
  cause a duplicate. This is not an exactly-once guarantee.

## Automation and acknowledgments

`smartdaily_postal_new_package` covers both new arrivals and next-day reminders.
Its event data contains `entry_id`, `community_id`, `package_ids` (due list),
`due_count`, and `unclaimed_count` (total currently uncollected).

The example intentionally handles **all configured Smartdaily entries**, sending
the event's own `entry_id` back to the local acknowledgment service. It has no
hard-coded household or entry ID. To restrict it to one entry, add an `event_data`
filter for that entry's ID to the trigger. Obtain the ID by listening for a real
event in **Developer tools → Events**; it is not the sensor entity ID.

The example calls `samsung_nui_notify.send` with only `message`, saving the response
in `delivery`. Only when **both** `delivery.acknowledged` and `delivery.image_served`
are true, and the event is not a test, does it call
`smartdaily_postal_ha.acknowledge` with that event's `entry_id` and `package_ids`.
The local ACK records the actual current Taipei date only for pending IDs. It
cannot collect, sign for, delete, or otherwise change a parcel and makes no cloud
read. Do not mark delivery merely because an automation ran or the count changed.

## End-to-end test without changing reminder receipts

With the receiver and automation installed, fire `smartdaily_postal_new_package`
in **Developer tools → Events** with:

```json
{"test": true, "package_ids": []}
```

The example waits **five seconds**, then sends `你有包裹通知（測試）`. A test never
calls the parcel ACK service, so it cannot suppress a genuine reminder. It tests
HA → sender → TV, not provider arrival. Watch the TV to confirm the overlay visually.

## Offline tests and source

From the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/smartdaily -v
```

The 27 tests use fake HTTP sessions and small HA API doubles, not devices or
credentials. They cover power gating, grouped retries, same-day restart deduplication,
Taipei midnight, new IDs, collected status, and unload races. They are not a full
HA integration test suite.

The read flow comes from
[andyching168/Smartdaily_Postal_HA](https://github.com/andyching168/Smartdaily_Postal_HA/tree/e558bab416f40593f54187ba3c4e9e5827c43678):
GET `getHashCodeV2`, `GetUserCommunityList`, and `getUserPostalList` at the fixed
HTTPS host `api.smartdaily.com.tw`. Requests have bounded timeouts, no redirects,
no parcel mutation endpoints, and no arbitrary image URL fetching.
