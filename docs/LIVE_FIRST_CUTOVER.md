# SeaCommons Live-first cutover

Status: deployed, unified with the VM-hosted lifecycle model. Distress markers are colored (active/resolved/archived), not deleted, until the true 7-day cutoff.

## Objective

Run `live.seacommons.org` as a realtime operational surface delivered over a zero-cost Cloudflare edge (WebSocket + Durable Object), while keeping exactly one lifecycle policy: `core/intel/lifecycle.py`, shared with the VM-hosted `/api/v1/live/signals` feed (`core/api/routes/live.py`).

The system does not backfill on a cold start (see "Clean start" below), but once running it is **not** a bare 6-hour ephemeral cache: a distress marker stays visible â€” colored red (active), green (resolved), or gray (archived/stale) â€” for its full lifecycle window (`lifecycle.DISTRESS_LIVE_MAX_AGE_DAYS`, 7 days), and is only actively removed from the edge once that window ends (an explicit `incident_removed`/`expired` signal from the publisher). The edge's own `LIVE_EVENT_TTL_SECONDS` is a backstop only, set well beyond that window, in case the publisher stops running before it can send the removal itself.

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

The Live edge implements:

- a `LIVE_EVENT_TTL_SECONDS` backstop (default 4 days â€” beyond the 7-day lifecycle window on purpose; see "Data retention" below), not the primary
  expiry mechanism;
- no HTTP caching for the current snapshot;
- a WebSocket snapshot on connection;
- deterministic incident IDs and material state-version IDs;
- replacement of an older version of the same incident;
- **resolved/archived is a color, not a removal** â€” a marker keeps
  broadcasting as `event` (never `remove`) while
  `event.properties.incident_lifecycle` is `active`/`resolved`/`archived`;
  only `event.properties.expired === true` (equivalently
  `type === 'incident_removed'`) triggers a `remove` broadcast and drops it
  from Durable Object state;
- `/v1/live/status` reporting freshness and connected clients;
- authenticated `/v1/live/reset` for a clean start;
- no historical backfill requirement on a cold start.

An event is considered a new material version when geometry, confidence, public properties (including `incident_lifecycle`), source URL or expiry state changes â€” so a lifecycle transition (e.g. active â†’ resolved) always produces a fresh version and is re-delivered/re-broadcast.

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
# Must exceed lifecycle.DISTRESS_LIVE_MAX_AGE_DAYS (7 days) with margin so an
# aging event is still inside the scan when it needs its final removal sent.
LIVE_EDGE_WINDOW_MINUTES=11520
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
  "ttl_seconds": 345600
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

Live is not a full archive/replay surface, but a distress marker's lifecycle is now identical whether served from the VM API or the edge:

- distress markers stay visible (colored) for `lifecycle.DISTRESS_LIVE_MAX_AGE_DAYS` (7 days) from the source's own observed timestamp, then the publisher sends an explicit removal;
- edge backstop TTL: 4 days (`LIVE_EVENT_TTL_SECONDS=345600`) â€” only matters if the publisher stops running before the 3-day mark;
- local delivered-version registry: 48 hours;
- existing operational database: the source of truth; not deleted or rotated by this feature;
- R2/Nostr/OpenTimestamps: disabled unless a separate archival policy is explicitly approved.

## Acceptance test

1. Reset edge and local outbox.
2. Confirm snapshot contains zero events.
3. Generate one real or controlled collector observation.
4. Confirm it appears on `/v1/live/snapshot` within three seconds of DB persistence, with `properties.incident_lifecycle === "active"`.
5. Enrich its coordinates and confirm the marker is replaced (new version) rather than duplicated.
6. Post a same-source follow-up reporting resolution and confirm the marker's `incident_lifecycle` flips to `"resolved"` in a new version â€” the marker must still be present in the snapshot, not removed.
7. Leave an unresolved marker alone for 24h+ and confirm it turns `"archived"` without being removed.
8. Advance past the 7-day window (or set a synthetic old `observed_at`) and confirm the publisher sends `type: "incident_removed"` / `properties.expired: true`, and the marker disappears from `/v1/live/snapshot`.
9. Stop Oracle and confirm the last active state remains available until the backstop TTL.
10. Restart Oracle and confirm collection resumes from the current DB state (not a full historical replay).

## Definition of Live

SeaCommons may show `LIVE` only when:

- the WebSocket is connected;
- `/v1/live/status` is reachable;
- the source status is not stale;
- each marker displays its source observation time;
- the interface does not present absence of reports as absence of distress.

This architecture is realtime best-effort. It is not an emergency dispatch service and does not provide an SLA.
