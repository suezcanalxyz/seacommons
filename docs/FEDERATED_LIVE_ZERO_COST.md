# SeaCommons Federated Live — Zero-Cost Architecture

Status: initial implementation proposal and deployable edge foundation.

## Objective

Keep `live.seacommons.org` responsive when the three Oracle E2.1.Micro collectors are slow, restarting, or temporarily unavailable, without introducing a paid server or making a blockchain the primary database.

The design treats Oracle as a set of replaceable collectors and Cloudflare as the public realtime edge. All protocols, schemas and adapters remain open source and exportable.

## What this change adds

- `SeaCommons Event v1`, a versioned public event contract.
- HMAC-authenticated ingestion from trusted collectors.
- A Cloudflare Durable Object acting as the Live room.
- WebSocket broadcast for browser clients.
- An HTTP snapshot fallback for degraded clients.
- Append-only hash chaining between accepted events.
- Deduplication by event ID.
- Optional snapshot writes to an R2 binding.
- Optional forwarding to a Nostr bridge.
- Tests for normalization and request authentication.

## Architecture

```text
Oracle collector 1 ─┐
Oracle collector 2 ─┼─ signed HTTPS events ─► Cloudflare Worker
Oracle collector 3 ─┘                              │
                                                   ▼
                                      Durable Object LiveRoom
                                      ├─ deduplicate
                                      ├─ append hash chain
                                      ├─ store recent events
                                      ├─ WebSocket broadcast
                                      ├─ HTTP snapshot
                                      ├─ optional R2 snapshot
                                      └─ optional Nostr bridge
```

The public browser connects to Cloudflare rather than directly to Oracle.

```text
primary:   WebSocket /v1/live/stream
fallback:  GET /v1/live/snapshot
archive:   R2/IPFS snapshot, when configured
replica:   Nostr relays, when configured
```

## Why blockchain is not the Live database

A public blockchain is unsuitable for continuous maritime observations because it introduces fees, latency, irreversible publication and privacy problems. SeaCommons should use cryptographic signatures and content hashes for each event, then periodically timestamp a Merkle root or manifest.

Recommended integrity layers:

1. event signature at the collector;
2. hash chain in the Live room;
3. signed daily manifest;
4. optional OpenTimestamps anchoring;
5. optional IPFS CID for public snapshots.

Only aggregate hashes should be anchored. Coordinates, personal data and operational messages must not be written to a public blockchain.

## Event contract

Source schema:

```text
docs/contracts/seacommons-event-v1.schema.json
```

Minimal collector payload:

```json
{
  "type": "distress_observation",
  "source": "alarm-phone",
  "node": "oracle-collector-1",
  "observed_at": "2026-08-02T16:30:00Z",
  "visibility": "public",
  "confidence": 0.72,
  "geometry": {
    "type": "Point",
    "coordinates": [14.52, 35.71]
  },
  "properties": {
    "persons": 37,
    "status": "active"
  },
  "source_url": "https://example.org/source"
}
```

The edge adds:

- `schema`;
- `received_at`;
- `previous_hash`;
- deterministic `id` when absent;
- `hash`.

Private events are rejected by the public Live endpoint. Private partner ingestion must continue through the authenticated Engine/API path.

## Collector authentication

Each request body is signed with HMAC-SHA256 using `INGEST_SECRET`.

Header:

```text
X-SeaCommons-Signature: <hex hmac sha256 of the exact request body>
```

Python example:

```python
import hashlib
import hmac
import json
import requests

payload = {
    "type": "source_health",
    "source": "alarm-phone",
    "node": "oracle-collector-1",
    "observed_at": "2026-08-02T16:30:00Z",
    "visibility": "public",
    "properties": {"status": "healthy"},
}
body = json.dumps(payload, separators=(",", ":")).encode()
signature = hmac.new(INGEST_SECRET.encode(), body, hashlib.sha256).hexdigest()
requests.post(
    "https://seacommons-edge.seacommons.workers.dev/v1/live/events",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-SeaCommons-Signature": signature,
    },
    timeout=10,
)
```

For a later federation phase, replace the shared collector secret with per-node Ed25519 public keys. The event schema is intentionally independent from the transport authentication method.

## Cloudflare deployment

From `apps/edge`:

```bash
npm ci
npm test
npx wrangler secret put INGEST_SECRET
npm run deploy
```

The Durable Object binding and SQLite migration are included in `wrangler.jsonc`.

### Optional R2 snapshots

Create a bucket and add a binding named `LIVE_SNAPSHOTS`:

```jsonc
"r2_buckets": [
  { "binding": "LIVE_SNAPSHOTS", "bucket_name": "seacommons-live" }
]
```

The latest snapshot is written to:

```text
live/latest.json
```

R2 is optional. Durable Object storage remains the primary state for this first implementation.

### Optional Nostr replication

The Worker does not store a Nostr private key. Instead it can forward accepted public events to a small open-source bridge that signs and publishes them to configured relays.

Set:

```text
NOSTR_BRIDGE_URL=https://nostr-bridge.example/v1/events
NOSTR_BRIDGE_TOKEN=<secret>
```

Recommended bridge behavior:

- accept only SeaCommons Event v1;
- sign with a dedicated SeaCommons Nostr key;
- publish to at least three relays;
- map events to an addressable application-specific kind;
- retain the original SeaCommons event hash in tags;
- never publish private events.

The bridge is optional and failures do not block Live ingestion.

## Browser integration

Primary connection:

```javascript
const socket = new WebSocket('wss://seacommons-edge.seacommons.workers.dev/v1/live/stream');
socket.onmessage = ({ data }) => {
  const message = JSON.parse(data);
  if (message.type === 'snapshot') replaceLiveState(message.events);
  if (message.type === 'event') applyLiveEvent(message.event);
};
```

Fallback:

```javascript
const snapshot = await fetch(
  'https://seacommons-edge.seacommons.workers.dev/v1/live/snapshot'
).then((response) => response.json());
```

The interface should expose four states:

- `LIVE`: WebSocket connected and recent event received;
- `DEGRADED`: polling snapshot works but WebSocket is unavailable;
- `ARCHIVE`: only an R2/IPFS snapshot is available;
- `OFFLINE`: no source is reachable.

Always display `updated_at` and never imply realtime status when serving an old snapshot.

## Role of the three Oracle micro instances

### Node 1 — Alarm Phone

- Alarm Phone monitor;
- local SQLite queue;
- signed event publisher;
- no public browser traffic.

### Node 2 — public intelligence

- GDACS, Bluesky and Mastodon collectors;
- local SQLite queue;
- signed event publisher;
- optional Nostr relay or IPFS pinning.

### Node 3 — AIS and maintenance

- selected AIS state and nearest-vessel events;
- source-health aggregation;
- snapshot/hash-manifest job;
- no full AIS stream forwarded to Cloudflare.

Each collector must keep an outbox and retry accepted public events after network failure. A failed Cloudflare request must not discard the source observation.

## AIS publication rules

Do not emit every AIS position. Emit only meaningful state changes:

- vessel enters or leaves a distress radius;
- movement exceeds a configurable distance;
- heading changes beyond a threshold;
- asset status changes;
- a fresh position replaces stale state;
- rescue-pattern correlation changes.

This protects free quotas and avoids implying complete AIS coverage.

## Retention

The initial Durable Object keeps the latest 500 events. Long-term history should be exported as immutable snapshots:

```text
live/YYYY/MM/DD/HH-mm.json
manifests/YYYY/MM/DD.json
```

Recommended later formats:

- JSONL for append-only source records;
- GeoParquet for analysis;
- signed JSON manifests for provenance;
- IPFS CIDs for public replication.

## Security limitations of this first version

The first implementation uses one shared HMAC secret. It is appropriate for the three controlled Oracle nodes but not yet for arbitrary third-party nodes.

Before onboarding external partners:

- introduce per-node keys;
- maintain a key registry and revocation list;
- apply per-node rate limits;
- validate event schemas strictly;
- restrict coordinate precision by publication policy;
- strip sensitive fields before public ingestion;
- record publication decisions in Engine;
- implement replay windows and nonce tracking.

The public edge must never become the route for private WhatsApp, Telegram, SMS or partner messages.

## Migration sequence

1. Deploy the new edge Worker with `INGEST_SECRET`.
2. Test `/health` and `/v1/live/snapshot`.
3. Add one collector publisher in shadow mode.
4. Compare edge events with the existing Oracle Live endpoint.
5. Connect the frontend WebSocket behind a feature flag.
6. Enable snapshot polling fallback.
7. Move public browser reads away from Oracle.
8. Add local collector outboxes and retries.
9. Add R2 snapshots.
10. Add the optional Nostr bridge and relay fallback.
11. Generate signed daily manifests.
12. Add OpenTimestamps only after the manifest format stabilizes.

## Operational acceptance checks

The change is ready for public rollout when:

- a collector can publish a valid signed event;
- invalid signatures are rejected;
- duplicate IDs do not produce duplicate broadcasts;
- two simultaneous browsers receive the same event;
- snapshot state survives a Worker restart;
- Live remains visible when all Oracle nodes are stopped;
- a collector outbox delivers queued events after reconnection;
- private events cannot enter the public room;
- the UI labels stale snapshots as degraded/archive;
- the old Oracle endpoint remains available during rollback.

## Rollback

The implementation is additive. To roll back:

- point the frontend back to the current `/api/v1/live` endpoint;
- stop collector publishing;
- leave the Durable Object data untouched for later inspection.

No migration of the operational database is required by this change.

## Follow-up implementation work

- Python collector publisher and durable SQLite outbox;
- frontend WebSocket client with fallback state machine;
- Ed25519 per-node authentication;
- standalone Nostr bridge;
- signed hourly/daily manifests;
- R2 and IPFS archive adapter;
- optional OpenTimestamps workflow;
- source-specific publication and coordinate-redaction policies.
