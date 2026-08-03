# Federated Live operations runbook

This runbook turns the zero-cost Live edge foundation into a reversible shadow deployment using the existing three Oracle micro instances.

## Deployment state

The architecture has four independent parts:

1. Cloudflare Worker and Durable Object distribute public events and snapshots.
2. The existing SeaCommons API and intel collectors continue to operate unchanged.
3. `core.live_edge_publisher` reads already-persisted public distress events and delivers them through a durable local SQLite outbox.
4. The existing public Live frontend remains on the Oracle-backed feed until shadow comparison is complete.

Do not switch the frontend before the edge tests, publisher delivery and snapshot freshness have been observed for at least 24 hours.

## Required Cloudflare resources

Create or bind:

- Durable Object namespace `LIVE_ROOM`;
- optional R2 bucket binding `LIVE_SNAPSHOTS`;
- Worker secret `INGEST_SECRET`;
- optional `NOSTR_BRIDGE_URL` and `NOSTR_BRIDGE_TOKEN`.

Deploy from the repository root:

```bash
cd apps/edge
npm ci
npm test
npx wrangler secret put INGEST_SECRET
npx wrangler deploy
```

Confirm:

```bash
curl https://seacommons-edge.seacommons.workers.dev/health
curl https://seacommons-edge.seacommons.workers.dev/v1/live/snapshot
```

The snapshot should return `seacommons-live-snapshot-v1`, even when it contains no events.

## Publisher configuration

Add these values to `/home/ubuntu/seacommons/.env` on the Oracle node that owns the canonical intel database:

```env
LIVE_EDGE_INGEST_URL=https://seacommons-edge.seacommons.workers.dev/v1/live/events
LIVE_EDGE_INGEST_SECRET=replace-with-the-same-cloudflare-secret
SEACOMMONS_NODE_ID=oracle-intel-01
LIVE_EDGE_OUTBOX_PATH=/home/ubuntu/seacommons/shared/live-edge-outbox.db
LIVE_EDGE_POLL_SECONDS=15
LIVE_EDGE_BATCH_SIZE=25
# Must exceed lifecycle.DISTRESS_LIVE_MAX_AGE_DAYS (3 days) with margin —
# see LIVE_FIRST_CUTOVER.md's "Realtime semantics" for why.
LIVE_EDGE_WINDOW_MINUTES=5760
LIVE_EDGE_TIMEOUT_SECONDS=12
LIVE_EDGE_MAX_ATTEMPTS=20
```

The publisher only exports:

- `distress` events;
- high-level IOM incidents treated as distress;
- records explicitly marked `publication_state=public` or `published`.

Ordinary context/news events stay private unless an operator explicitly publishes them.

## Install the systemd service

```bash
sudo mkdir -p /home/ubuntu/seacommons/shared
sudo chown ubuntu:ubuntu /home/ubuntu/seacommons/shared
sudo cp deploy/systemd/seacommons-live-edge-publisher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now seacommons-live-edge-publisher
sudo systemctl status seacommons-live-edge-publisher
```

Follow logs:

```bash
journalctl -u seacommons-live-edge-publisher -f
```

The service is constrained to 220 MB RAM, 35 percent CPU and 64 tasks. It can be disabled independently without affecting the API or collectors.

## Outbox behavior

The SQLite outbox uses WAL mode and stores:

- the last database timestamp scanned;
- pending event payloads;
- attempts and next retry time;
- the most recent delivery error.

Retries use exponential backoff capped at one hour. A delivery acknowledged with HTTP 200 or 202 is deleted from the outbox. Re-delivery is safe because the Durable Object deduplicates on event ID.

Inspect the queue:

```bash
sqlite3 /home/ubuntu/seacommons/shared/live-edge-outbox.db \
  'select event_id,attempts,last_error from pending order by created_at;'
```

Queue counts:

```bash
sqlite3 /home/ubuntu/seacommons/shared/live-edge-outbox.db \
  'select count(*) as pending, sum(attempts > 0) as retrying from pending;'
```

## Shadow verification

For 24 hours compare:

- the newest operational incident in Oracle Live;
- the newest event in `/v1/live/snapshot`;
- event IDs and source timestamps;
- coordinate confidence and radius;
- `incident_lifecycle` (active/resolved/archived) — must match the VM feed's `kind`/`incident_lifecycle` for the same incident, since both read `core/intel/lifecycle.py`;
- source URL;
- edge `updated_at` freshness.

Acceptable initial targets:

- edge propagation under 60 seconds;
- no lost public distress events;
- duplicate rate handled without visible duplicate markers;
- outbox returns to zero after temporary network interruption;
- Oracle API memory is unchanged within normal variance.

## Failure tests

### Cloudflare unavailable

Block or invalidate the edge URL for five minutes. Events must accumulate in the outbox and deliver after connectivity returns.

### Publisher restart

Restart the service while records are pending:

```bash
sudo systemctl restart seacommons-live-edge-publisher
```

Pending records must remain in SQLite.

### Duplicate delivery

Copy a pending payload and POST it twice with the same event ID and valid signature. The second response should report a duplicate and must not create another map event.

### Oracle API restart

Restarting the API or collectors must not delete edge state. The public snapshot remains available from the Durable Object/R2 path.

## Frontend cutover

Only after shadow verification, add an environment variable such as:

```env
VITE_LIVE_EDGE_BASE=https://seacommons-edge.seacommons.workers.dev
```

The frontend client should try, in this order:

1. WebSocket `/v1/live/stream`;
2. polling `/v1/live/snapshot`;
3. current Oracle `/api/v1/live` feed;
4. last local browser snapshot.

The UI must display `LIVE`, `DEGRADED`, `ARCHIVE` or `OFFLINE`, plus the last update timestamp. Keep the Oracle fallback until the edge path has completed a longer operational trial.

## Rollback

Rollback requires no database migration:

```bash
sudo systemctl disable --now seacommons-live-edge-publisher
```

Then leave or restore the frontend to the existing Oracle Live endpoint. Durable Object data and R2 snapshots can remain for later inspection or be deleted separately.

## Nostr and blockchain boundary

Nostr is an optional public replication transport, not the authoritative operational database. OpenTimestamps may later anchor periodic manifest hashes to Bitcoin. Never publish private source material, personal data or sensitive operational coordinates to immutable or uncontrolled networks.

## Remaining work before production cutover

- add the frontend edge/fallback client;
- expose publisher health and outbox age to source-health monitoring;
- add signed key rotation with overlapping secrets;
- generate periodic signed manifests;
- implement an independently hosted Nostr bridge and relay policy;
- define retention for Durable Object, R2 and public incident archives;
- complete a privacy and threat-model review.
