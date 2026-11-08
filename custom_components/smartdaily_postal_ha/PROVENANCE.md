# Smartdaily read-only HA integration: provenance and license

Prepared from `andyching168/Smartdaily_Postal_HA` at the immutable upstream commit
`e558bab416f40593f54187ba3c4e9e5827c43678` (upstream integration version 0.5.5).
Upstream source and MIT copyright are preserved by attribution and LICENSE.

- Source: https://github.com/andyching168/Smartdaily_Postal_HA/tree/e558bab416f40593f54187ba3c4e9e5827c43678
- This repository's version is a deliberately reduced, substantially rewritten fork.
- It is not affiliated with, endorsed by, or a documented public API from Smartdaily.
- This optional component retains the upstream MIT LICENSE and copyright.

## Retained upstream behavior

1. A resident's DeviceSn/DeviceCode is exchanged at the fixed provider host
   `https://api.smartdaily.com.tw/api/Valid/getHashCodeV2` using GET `code`.
2. The returned `Data.token` authorizes community/package reads using the header
   `KingnetAuth: CommunityUser <token>`.
3. Community selection reads `/api/Community/GetUserCommunityList`.
4. Package polling reads `/api/Postal/getUserPostalList` with `com_id`; the local
   interval is 900 s and every runtime provider GET first requires an explicit
   PowerState `on` from the configured TV's fixed local REST endpoint.
5. `pd_id` identifies a package; `p_status` 1 is unclaimed, 2 is collected.

## Local changes

- No credential/token/header/body printing, logging, hashes in entity IDs, or camera.
- All I/O is asynchronous shared-session HA HTTP, fixed HTTPS host, GET-only,
  bounded 15 s requests (5 s connection), redirects disabled, default TLS checks.
- DeviceCode is entered into a password-selector field directly in HA and is stored
  only as configuration data; tokens remain transient runtime values.
- Entity/device identities use the HA config entry ID, not DeviceCode.
- Daily delivery uses stable package IDs and the actual Asia/Taipei acknowledgment
  date, persisted in HA Store. Each TV-on poll emits one grouped event for unclaimed
  IDs not successfully acknowledged today. Unacknowledged IDs retry next poll;
  still-unclaimed IDs become due next day. Fresh install has no silent baseline.
- Local `acknowledge` only saves successful delivery dates for currently pending
  IDs, never mutates provider data or triggers a refresh. It must only be invoked
  after the TV send action reports a matching successful ACK.
- TV-off/unreachable/ambiguous states skip all runtime cloud calls and preserve
  the last real snapshot. Initial absence remains unavailable, never synthetic zero.
- TV host is restricted to literal RFC1918 IPv4, fixed port8001 and path/api/v2/;
  no wake/launch/control, redirects, arbitrary URLs, or credential headers.
- IDs are deduplicated, counts are not used to infer arrivals, and dates are not
  estimated from localized relative strings.
- HTTP/schema failures are unavailable states, never a synthetic empty mailbox.
- Basic reauthentication replaces the DeviceCode without changing entity IDs.
- The component creates one unclaimed-count sensor, daily reminder events, and a
  local-only ACK service. The example TV notification automation runs inside HA.

## Credential acquisition

The code expects the **decoded payload of the user's own resident pickup barcode**
from the Smartdaily app, called DeviceSn/DeviceCode upstream. It is not a Samsung
credential, account password, tracking number, or community administrator login.
If a screenshot is provided for decoding, decode locally only. Do not use the
external barcode-decoding website suggested by upstream. The selected household
must already be authorized by its community; the integration does not grant access.

## Review/compatibility boundary

The used APIs were checked against HA Core 2025.7.1 (Python 3.13): password text
selector, config entry runtime_data, async platform forwarding/unload, coordinator
auto-shutdown, and reauthentication are supported. No external Python dependencies
are required. The provider read flow and a controlled HA-triggered TV notification
were checked in an authorized installation. A real newly arriving parcel has not
yet been observed end to end. Offline tests do not guarantee future compatibility
with the undocumented provider API or all TV models.
