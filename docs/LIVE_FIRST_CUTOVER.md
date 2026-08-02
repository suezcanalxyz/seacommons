# SeaCommons Live-first cutover

Status: implementation plan for a clean realtime start. Existing SeaCommons data may be discarded.

## Objective

Run `live.seacommons.org` as an ephemeral realtime operational surface rather than an archive or a mirror of the current database.

The system starts from the moment it is enabled. It does not backfill existing incidents. Each accepted event is visible for a limited TTL, is replaced when the same incident changes, and is removed immediately when resolved or archived.

## Runtime path

```text
source collector
  -> existing IntelEventDB write
  -> live publisher scan, every 1 second
  -> durable SQLite outbox
  -> signed POST to Cloudflare
  -> Durable Object state replacement
  -> WebSocket broadcast to browsers
```

The database is used only as a local short-lived interchange point. Historical completeness is not required.

## Realtime semantics

The Live edge now implements:

- six-hour default TTL, configurable with `LIVE_EVENT_TTL_SECONDS`;
- no HTTP caching for the current snapshot;
- a WebSocket snapshot on connection;
- deterministic incident IDs and material state-version IDs;
- replacement of an older version of the same incident;
- immediate removal when an event is marked resolved or archived;
- `/v1/live/status` reporting freshness and connected clients;
- authenticated `/v1/live/reset` for a clean start;
- no historical backfill requirement.

An event is considered a new material version when geometry, confidence, public properties, source URL or state changes.

## Oracle publisher settings

Use:

```env
LIVE_EDGE_INGEST_URL=https://seacommons-edge.seacommons.workers.dev/v1/live/events
LIVE_EDGE_INGEST_SECRET=replace-with-cloudflare-secret
SEACOMMONS_NODE_ID=oracle-intel-01
LIVE_EDGE_OUTBOX_PATH=/home/ubuntu/seacommons/shared/live-edge-outbox.db
LIVE_EDGE_POLL_SECONDS=1
LIVE_EDGE_BATCH_SIZE=25
LIVE_EDGE_SCAN_LIMIT=200
LIVE_EDGE_WINDOW_MINUTES=360
LIVE_EDGE_TIMEOUT_SECONDS=8
LIVE_EDGE_MAX_ATTEMPTS=20
```

The publisher rescans only the configured recent window. Delivered material versions are remembered for 48 hours in the local outbox database and are not retransmitted.

## Clean start

Old application and outbox data can be removed before activation.

Stop the publisher:

```bash
sudo systemctl stop seacommons-live-edge-publisher
```

Remove its transient delivery state:

```bash
rm -f /home/ubuntu/seacommons/shared/live-edge-outbox.db*
```

Reset the Cloudflare Live room with a signed empty JSON body:

```bash
BODY='{}'
SIGNATURE=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$LIVE_EDGE_INGEST_SECRET" -hex | awk '{print $2}')

curl -X POST \
  https://seacommons-edge.seacommons.workers.dev/v1/live/reset \
  -H 'Content-Type: application/json' \
  -H "X-SeaCommons-Signature: $SIGNATURE" \
  --data "$BODY"
```

Restart:

```bash
sudo systemctl start seacommons-live-edge-publisher
```

Only events in the recent live window are then considered. To guarantee an absolutely empty initial state, temporarily set `LIVE_EDGE_WINDOW_MINUTES=5`, start the service, and increase it only if needed.

## Health checks

Edge service:

```bash
curl https://seacommons-edge.seacommons.workers.dev/health
```

Realtime status:

```bash
curl https://seacommons-edge.seacommons.workers.dev/v1/live/status
```

Current state:

```bash
curl https://seacommons-edge.seacommons.workers.dev/v1/live/snapshot
```

A healthy active result should report:

```json
{
  "status": "live",
  "age_seconds": 12,
  "event_count": 1,
  "ttl_seconds": 21600
}
```

`waiting` means the edge is online but has not received an event during the last two minutes. It does not necessarily mean the collectors are broken.

## Operational latency target

With one-second publisher polling, normal latency should be approximately:

```text
collector persistence: source-dependent
publisher detection: 0-1 second
network and edge acceptance: usually below 1 second
WebSocket delivery: near immediate
```

The realistic target after the collector has produced an event is under three seconds.

## Current limitation

The publisher currently discovers events through the local Intel database rather than being called synchronously inside every collector. This keeps the change reversible and avoids modifying all collectors at once, but adds up to one second of detection latency.

A later optimization can add a common `publish_live(event)` hook directly to `IntelStore.add`, `enrich_location`, and `update_metadata`. The edge protocol and outbox can remain unchanged.

## Data retention

Live is not the archive:

- active edge state: six hours by default;
- resolved incidents: removed immediately;
- local delivered-version registry: 48 hours;
- existing operational database: may be deleted or rotated independently;
- R2/Nostr/OpenTimestamps: disabled unless a separate archival policy is explicitly approved.

## Acceptance test

1. Reset edge and local outbox.
2. Confirm snapshot contains zero events.
3. Generate one real or controlled collector observation.
4. Confirm it appears on `/v1/live/snapshot` within three seconds of DB persistence.
5. Enrich its coordinates and confirm the marker is replaced rather than duplicated.
6. Mark it resolved and confirm it disappears.
7. Stop Oracle and confirm the last active state remains available until TTL expiration.
8. Restart Oracle and confirm new events resume without replaying the old database.

## Definition of Live

SeaCommons may show `LIVE` only when:

- the WebSocket is connected;
- `/v1/live/status` is reachable;
- the source status is not stale;
- each marker displays its source observation time;
- the interface does not present absence of reports as absence of distress.

This architecture is realtime best-effort. It is not an emergency dispatch service and does not provide an SLA.
