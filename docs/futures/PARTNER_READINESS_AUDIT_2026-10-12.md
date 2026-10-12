# Futures partner readiness audit
Date: 2026-10-12
Scope: `futures.seacommons.org`, SeaCommons project and partner-facing materials.
No external partner identities or confidential proposals are included in this report.

## Executive assessment
Futures is a functioning OIDC-protected frontend and useful overview of public-safe
SeaCommons operational data. It is **not yet a production-grade private collaborative
workspace**. The identity gate, document registry and visual demo should not be
mistaken for per-resource authorization or persistent partner operations.

## Evidence inspected
- `apps/web/src/futures/FuturesApp.jsx`, `data.js`, browser E2E and API client.
- API responses via `https://futures.seacommons.org/api/v1/status?hours=24`,
  `/api/v1/play/counts`, `/api/v1/live/pipeline`.
- Dedicated identity project schemas: `documents`, `document_versions`,
  `memberships`, `access_grants`, and storage bucket inventory.
- As of this audit: 11 document rows, 11 version rows, **0 memberships**,
  **0 access grants**, **0 storage buckets**. Document tables and SELECT RLS
  policies exist; this does not establish a working file-upload/download service.
- The public-safe 24 h status snapshot returned 24,069 raw observations, 2,855
  normalised events, 368 maritime episodes, 7 corroborated episodes. Play
  returned 2,881 cumulative archive entries. These are not interchangeable
  populations and cannot be used as impact metrics.
- Production pipeline includes degraded acquisition families; these must remain
  visible rather than being promoted to unconditional reliability claims.

## Current changes in this branch
- Overview: evidence mission, two operating verticals, stage-level metrics,
  transparent API provenance, current product surfaces.
- Applied research: an explicit **operational core** plus individually labelled
  **pilot-design / concept** vertical pathways; no unverified impact claims.
- Pilot framework: define / baseline / pilot / evaluate with locally contextual
  questions and data safeguards.
- Docs: searchable resource catalogue, in-browser partner deck and interim
  versioned repository intake for non-sensitive assets.
- Access UI: no invented bootstrap administrator grant; authentication is not
  represented as authorization.

## P0: must complete before confidential partner onboarding
1. **Server-side grants**: verify signed Suez Identity JWT, resource audience,
   issuer, expiry and workspace membership on every private SeaCommons
   API call; fail closed on wrong/missing grant. Never infer a role from a
   browser claim or successful OAuth redirect.
2. **One authoritative document service**: decide the owner (SeaCommons DB +
   private object storage recommended). Versioned metadata, private bucket,
   per-resource RLS/auth, signed URL expiry, upload limits, content-type/magic
   validation, audit record and virus/malware policy.
3. **Role onboarding**: administrator, editor, analyst, read-only partner and
   restricted-document reviewer with invitation expiry, revocation,
   workspace-specific membership and least privilege.
4. **Isolated partner test**: two organisations, one granted and one not; no
   cross-tenant document enumeration, API leakage, storage URL reuse or
   privilege escalation; check revoked account and expired token.
5. **No uncontrolled public assets**: keep restricted attachments out of the
   repository's public web build and out of unauthenticated GitHub raw links.
6. **Production release qualification**: test fresh-code login, remembered
   browser, logout, callback, history, mobile Docs, on-failure dashboard
   fallback, and private endpoint 401/403.

## P1: pilot-operational requirements
- Repository-backed files are only an **interim administrator intake**. Build
  authenticated browser uploads with queue/progress/retry/version rollback
  only after P0 authorization and storage have passed.
- Convert static roadmap cards into owned work items, due dates, decision logs,
  review states and reproducible activity history.
- Add explicit API freshness and SLO thresholds, error budgets, storage
  retention/size monitoring and alerting. Operational availability must not
  be interpreted as evidence confirmation.
- Implement independently reviewable partner dossiers: question, bounded
  geography, source inventory, timeline, evidence statements, contradictions,
  findings status, limitations and exports.
- Make indicator registry typed: unit, time window, denominator, origin,
  verification level, data steward, baseline and confidence limits.
- Support bilingual content and exportable reports, respecting licence terms
  and sensitive humanitarian-location policies.

## P2: vertical expansion framework
- Every new sector gets its own bounded data contracts, source/licence audit,
  method card, impact-evaluation approach, access controls and validation plan.
- Coastal/island observatory: link public geospatial and territorial statistics
  with verified maritime context. No personal data ingestion by default.
- Participatory impact: consented qualitative records alongside project
  baseline/outcome metrics, not synthetic 'social impact scores'.
- Water, decentralised energy and food systems: only after primary local data
  owners, instruments, QA and maintenance feasibility are confirmed.
- Keep vertical code modular, with no cross-tenant grants or datasets implied
  by mere presence of navigation.

## Acceptance criteria
- P0: client A never reads client B document in UI, DB, object store or API;
  revoked member gets 403; upload/version/download audit round trip passes.
- P1: one pilot report can be reproduced from named sources and dated baseline;
  an unavailable source is visible and never silently replaced with a fake 0.
- P2: prospective verticals remain clearly marked as proposals until technical
  and governance checks have been completed.

## Decision
Release the partner-facing overview and non-sensitive native presentation
with explicit maturity labels. Do not activate direct uploads or claim a
fully operational partner workspace until P0 is complete.
