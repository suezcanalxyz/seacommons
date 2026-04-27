# Pilot Phase 0

Status: completed

Recommended runtime:
- Docker local for Postgres/Redis
- Local backend only if Docker is not available

Collected:
- `SUEZCANAL_SIGNING_KEY`: generated
- `AISSTREAM_KEY`: present in local `.env`
- `CMEMS_USERNAME`: present in local `.env`
- `CMEMS_PASSWORD`: present in local `.env`

Still required:
- `DATABASE_URL`
- `REDIS_URL`

Recommended pilot defaults:
- `MOCK=false`
- `TIMEZERO_ENABLED=false` unless a real TimeZero target is ready
- `WITNESS_ENDPOINTS=` empty for first pilot unless witness receivers are live

Security note:
- Existing secrets found in local `.env` should be rotated before pilot if they were shared in logs, audits, or chat.
