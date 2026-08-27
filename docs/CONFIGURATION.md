# Configuration

Status: canonical configuration reference. Last reviewed: 2026-08-27.

All settings are environment variables, loaded by `core/config.py`
(`SuezCanalConfig`, a pydantic-settings model). Unknown variables are ignored,
so deployed `.env` files stay forward compatible. This page groups the surface
conceptually; `ops/.env.production.example` is the annotated template.

## Groups

| Group | Variables (prefix / key) |
| --- | --- |
| Runtime | `RUNTIME_PROFILE`, `MOCK` (deprecated), `DEMO_PUBLIC_MODE`, `LOG_FORMAT`, `EXTERNAL_DATA_TIMEOUT_S` |
| Database | `DATABASE_URL`, `REDIS_URL`, `DEFAULT_RETENTION_DAYS` |
| Auth | `AUTH_ENABLED`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, `OIDC_ROLES_CLAIM`, `OIDC_DEFAULT_ROLES`, `OIDC_ORGANIZATION_CLAIM` |
| Object storage | `OBJECT_STORAGE_ENDPOINT`, `OBJECT_STORAGE_ACCESS_KEY`, `OBJECT_STORAGE_SECRET_KEY`, `OBJECT_STORAGE_BUCKET`, `OBJECT_STORAGE_SECURE`, `MAX_ATTACHMENT_BYTES` |
| Jobs / workers | `JOB_EXECUTION_MODE`, `JOB_MAX_ATTEMPTS`, `JOB_LEASE_SECONDS`, `JOB_POLL_SECONDS`, `WORKER_HEARTBEAT_SECONDS`, `OPENDRIFT_PREWARM_ENABLED` |
| Intel / OSINT | `INTEL_ENABLED`, `INTEL_MONITORS_ENABLED`, `INTEL_AUTO_DRIFT_ENABLED`, `EXTERNAL_INTEL_INGEST_SECRET`, `TWITTER_BEARER_TOKEN`, `TWIKIT_*` |
| Drift | `ALERT_DRIFT_DURATION_H`, `DRIFT_WORKER_URL`, `DRIFT_WORKER_SECRET`, `DRIFT_WORKER_TIMEOUT_S`, `API_INTERNAL_URL`, `API_INTERNAL_HOST_HEADER` |
| AIS | `AISSTREAM_KEY`, `AISSTREAM_NGO_KEY` (must be a different account) |
| Weather / marine | `CMEMS_USERNAME`, `CMEMS_PASSWORD`, `CMEMS_*_DATASET`, `OPEN_METEO_BASE` |
| Messaging / webhooks | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OPERATIONS_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET`, `META_APP_*`, `META_WEBHOOK_VERIFY_TOKEN`, `META_EMBEDDED_SIGNUP_CONFIG_ID`, `TWILIO_*`, `PARTNER_WEBHOOK_SECRET`, `MAX_WEBHOOK_BODY_BYTES`, `PUBLIC_API_URL` |
| External APIs / sensors | `ADSB_EXCHANGE_KEY`, `ACLED_KEY`, `GPSJAM_URL`, `MADRIGAL_URL`, `EMSC_WS`, `TID_*`, `GNSS_ENABLED`, `INFRASOUND_*`, `SEISMIC_*`, `HYDRO_ENABLED`, `SDR_*`, `ADSB_*`, `WITNESS_ENDPOINTS`, `TIMEZERO_*` |
| Correlation / SAR tuning | `CORRELATION_CONFIDENCE_ALERT`, `CORRELATION_CONFIDENCE_URGENT`, `SAR_TRIANGULATION_*` |
| Edge (Worker vars, `apps/edge/wrangler.jsonc`) | `ALLOWED_ORIGINS`, `LIVE_EVENT_TTL_SECONDS`, `LIVE_HEARTBEAT_MAX_AGE_SECONDS`, `NOSTR_BRIDGE_URL`; publisher side: `LIVE_EDGE_INGEST_URL`, `LIVE_EDGE_INGEST_SECRET`, `LIVE_EDGE_METRICS_PORT` (0 = off), `LIVE_EDGE_POLL_SECONDS`, `LIVE_EDGE_BATCH_SIZE`, `LIVE_EDGE_MAX_ATTEMPTS`, `LIVE_EDGE_HEARTBEAT_SECONDS`, `SEACOMMONS_NODE_ID`, `LIVE_EDGE_OUTBOX_PATH` |
| Observability | see [PRODUCTION_RUNBOOK.md](PRODUCTION_RUNBOOK.md#observability); metrics are always on, exposure is controlled by the reverse proxy |

## Required in production

With `RUNTIME_PROFILE` in {`production`, `prod`} the API refuses to start
without `AUTH_ENABLED=true`, `OIDC_ISSUER`, `OIDC_AUDIENCE`,
`OBJECT_STORAGE_ENDPOINT` and `JOB_EXECUTION_MODE=queue`
(`core/security.py::validate_production_security`). The edge publisher also
requires `LIVE_EDGE_INGEST_URL` and `LIVE_EDGE_INGEST_SECRET`.

## Combination validation

`core/config_validation.py` checks combinations that are impossible or unsafe
regardless of profile. The API runs it at startup (errors abort, warnings log);
run it standalone before a deploy:

```bash
cd apps/api && python -m core.config_validation
```

Errors (abort): invalid `JOB_EXECUTION_MODE`; `DEMO_PUBLIC_MODE=true` on a
production profile; `AISSTREAM_NGO_KEY` equal to `AISSTREAM_KEY`;
`DRIFT_WORKER_URL` without `DRIFT_WORKER_SECRET`;
`CORRELATION_CONFIDENCE_ALERT` >= `CORRELATION_CONFIDENCE_URGENT`.

Warnings (proceed): `MOCK=true` on production; `TWIKIT_ENABLED` without a
usable cookies file; `TWIKIT_ALERTS_ENABLED` without Telegram credentials;
priority poll interval slower than the base interval; a Telegram chat id with
no bot token; partial Meta WhatsApp configuration.

Every check fires only on a combination that is already broken at runtime — no
previously-working environment starts failing.

## Development defaults / demo-only

`scripts/run_dev.sh` sets `MOCK=true`, SQLite, `DEMO_PUBLIC_MODE=true`, no
auth. `MOCK` and `DEMO_PUBLIC_MODE` are dev/demo only; `DEMO_PUBLIC_MODE`
allows public SAR simulation while rejecting case, governance and ingestion
mutations. Never set live AIS/CMEMS/WhatsApp/Telegram secrets on a demo API.

## Related documents

- [Deployment](DEPLOYMENT.md)
- [Development](DEVELOPMENT.md)
- [Security model](SECURITY_MODEL.md)
