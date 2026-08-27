# SeaCommons Live-first cutover

Status: deployed, unified with the VM-hosted lifecycle model. Directly resolved incidents leave operational Live immediately; active, needs-review and archived markers remain bounded by the 7-day cutoff.

## Objective

Run `live.seacommons.org` as a realtime operational surface delivered over a zero-cost Cloudflare edge (WebSocket + Durable Object), while keeping exactly one lifecycle policy: `core/intel/lifecycle.py`, shared with the VM-hosted `/api/v1/live/signals` feed (`core/live/feed.py`).

The system does not backfill on a cold start (see "Clean start" below), but once running it is **not** a bare 6-hour ephemeral cache. A directly concluded incident is removed from operational Live immediately. Other distress markers remain visible as red (active), amber (needs review), or gray (archived/stale) within `lifecycle.DISTRESS_LIVE_MAX_AGE_DAYS` (7 days). The edge's 8-day TTL is only a backstop if the publisher stops before it sends the explicit removal.

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

- an 8-day `LIVE_EVENT_TTL_SECONDS` backstop, beyond the 7-day lifecycle window, not the primary retention mechanism
  expiry mechanism;
- no HTTP caching for the current snapshot;
- a WebSocket snapshot on connection;
- deterministic incident IDs and material state-version IDs;
- replacement of an older version of the same incident;
- the edge removes only an explicit `event.properties.expired === true`
  (`type === 'incident_removed'`) sent by the canonical publisher; this is
  emitted for direct resolution and for the 7-day cutoff;
- `incident_lifecycle` remains the canonical state contract for operational
  and archive consumers: `active`, `resolved`, `needs_review`, `archived`;
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
LIVE_EDGE_HEARTBEAT_SECONDS=60
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
  "heartbeat_age_seconds": 12,
  "event_count": 1,
  "ttl_seconds": 691200
}
```

`live` is driven by the signed publisher heartbeat, independently from incident
arrival. `degraded` means the relay still has retained incidents but the
publisher heartbeat is stale. `waiting` means that no fresh heartbeat and no
retained incident are available; it does not by itself prove that the Worker is
unreachable.

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

- directly resolved markers are removed from operational Live immediately; other distress markers remain for at most `lifecycle.DISTRESS_LIVE_MAX_AGE_DAYS` (7 days), then the publisher sends an explicit removal;
- edge backstop TTL: 8 days (`LIVE_EVENT_TTL_SECONDS=691200`) â€” only matters if the publisher stops before sending the 7-day removal;
- local delivered-version registry: 48 hours;
- existing operational database: the source of truth; not deleted or rotated by this feature;
- R2/Nostr/OpenTimestamps: disabled unless a separate archival policy is explicitly approved.

## Acceptance test

1. Reset edge and local outbox.
2. Confirm snapshot contains zero events.
3. Generate one real or controlled collector observation.
4. Confirm it appears on `/v1/live/snapshot` within three seconds of DB persistence, with `properties.incident_lifecycle === "active"`.
5. Enrich its coordinates and confirm the marker is replaced (new version) rather than duplicated.
6. Post a verified same-author reply reporting resolution and confirm the publisher sends a new expired version and the marker leaves the operational snapshot.
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
