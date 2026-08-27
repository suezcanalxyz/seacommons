# SeaCommons security model

Status: canonical security design. Last reviewed: 2026-08-26.

This document describes implemented controls and trust boundaries. Operational
deployment requirements and vulnerability reporting remain in the root
`SECURITY.md` and `docs/PRODUCTION_RUNBOOK.md`.

## Assets and trust boundaries

Primary protected assets are raw humanitarian reports, personal/contact data,
precise locations, credentials, case records, forensic artifacts and provider
tokens. The main boundaries are:

1. public internet to authenticated operational API;
2. signed provider webhook to ingestion parser;
3. private operational state to the public Live projection;
4. API publisher to Cloudflare edge ingestion;
5. application processes to database/object storage.

Public Live is a separate, reduced-trust data product. It receives only the
validated public projection, never direct database access.

## Authentication and authorization

Production uses OIDC JWTs. The API accepts RS256/ES256 tokens with issuer,
audience, expiry, issue time and subject validation. Roles are grouped into
read and write sets; administrator-only paths are checked centrally by the API
authorization middleware.

Browser WebSockets authenticate before acceptance. Because browser APIs cannot
set an Authorization header for WebSocket upgrades, clients send two
subprotocols: `bearer` and the JWT. The server validates the second value and
selects only the `bearer` protocol; invalid or underprivileged clients receive
4401/4403 closure codes.

Anonymous routes are intentionally narrow: probes/docs, provider webhooks with
their own authenticity checks, resource-bounded public simulation actions and
read-only `/api/v1/live/*` endpoints. New routes default to requiring
authentication and must be reviewed against this list.

## Ingestion authenticity

- Meta WhatsApp verifies `X-Hub-Signature-256` over the exact request body.
- Telegram verifies its configured secret-token header.
- Partner/external webhooks use HMAC-SHA256 over the exact body.
- Edge publisher requests use HMAC-SHA256 and a timing-safe comparison.

Missing production verification configuration fails closed. Connector database
records contain secret references, not provider tokens. Secrets belong in the
deployment secret manager/environment and must never be committed.

## Public/private enforcement

User-originated input defaults to private. Publication status, source policy,
verification status, lifecycle and location precision use the canonical models
in `core/domain/live_contracts.py` and the matching JSON schemas. Public
projection follows these rules:

- explicit private status always wins;
- unknown or blocked source policy is rejected;
- raw source/caller text and private metadata are not copied;
- geometry is absent, coarse or area-based when precision does not justify a
  reported point;
- contract-invalid output is dropped and logged without payload content.

The edge independently rejects private visibility and invalid public vocabulary.
This defence-in-depth validation does not replace the backend projection.

## Production fail-safe configuration

`validate_production_security()` prevents startup unless production enables
authentication, configures OIDC issuer/audience and object storage, and selects
the durable queue execution mode. Public demo mode blocks operational mutations
and must not receive live provider credentials.

TLS termination, database network isolation, encrypted off-host backups, MFA,
least-privilege role assignment and secret rotation are deployment controls.

## Known limitations and accepted risks

- JWKS retrieval trusts the operator-configured HTTPS endpoint and platform TLS
  validation; certificate pinning is not implemented.
- The controlled-node public edge currently uses one shared HMAC secret. It is
  not suitable for arbitrary third-party federation; per-node asymmetric keys
  and overlapping rotation are future work.
- Source-health state is process-local, while durable worker heartbeats are in
  the shared database. Split deployments must monitor both worker and API sync
  metrics.
- SeaCommons is a research prototype and is not certified for emergency
  dispatch or a replacement for maritime rescue coordination authorities.

## Verification

Security and privacy regressions are covered by `tests/test_security.py`,
`tests/test_connectors.py`, `tests/test_public_policy.py`,
`tests/test_live_contracts.py` and the Edge tests. Dependency audits and update
automation are configured in `.github/workflows/ci.yml` and
`.github/dependabot.yml`.
