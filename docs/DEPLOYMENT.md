# Deployment

Status: canonical deployment description. Last reviewed: 2026-08-27.

This document is the map of how SeaCommons is deployed and which knobs are
safe. Step-by-step procedures live in the runbooks it links; this page owns the
model, the required configuration and the rollout/rollback order.

## Deployable surfaces

| Surface | Code | Where it runs | Critical for Public Live? |
| --- | --- | --- | --- |
| Institutional site | `apps/site` | Static host (Vercel / Cloudflare Pages) | No |
| Operational console | `apps/web` | Static host; same-origin `/api` via `vercel.json` rewrites | Serves Live UI |
| API and workers | `apps/api` | Linux host (Docker Compose in production; systemd on a single VM for pilots/demos) | Yes — publishes to the edge |
| Public Live edge | `apps/edge` | Cloudflare Worker + Durable Object | Yes — public distribution point |

The console and the demo share one codebase and one static deployment. Host
routing in `vercel.json` selects `console.html` for the operational hostnames
(`live`, `play`, `console`, `engine`) and `site.html` otherwise. The
operational and demo API runtimes stay isolated internally regardless of the
shared frontend.

## Deployment modes

### 1. Production (self-hosted)

Full stack via Docker Compose: FastAPI API, separate intel worker, durable job
worker, edge publisher, PostgreSQL, Keycloak (OIDC), MinIO (S3), Prometheus,
Grafana, Caddy. Procedure: [PRODUCTION_RUNBOOK.md](PRODUCTION_RUNBOOK.md).

Process split (see [ARCHITECTURE.md](ARCHITECTURE.md#supported-process-topologies)):

- API — `core.api.main`, `INTEL_MONITORS_ENABLED=false`
- intel worker — `python -m core.intel_worker_main`
- job worker — `python -m core.worker`, `JOB_EXECUTION_MODE=queue`
- edge publisher — `python -m core.live_edge_publisher`

### 2. Zero-cost live demo

Static frontend on Cloudflare Pages or Vercel; API on an Oracle Cloud Always
Free VM behind Nginx + Certbot, SQLite, `MOCK=true`, `DEMO_PUBLIC_MODE=true`,
no auth. Procedure: [DEPLOY_CLOUDFLARE_ORACLE.md](DEPLOY_CLOUDFLARE_ORACLE.md),
alternative hosts in [../DEMO_DEPLOY.md](../DEMO_DEPLOY.md). This mode is for
walkthroughs, never operations: SAR cases fall back to the Gaussian model and
no background sensors run.

### 3. Public Live edge

Independent of the API deployment. Procedure:
[CLOUDFLARE_EDGE_DEPLOYMENT.md](CLOUDFLARE_EDGE_DEPLOYMENT.md).

```bash
cd apps/edge && npm ci && npm test && npx wrangler login && npx wrangler deploy
```

Then set `VITE_EDGE_API_BASE` / `VITE_LIVE_EDGE_BASE` in the frontend build and
redeploy `apps/web`. The Worker's `ALLOWED_ORIGINS` var must list only real
Play/Live origins; the checked-in `localhost:5173` entry is for development.
`LIVE_EVENT_TTL_SECONDS` (691200 = 8 days) is a backstop only — the canonical
7-day removal comes from the publisher.

## Required production configuration

With `RUNTIME_PROFILE` in {`production`, `prod`}, the API refuses to start
unless all of the following are set (`core/security.py::validate_production_security`,
`core/object_store.py`):

| Variable | Requirement |
| --- | --- |
| `AUTH_ENABLED` | `true` |
| `OIDC_ISSUER` | set |
| `OIDC_AUDIENCE` | set (default `seacommons-api`) |
| `OBJECT_STORAGE_ENDPOINT` | set |
| `JOB_EXECUTION_MODE` | `queue` |

The edge publisher additionally requires `LIVE_EDGE_INGEST_URL` and
`LIVE_EDGE_INGEST_SECRET`. `core/config_validation.py` rejects unsafe
combinations at startup; run `python -m core.config_validation` before a
deploy. Full variable reference: [CONFIGURATION.md](CONFIGURATION.md).

### Optional integrations

All default to disabled/unset and degrade cleanly when absent: `AISSTREAM_KEY`
and `AISSTREAM_NGO_KEY` (must be different accounts), `CMEMS_USERNAME` /
`CMEMS_PASSWORD`, `INTEL_ENABLED` + `TWITTER_BEARER_TOKEN` / `TWIKIT_*`,
`META_APP_*` and `TELEGRAM_*` webhooks, `TIMEZERO_*`. Partner WhatsApp tokens
never live in env — the database stores a `secret_ref` and the token stays in
the host vault. Template: `ops/.env.production.example`.

### Development defaults / demo-only settings

`scripts/run_dev.sh` defaults to `MOCK=true`, `DATABASE_URL=sqlite+aiosqlite:///./suezcanal.db`,
`DEMO_PUBLIC_MODE=true`, no auth. `MOCK=true` and `DEMO_PUBLIC_MODE=true` are
demo/dev only: `DEMO_PUBLIC_MODE` allows public SAR simulation while rejecting
case, governance and ingestion mutations, and keeps the API lightweight. Never
set live AIS, CMEMS, WhatsApp or Telegram secrets on a demo API.

## DNS (production)

`seacommons.org`, `www` → site; `live.seacommons.org`, `play.seacommons.org` →
frontends; `api.seacommons.org`, `auth.seacommons.org` → API host;
`edge.seacommons.org` → Worker custom hostname (attach only after the
`workers.dev` smoke test passes).

## Rollout order

1. API host up; `/health` and `/ready` green (`/ready` checks the database).
2. Edge Worker deployed; `workers.dev` smoke test passes.
3. Frontend built with `VITE_*` edge/API bases set; deployed.
4. Attach custom hostnames.
5. End-to-end check: login, an authenticated mutation, a denied anonymous
   mutation, `POST /api/v1/alert` from the live frontend, one incident visible
   on Public Live.

## Rollback

- Frontend / site: redeploy the previous static build (host-native rollback).
- Edge Worker: `wrangler rollback`, or redeploy the previous `apps/edge` commit;
  Durable Object state and migrations `v1` are backward compatible within the
  current contract.
- API: redeploy the previous image/commit. Database migrations are expand-only;
  check the runbook before reverting one. A `dead` job needs operator review,
  not an automatic retry.
- Full cutover reversal: [LIVE_FIRST_CUTOVER.md](LIVE_FIRST_CUTOVER.md).

## Observability after deploy

Prometheus scrapes the API on the private network; `/metrics` returns 404
publicly by design. Grafana binds `127.0.0.1:3001` (reach it over an SSH
tunnel). Every HTTP response carries `X-Request-Id`; logs are JSON. See
[PRODUCTION_RUNBOOK.md](PRODUCTION_RUNBOOK.md#observability).

## Related documents

- [Architecture](ARCHITECTURE.md)
- [Development](DEVELOPMENT.md)
- [Security model](SECURITY_MODEL.md)
- [Realtime architecture](REALTIME_ARCHITECTURE.md)
