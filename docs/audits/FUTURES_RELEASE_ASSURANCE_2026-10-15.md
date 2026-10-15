# SeaCommons Futures: partner-facing release assurance
**Date:** 2026-10-15
**Scope:** partner UX, semantic integrity and front-end boundary; no production DB or Oracle worker changes.

## Independent standards

1. Claim validity: evidence source and maturity (operational / pilot / concept / requested support) for every material assertion.
2. Metric validity: original stored entity, SQL selection, time field, retention and freshness. No implicit null-to-zero coercion.
3. Usability: accessible hover, touch and keyboard guidance; honest partner actions; no nested buttons.
4. Release evidence: unit, build, browser, source code, actual deployment SHA and live status; Vercel READY alone cannot prove data quality.

## Primary evidence and caveats

- Public Overall: `GET /api/v1/futures/overall`, `apps/api/core/api/routes/ops.py`. Exact retained IntelEvent database count, cached up to 15 min, not incidents or immutable lifetime intake.
- 24h/7d: `GET /api/v1/status?hours=24` and `?hours=168`. Different time-window populations, not additive.
- Protected all-time: `/api/v1/operator/ingestion/overall-metrics`, `operator_ingestion.py`. Per-query timeout; some planner-based estimates indicated with an approximation mark.
- OIDC: `apps/web/src/auth.jsx`, `apps/web/api/proxy.js` and `apps/api/core/security.py`. The backend independently verifies JWT issuer/signature/audience; actual authenticated user session requires a separate live acceptance test.
- Invitations: `futures_invitations.py` and API proxy. The currently deployed invitation integration does not meet the required authorization and gateway policy; the Futures proxy refuses invitation mutations. Do not expose a false working form or enable a POST route without role verification.
- Agents: `data/futures-scheduled-tasks.json` is a periodically imported snapshot, not a live run-state oracle.
- Provider: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm documents up to two AMD E2.1.Micro within Always Free and home-region capacity limitations; https://www.oracle.com/europe/cloud/free/faq/ documents identity/payment-card verification.
- Physical devices: `NetworkPlatform.jsx` references actual manufacturer parts and Wikimedia image-source pages; hardware remains a concept/pilot unless independently deployed and accepted.

## Findings

P0: Public Overall fallback used `Number(null)`, which yields a false zero. Contract must reject null/malformed/inconsistent counts. The public fallback supplies *only* normalized IntelEvent inventory, with all other historical measures marked unavailable.

P1: Authenticated API failures were indistinguishable from service outages. Propagate HTTP status and show separate authentication remediation. Do not retry another protected historical API after 401/403.

P1: Device selector `button` contained glossary `button`; remove nested interactivity to preserve valid keyboard and focus handling.

P1: Invitation submission was shown but cannot save or approve requests. Replace with transparent manual review instructions until backend authentication, membership policy and access checks are ready.

P2: Agents' frozen state cannot be advertised as real-time ACTIVE. Show state as imported and warn if older than 24h.

P2: Software-tool module claims should link to versioned repository implementation directories. Reusability across unbuilt verticals is a hypothesis, not demonstrated deployment.

## Required tests and release evidence

- Retained contract tests: null/NaN/empty, exact zero, positioned > total, bad timestamp.
- Frontend transport: HTTP 401 surfaced without leaking tokens.
- Browser flows: denied session vs downtime, Overall partial / malformed, accessible device selection, no fake invitation submission, stale Agents disclosure.
- Build: lint, TypeScript, JS unit suites, unified Vite.
- Live: exact deployed SHA, overall and rolling 24/168 HTTP 200; no anonymous protected operator data; forged signed-token check 401.
- Must test a real authorized user's signed-in 24h/7d/Overall before full authenticated release acceptance.
- Remaining Play browser and radio CI failures must be recorded, not hidden.

## Outside scope

Oracle's checkout contains local changes; no unreviewed pull, migration or restart. Public operator endpoint access controls outside Futures warrant a dedicated security review. Node `url.parse()` deprecation warns on existing Vercel runtime paths, requiring ownership and tracing.

## Final release

Pending recorded CI, deployment and endpoint verification for the exact merged SHA.
