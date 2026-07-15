# Architecture

## Current implementation

The current application is a React/Vite/MapLibre console backed by FastAPI and
SQLAlchemy. SQLite is supported only for local development. Production uses
PostgreSQL/PostGIS, Valkey, Keycloak and Caddy. Drift and some ingestion work is
still executed in API background threads; durable workers are a target, not a
current capability.

```mermaid
flowchart LR
  U[Operator] --> C[Caddy TLS]
  C --> W[React console]
  C --> A[FastAPI]
  C --> K[Keycloak OIDC]
  A --> P[(PostgreSQL/PostGIS)]
  A --> V[(Valkey cache)]
  A --> O[(MinIO object storage)]
  T[Telegram / signed partner webhook] --> A
  A --> Q[(Durable job queue)]
  Q --> R[Worker]
  R --> D[OpenDrift]
```

## Target boundary

Drift and alert simulations use a database-backed durable queue in production,
with leases, retry backoff and dead-letter state. Media extraction and report
generation still need to move to the worker before those paths can scale
horizontally.
