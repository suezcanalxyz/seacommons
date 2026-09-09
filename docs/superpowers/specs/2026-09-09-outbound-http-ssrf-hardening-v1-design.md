# Outbound HTTP / SSRF Hardening v1 — Design

**Date:** 2026-09-09
**Status:** design approved in chat; implementation pending written-spec review
**Scope:** backend outbound HTTP/HTTPS trust boundary. No collector semantics, publication authority, lifecycle, database schema, AIS/radio protocol, or frontend behaviour changes.

## Goal

Create one enforceable outbound HTTP policy for SeaCommons and close the highest-risk SSRF paths without attempting a single giant migration of every historical collector.

Packet J v1 must make the provenance of a destination explicit at the call site, prevent request/feed-derived URLs from reaching private infrastructure, bound response reads, validate redirects hop-by-hop, and preserve legitimate operator-configured internal endpoints.

The packet also adds an adoption guard so new backend code cannot introduce another direct `urllib`, `httpx`, or `requests` bypass while legacy fixed collectors are migrated in later batches.

## Threat model

The protected boundary is server-side code that opens an outbound HTTP/HTTPS connection. The attacker-controlled input may originate from an API request, external feed/media object, stored source URL, redirect target, DNS answer, or other externally-derived data.

The design must prevent those inputs from reaching loopback, RFC1918/private, link-local, multicast, unspecified, reserved, IPv4-mapped private IPv6, and cloud/instance metadata destinations. It must also prevent a public URL from redirecting into those ranges or changing destination after validation through DNS rebinding.

Legitimate operator-configured services are not treated as attacker-controlled. `API_INTERNAL_URL`, `DRIFT_WORKER_URL`, OIDC issuer/JWKS origins, and configured witness endpoints may intentionally use private or loopback networks. Their privilege comes only from trusted configuration and can never be selected by request/feed input.

## Canonical module

Add `core/net/outbound.py` as the canonical policy and transport boundary for HTTP/HTTPS requests in backend core code.

It exposes shared destination validation plus synchronous and asynchronous clients so async call sites do not block the event loop and sync collectors do not need ad-hoc event-loop bridging.

The public API is policy-oriented rather than a generic pass-through. Callers select a code-defined trust profile and response contract; input data can supply path/query/body values but cannot select or weaken the trust profile.

Direct creation of `httpx.Client`, `httpx.AsyncClient`, `urllib.request.urlopen`, and `requests.*` remains temporarily allowed only in a checked-in legacy exception inventory. New exceptions require explicit review.

## Trust profiles

### `PUBLIC_UNTRUSTED`

Use for any URL whose scheme/host/port can originate from an API request, external content, feed/media object, or stored externally-derived URL.

- HTTPS only.
- Port 443 only in v1.
- URL userinfo is forbidden.
- Destination host is normalized and DNS-resolved before connection.
- Every resolved address must be public-routable under the deny rules; one forbidden answer blocks the target.
- Environment proxies are disabled (`trust_env=False`).
- Only GET/HEAD are permitted.

### `PUBLIC_FIXED`

Use when code owns the public origin and only bounded path/query/body values vary, for example IOM, GDACS, NOAA, Copernicus, OpenSanctions, or an explicitly known media CDN.

- HTTPS by default.
- The call site declares the allowed host/origin set in code.
- Resolved IPs must still be public-routable.
- Redirects are allowed only when each hop remains inside the declared host/origin allowlist.
- GET/HEAD/POST are allowed as required by the collector.
- Environment proxies remain disabled.

### `OPERATOR_INTERNAL`

Use only for exact origins supplied by trusted deployment configuration, including private/loopback endpoints when intentionally configured.

- HTTP or HTTPS is permitted.
- Private, loopback, and non-standard ports are permitted only because the exact origin comes from operator configuration.
- Request/feed/external content must never determine the scheme, hostname, or port under this profile.
- Redirects are disabled by default. An internal call site may opt into redirects only to an explicit configured origin set.
- Each internal caller binds an exact configured origin once and subsequent request methods accept only relative path/query data against that origin. Path components may be appended by code, but attacker-controlled values must be encoded as path/query data rather than reparsed as an origin.

## Destination normalization and deny rules

Hostname comparison is case-insensitive, strips a terminal dot, and uses IDNA normalization. IP literals are canonicalized before policy evaluation, including IPv4-mapped IPv6 forms.

For public profiles, reject addresses classified as loopback, private, link-local, multicast, unspecified, or reserved. Explicitly cover well-known metadata targets such as `169.254.169.254`, IPv6 link-local/private equivalents, and metadata hostnames whose final A/AAAA answers are forbidden.

DNS resolution must fail closed: resolution failure, an empty answer set, or any forbidden address blocks the request for public profiles.

## DNS rebinding resistance and connection pinning

Validation and connection must use the same resolved destination. The transport therefore connects to one of the already-validated IP addresses rather than handing the original hostname back to a second resolver.

For HTTPS, the original normalized hostname is preserved in the HTTP `Host` header and TLS SNI/certificate validation. The installed `httpcore` exposes the `sni_hostname` request extension; Packet J isolates this detail in the outbound transport and covers it with a contract test so a dependency upgrade cannot silently remove the guarantee.

Connection selection across multiple validated addresses may be deterministic or fail over between validated addresses, but it may never resolve a fresh unvalidated address during the same hop.

## Redirect policy

Automatic library redirects are disabled. The canonical client handles redirects explicitly.

- Maximum three redirect hops.
- Relative redirects inherit the validated origin and are normalized before the next request.
- Absolute redirects are treated as a new destination and rerun the complete trust-profile validation, DNS resolution, IP validation, and pinning flow.
- `PUBLIC_UNTRUSTED` permits only HTTPS redirects that still satisfy its public-target rules.
- `PUBLIC_FIXED` additionally requires the redirected host/origin to remain in the call-site allowlist.
- `OPERATOR_INTERNAL` does not redirect unless the call site explicitly declares allowed configured origins.
- POST/other non-GET/HEAD requests do not auto-follow redirects in v1; a 3xx is returned as an upstream/policy failure rather than silently rewriting the method or body.
- Redirect loops or excess hops fail with a typed `redirect_blocked`/`redirect_limit` outcome.

## Response bounds

Every canonical request is streamed and bounded. There is no unlimited `response.content` or bare `response.read()` path in the new client.

Call sites choose a bounded response contract. Packet J v1 defines `IMAGE` at 8 MiB (preserving the existing X-media cap and requiring `image/*`), `JSON_TEXT` at 16 MiB, and `BINARY` at 32 MiB. 32 MiB is the absolute v1 ceiling; a later collector that genuinely requires more must change the reviewed policy rather than pass an arbitrary larger integer.

If `Content-Length` exceeds the selected cap, reject before reading. If length is absent or inaccurate, stop streaming after `max_bytes + 1` and return `response_too_large` without exposing the partial body to the caller.

Timeouts are split into connect/read/write/pool values rather than one unbounded default. No component may disable a timeout. Call sites may preserve an existing bounded timeout, including the 90 s remote-drift budget, but every individual timeout component is capped at 120 s in v1.

## Errors and logging

The client returns or raises typed failures with bounded reason codes such as:

- `blocked_target`
- `invalid_scheme`
- `invalid_port`
- `dns_failed`
- `redirect_blocked`
- `redirect_limit`
- `timeout`
- `tls_failed`
- `invalid_content_type`
- `response_too_large`
- `upstream_error`

Default exception/log text must not contain the raw URL, query string, credentials, authorization headers, or response body. Callers may log a normalized hostname when operationally useful, but never a query-bearing URL.

Existing best-effort semantics are preserved: media/image fetchers return their current empty/None result on blocked/network failure; auto-drift returns false; remote drift compute falls back in-process; witness broadcasting logs and continues; OIDC/JWKS authentication fails closed.

## Observability

Add bounded metrics for outbound requests using only low-cardinality labels such as `policy`, `method`, and `outcome`. Do not label metrics with hostname, URL, IP, provider token, receiver id, source id, or exception text.

## Packet J v1 migration scope

The first packet closes dynamic/configurable trust boundaries. It does not require every hardcoded collector to migrate before acceptance.

Required v1 migrations:

1. `core.intel.vision.extract_from_url` and `/api/v1/intel/extract-image` use `PUBLIC_UNTRUSTED`, image content-type enforcement, response-size cap, redirect validation, and pinned DNS/IP connection.
2. `core.intel.x_media_utils._download_bounded_image` and syndication/media fetches use `PUBLIC_FIXED` with the existing X/Twitter media/CDN allowlists expressed through the canonical policy.
3. `core.intel.auto_drift_client` uses `OPERATOR_INTERNAL` for the configured `API_INTERNAL_URL` origin while preserving its Host-header override and best-effort return contract.
4. `core.drift.engine` remote compute uses `OPERATOR_INTERNAL` for `DRIFT_WORKER_URL`, preserves the worker secret header, and retains in-process fallback on network/policy failure.
5. OIDC JWKS acquisition uses `OPERATOR_INTERNAL` for the configured issuer/JWKS origin. `authenticate_token` must select signing keys from JWKS fetched through the canonical client rather than allowing `PyJWKClient` to perform an independent ungoverned fetch. Preserve the current five-minute JWKS cache and perform one bounded refresh on an unknown `kid` so normal key rotation still works; network/policy failure remains authentication fail-closed.
6. Forensic witness POSTs use `OPERATOR_INTERNAL` against the exact configured witness origins and preserve best-effort fan-out without automatic redirects.

Any origin used by `OPERATOR_INTERNAL` must be parsed from trusted runtime configuration before request data is handled. A call site may not pass a raw external URL to this profile merely because it needs private-network access.

## Legacy collector migration boundary

Hardcoded public collectors such as IOM, NOAA, GDACS, Copernicus, OpenSanctions, OFAC, ACLED, EMODnet, Marine Regions, GPSJam, and similar fixed sources remain behaviourally unchanged in Packet J v1 unless a required v1 call path already touches them.

They are recorded as legacy outbound exceptions and migrated later in bounded batches to `PUBLIC_FIXED`. The migration backlog must be explicit rather than hidden in grep output.

Packet J v1 adds a CI/static adoption guard that fails when new direct HTTP client call sites appear outside the checked-in legacy exception set. The guard must be path/call-pattern based and reviewable; it must not silently auto-approve newly discovered exceptions.

## Required security tests

All tests are deterministic and must not require live Internet access.

The policy suite must prove at minimum:

- `127.0.0.1`, `localhost`, RFC1918, IPv6 loopback, link-local, multicast, unspecified, reserved, and metadata addresses are blocked by `PUBLIC_UNTRUSTED`.
- IPv4-mapped IPv6 cannot bypass private/loopback classification.
- A hostname resolving to any forbidden A/AAAA answer is blocked.
- A public first hop redirecting to a private/metadata destination is blocked before the second connection.
- A simulated DNS rebinding attempt cannot change the connection target after validation; the transport connects only to an IP from the validated answer set while preserving original Host/SNI.
- URL userinfo, non-HTTPS schemes, and non-443 ports are rejected by `PUBLIC_UNTRUSTED`.
- `PUBLIC_FIXED` rejects a public but non-allowlisted redirect/host.
- `OPERATOR_INTERNAL` can intentionally reach configured loopback/private endpoints but cannot derive a new origin from request data.
- Oversized declared and streamed bodies fail at the configured cap.
- Image contracts reject non-image content types.
- Timeout and redirect failures surface only bounded reason codes.
- Metrics contain no hostname/URL/IP cardinality and logs do not expose query tokens or authorization values.

Migration tests must also preserve each existing caller's success/failure contract, including drift fallback and auth fail-closed behaviour.

## Rollout and compatibility

No database migration is required. The canonical client is introduced behind existing caller interfaces so downstream domain code does not learn about transport policy.

The v1 rollout is code-only. No production flag is required for `PUBLIC_UNTRUSTED`: once the vulnerable image path is migrated, the safety policy is mandatory and fail-closed. Operator-configured migrations are validated against the current production configuration before restart so legitimate private/internal destinations are not accidentally blocked.

A blocked request is never retried through a legacy direct client as a fallback. Network fallback may change computation source only where the caller already has an explicit safe fallback, such as remote drift to in-process drift.

## Out of scope

Packet J v1 does not:

- change collector classification, publication policy, Humanitarian/Maritime authority, lifecycle, or evidence confidence;
- migrate every fixed public collector in one change;
- proxy all traffic through a new egress service;
- govern WebSocket transports used by AIS/radio in this version;
- persist new request/response bodies;
- add a user-configurable allowlist UI;
- allow request data to opt into `OPERATOR_INTERNAL`;
- weaken TLS verification for pinned HTTPS connections.

WebSocket URL policy and complete `PUBLIC_FIXED` collector migration are follow-up batches after the v1 HTTP boundary is proven in production.

## Exit gate

Packet J v1 is complete only when one exact implementation SHA proves all of the following:

- canonical sync and async outbound clients exist with the three trust profiles;
- DNS/IP validation, connection pinning, manual redirects, bounded reads, timeout policy, and redacted errors are covered by RED→GREEN tests;
- every required v1 call site has migrated and has no legacy-network fallback;
- `/api/v1/intel/extract-image` cannot reach loopback/private/link-local/metadata targets through direct URL, DNS answer, or redirect;
- existing X media, auto-drift, remote drift, OIDC/JWKS, and witness behaviours pass their focused regression suites;
- the legacy outbound exception inventory is explicit and the adoption guard rejects new bypasses;
- outbound observability uses bounded labels only;
- Ruff critical, mypy for touched canonical modules, dependency/security tests, Full CI, and exact-diff review are green;
- production restart/config validation confirms legitimate operator-internal endpoints still function;
- controllers record the implementation SHA, remaining legacy collector batches, and production verification result.

No production completion claim may be made from unit tests alone; the high-risk image fetch block and operator-internal paths must be smoke-verified after deployment without disclosing configured private URLs or credentials.
