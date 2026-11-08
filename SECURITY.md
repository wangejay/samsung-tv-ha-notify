# Security and privacy model

This is an experimental **trusted-LAN** integration, not an Internet-facing notification service.

- The TV listens on UDP 18110 without cryptographic authentication. It accepts image URLs whose HTTP prefix matches the UDP sender's address. That binding is not a substitute for sender authentication: another permitted LAN peer may send its own notification. The receiver's simple string-prefix check is not strict URL validation, and its HTTP client may follow redirects; do not treat it as an SSRF or destination-isolation boundary. Do not expose TV ports or this UDP listener to the Internet; constrain access with your network/firewall where needed.
- HA serves the current image through its existing HTTP server. Each image has a random 256-bit token, a maximum 12-second in-memory lifetime, one successful GET, and a **direct TCP peer-IP check** for the configured TV. Forwarded headers are not trusted. The empty route returns 404. No HA bearer token is sent to the TV.
- The native receiver checks the source address prefix but is derived from an experimental upstream receiver. It does not provide comprehensive hostile-peer resource limits or a signed-message protocol. Do not treat it as hardened for an untrusted network.
- Notification text is sent as a PNG over plain LAN HTTP; do not assume end-to-end encryption. Request paths may appear in explicitly enabled HTTP/proxy debug logs.
- The optional Smartdaily component uses fixed HTTPS endpoints with TLS verification, GET-only calls, bounded timeouts and redirects disabled. No provider-side package status is changed. DeviceCode is saved in HA's config entry; provider tokens are transient. Treat HA storage and backups as sensitive.
- No Samsung credentials, signing keys, DUID, resident DeviceCode, user tokens, household config entries, or device-specific signed packages belong in this repository or bug reports.

For a suspected vulnerability, use the repository's private security-reporting option if enabled; otherwise contact the maintainer privately without publishing credentials, tokens, private keys, or personal package records. Public compatibility reports should include only sanitized model, OS, component version, and errors.
