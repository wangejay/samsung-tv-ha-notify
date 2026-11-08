# Verification record and boundaries

## Physically accepted — 2026-11-08

On one Samsung **QA75Q60DAXXZW (Q60D, 75-inch), Tizen 9.0**, using receiver **1.0.1**, HA Core **2025.7.1 / Python 3.13**:

- A compact 480×83 corner notification appeared while the current native video continued; the user reported no remote-control interruption.
- The receiver's original persistence defect was fixed by retaining NUI lifecycle objects and adding a monotonic deadline cleanup pump. A garbage-collection root cause was plausible, not directly proven.
- A test then ran through **HA event → automation → HA PNG rendering / HTTP / UDP → TV receiver**. HA recorded completed execution, image served and matching ACK, without action errors.
- The user independently confirmed that HA-sent test was visible and disappeared after **about seven seconds**.
- Controlled close/restart of **only this receiver app** via local REST worked. No whole-TV reboot or power-cycle test was done.
- Smartdaily read-only authentication, authorized community selection and package schema worked. There were **zero unclaimed items** during setup; no real new courier arrival was observed.

No credentials, DUIDs, household addresses, entry IDs, traces or private deployment data are published as evidence. The image in the root README is rendered artwork, not a TV photograph.

## Offline checks

The public tree includes tests covering sender input/rendering, single-use/expiry and direct-peer image restrictions, image+matching-ACK requirements, timeouts, cancellation/cleanup, single-flight behavior, power checks and optional app launch using localhost stubs. A regression check serializes the actual config-form schema with HA 2025.7.1's voluptuous dependency versions.

The Smartdaily tests use HA doubles and exercise stable package IDs, same-day persistence, next Asia/Taipei date, new package arrival without repeating already-acknowledged IDs, failed-delivery retries, collected items, malformed responses, TV-off no-cloud behavior and unload races. These are not claims that all HA runtime APIs were imported in CI.

The public native receiver source was compiled and staged twice in fresh temporary directories with the pinned SDK/workload: zero warnings/errors, six expected payload members, valid ZIP CRC, no signatures or certificate members. Both unsigned archives were byte-identical (89,373 bytes; SHA256 `e75f15ad8fd7e6960fb76cee073c3c795b39a34d1af280e657ea04aba0a25263`). Generated packages, SDK/cache files and build logs are not published. The receiver can be freshly compiled and staged as unsigned TPK with the pinned SDK/workload. Building unsigned verifies source/toolchain compatibility, not signing acceptance or screen rendering on another TV.

## Not established

- Universal Samsung/Tizen compatibility, all DRM apps, inputs or firmware releases.
- Receiver lifetime over prolonged standby or a complete TV power cycle.
- Live new-package arrival or actual next-day reminder observed over a date transition; those decision rules were exercised offline.
- Transactional exactly-once display across TV crashes, ACK loss, HA restarts or storage failures.
- A user-independent installable signed TPK. Each user needs their own device-authorized Samsung signing profile.

## GitHub automation setup

The publishing OAuth credential did not grant GitHub's `workflow` permission, so GitHub Actions is **not enabled** in this initial publication. All checks reported above were run locally. [`ci-template.yml`](ci-template.yml) contains the reviewed, pinned-action workflow template; a repository owner with the appropriate GitHub authorization can later place it at `.github/workflows/checks.yml`. No additional authorization is needed to read, clone or run this project locally.
