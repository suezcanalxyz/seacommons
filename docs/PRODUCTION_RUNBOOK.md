# Production runbook

## Scope

The production stack is entirely self-hostable. Oracle Cloud may host the VM but
is not required; any Linux host with Docker Compose works.

## Required DNS

- `seacommons.org` -> host public IP
- `www.seacommons.org` -> `seacommons.org`
- `live.seacommons.org` -> authenticated live-map frontend
- `play.seacommons.org` -> isolated public-demo frontend
- `api.seacommons.org` -> host public IP
- `auth.seacommons.org` -> host public IP

The Vercel edge profile serves both frontends with same-origin `/api` routes.
The operational and demo API processes stay separate internally, even though
users do not need a second public API hostname.

After the new names pass TLS and application acceptance, point
`seacommons.suezcanal.xyz` to the same host and keep the permanent redirect to
`https://seacommons.org`. Do not delete the old record before the redirect is
live, or existing bookmarks and indexed URLs will break.

## Bootstrap

1. Copy `.env.example` to `.env.production` and generate unique secrets.
2. Set `POSTGRES_PASSWORD`, `KEYCLOAK_DB_PASSWORD`,
   `KEYCLOAK_ADMIN_PASSWORD`, `MINIO_ROOT_PASSWORD` and a signing key.
3. Start with `docker compose --env-file .env.production -f deploy/docker-compose.production.yml up -d --build`.
4. Keycloak imports the versioned `seacommons` realm, OIDC client, API audience,
   roles and institutional login theme from `ops/keycloak` on first start.
5. Create users through Keycloak, verify their email, assign the minimum role
   required and enable an MFA policy before live use.
6. Test login, authenticated mutation, denied anonymous mutation, database backup
   and restore before pointing public DNS.

The public demo uses a separate frontend, API and SQLite volume. It allows SAR
simulation creation but rejects case management, governance and ingestion
mutations. Never configure live AIS, WhatsApp, Telegram or partner secrets on
`demo-api`.

The production profile requires `JOB_EXECUTION_MODE=queue`. The `worker` service
claims jobs using database leases and retries failures with exponential backoff.
Inspect `/api/v1/jobs/{job_id}`; a `dead` job requires operator review rather
than an automatic infinite retry.

## Observability

Prometheus scrapes the API over the private Compose network. Caddy deliberately
returns 404 for public requests to `/metrics`. Grafana is bound only to
`127.0.0.1:3001`; access it with an SSH tunnel such as
`ssh -L 3001:127.0.0.1:3001 <host>` and open `http://localhost:3001`.

The provisioned dashboard reports request rate, p95 latency, queue state and
fresh worker heartbeats. `/health` is a liveness probe; `/ready` verifies the
database dependency. Application logs are JSON and every HTTP response carries
`X-Request-Id`.

## Roles

`researcher`, `analyst`, `operator`, `case_manager`, `data_steward`,
`integration_service`, `administrator`.

## Webhooks

Telegram uses `X-Telegram-Bot-Api-Secret-Token`. Partner webhooks sign the exact
body with HMAC-SHA256 and send `X-Seacommons-Signature: sha256=<hex>`. Meta
WhatsApp Cloud signs the exact body in `X-Hub-Signature-256`; its callback is
`/api/v1/ingest/meta/whatsapp`. Missing verification configuration fails closed.
Set `PUBLIC_API_URL=https://api.seacommons.org` so Engine can display the exact
callback address without exposing credentials.

For partner-owned WhatsApp numbers, configure the platform Meta app with
`META_APP_ID`, `META_APP_SECRET`, `META_WEBHOOK_VERIFY_TOKEN` and the Embedded
Signup configuration ID. Each partner connector is tenant-scoped by its Meta
`phone_number_id`; its access token stays in Oracle Vault and the application
database stores only a `secret_ref`. Inbound messages are private by default.
Twilio remains available as a legacy bridge for SMS and existing deployments.

When `TELEGRAM_OPERATIONS_CHAT_ID` is configured, that chat can use
`/case <case-id-or-prefix> <note>` and `/status <case-id-or-prefix> <status>`.
Commands from every other chat are rejected even when delivered by the valid bot
webhook.

## Backups

Back up PostgreSQL and MinIO independently to encrypted off-host storage. Perform
a restore drill before launch and quarterly thereafter. Valkey is disposable and
must never be the sole store for operational data.
