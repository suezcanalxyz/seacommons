# Futures Overall: public contract and release plan

## Requirement
Overall is an anonymous read-only summary of the retained intelligence corpus. No OIDC, token or login is required for its metrics. Detailed operator capabilities stay restricted.

## API
`GET /api/v1/futures/intelligence-overall` returns `scope=all_time`, `access=public_aggregate`, timestamp, seven stage counters, five sensor counters and explicit estimated/unavailable fields.

Counts measure separate populations, not unique vessels or confirmed incidents. The aggregate is computed by the same code as the protected operator view, with no forged or injected authorization credentials. The public response is an explicit whitelist containing no source identities, case IDs, raw observations, coordinates or evidence content.

Backend aggregation uses a five-minute cache, per-query deadlines and null for unknown values. Planner estimates are marked approximate.

## Frontend
- Overall queries the new public API only, not an operator route.
- If this API is unavailable, the independent public retained-IntelEvent API can report one validated normalized-event inventory and explicitly marks other figures unknown.
- Overall source-specific and case-specific detail requests are disabled, rather than invisibly trying protected endpoints.
- Current 24-hour and seven-day metrics remain separate, with their existing temporal semantics.

## Verification and controlled Oracle release
- Prove anonymous public 200 and unchanged protected operator 401.
- Verify all twelve counters, estimate labels, response freshness, null/zero distinction, proxy read-only allowlist and no identifier leakage.
- Pass JS/TS/build, Python targeted tests and browser contract tests.
- The Vercel merge does not deploy Oracle. Patch the two live API source files surgically with backups and change preflight; preserve all unrelated local changes.
- Reload only the API after a syntax and import test. Verify endpoint, health, production alias and private access. Roll back if any check fails.
- Never disable OIDC or expose detailed cases, source identities, raw payloads or PostgreSQL schema.

## Evidence sources
`apps/api/core/api/routes/operator_ingestion.py`, `apps/api/core/api/routes/ops.py`, `apps/web/api/proxy.js`, `apps/web/src/futures/IntelligenceDashboard.jsx` and the independent public `/api/v1/futures/overall` retained-record contract.
