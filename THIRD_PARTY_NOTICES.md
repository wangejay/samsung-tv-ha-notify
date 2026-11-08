# Licenses and source attribution

This repository is a collection of separately licensed components. The root `LICENSE` is GPL version 3 for files without a more specific license. Preserve all per-directory notices when copying components.

## Native receiver — GPL-3.0

- Upstream: [als7294/overscreen](https://github.com/als7294/overscreen)
- Pinned revision: `c0fd412bec1a5a82f1d6a4cf867d3eb0281e55da`
- Scope: only the native `tvoverlay/` receiver, not the upstream desktop launcher, news, phone, iMessage, FaceTime, Discord or assistant hooks.
- Public source here: `tv/`; full license in `tv/LICENSE` / `licenses/GPL-3.0.txt`.
- Local changes: version 1.0.1 retains window/view/image/timer/animation objects, uses a monotonic deadline cleanup pump, and resets/deletes active resources reliably. Build/install documentation and an isolated unsigned-build script were added. App ID and wire protocol remain compatible.
- Exact authorship information is retained in the source and upstream project attribution; no Samsung runtime/SDK redistribution is included.

## Smartdaily read-only integration — MIT

- Upstream: [andyching168/Smartdaily_Postal_HA](https://github.com/andyching168/Smartdaily_Postal_HA)
- Pinned revision: `e558bab416f40593f54187ba3c4e9e5827c43678`, version 0.5.5.
- Copyright (c) 2025 andyching168; preserved MIT license in `custom_components/smartdaily_postal_ha/LICENSE`.
- This is a substantially rewritten, reduced sensor/event fork. See its `PROVENANCE.md` for changes. It is not an official or documented public Smartdaily API.

## New HA sender — MIT

- `custom_components/samsung_nui_notify/` (except bundled font files): Copyright (c) 2026 wangejay, MIT; included component `LICENSE`.
- This sender implements the receiver's LAN protocol independently using HA's existing HTTP server, Pillow and aiohttp.

## Noto Sans TC — SIL Open Font License 1.1

- Font: unmodified `NotoSansTC[wght].ttf`, redistributed as `NotoSansTC.ttf`.
- Source: [google/fonts](https://github.com/google/fonts), commit `3be1884c48c3e45b52ecc725676a08f87776373e`.
- Scope: `custom_components/samsung_nui_notify/fonts/`.
- Full original copyright / OFL text in `fonts/OFL.txt`; exact source URLs, blob IDs and SHA256 in `fonts/PROVENANCE.json`.
- No Apple system font is distributed or required.

Microsoft .NET and Samsung Tizen SDK/runtime files are not bundled. Install them separately from their official sources and follow their licenses. This repository contains no personal signing keys, author/distributor identity, signed device-specific package or private deployment snapshot.
