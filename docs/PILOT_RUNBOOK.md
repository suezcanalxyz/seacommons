# Pilot Runbook

## Goal

Run the API-first pilot with durable alert, drift, and forensic persistence.

## Recommended start

```powershell
docker compose -f docker-compose.pilot.yml up --build
```

## Required env

- `SUEZCANAL_SIGNING_KEY`
- `MOCK=false`

## Recommended env

- `DATABASE_URL=postgresql://suez:canal@postgres:5432/suezcanal`
- `REDIS_URL=redis://redis:6379/0`

## Smoke checks

1. `GET /health`
2. `GET /docs`
3. `POST /api/v1/alert`
4. `GET /api/v1/alert/{event_id}`
5. `GET /api/v1/forensic/{event_id}`

## Notes

- Frontend is intentionally excluded from the first pilot path until the repo structure is realigned.
- If no external DB URL is provided, the code falls back to local SQLite for pilot bootstrap.
