# SeaCommons Live audit - 2026-08-24

## Outcome

The public Live path is edge-first and does not require Oracle for its normal
incident, archive, environmental-forcing or drift flows. Oracle remains a
rate-limited incident-feed backup after three consecutive edge failures.

This document records the code and endpoint audit. Each layer becomes
production behaviour only after its Worker, publisher or web deployment.

The Worker portion was deployed on 2026-08-24 as Cloudflare version
`dfa40b37-00c3-4bf5-bc89-a4b80c0b56fb`. Immediately after deployment the
snapshot v2 reported three retained incidents (two active, one archived) and
`degraded`, as expected before rollout of the publisher heartbeat.

## Production observation before the fix

Checked on 2026-08-24 from Europe/Rome:

- `https://live.seacommons.org` returned HTTP 200;
- `https://seacommons-edge.seacommons.workers.dev/v1/live/snapshot` returned
  HTTP 200 and four retained Alarm Phone incidents;
- two incidents were archived and two were active;
- the two active incidents had no point geometry, so drawing an automatic
  drift for them would be misleading;
- `https://api.seacommons.org/health` did not answer within 12 seconds.

The edge was available, but the frontend rejected its snapshot whenever the
newest incident was older than 120 seconds. It then entered the unavailable
Oracle path. Event recency had incorrectly become a proxy for infrastructure
health.

## Implemented runtime contract

### Live

1. Load `/v1/live/snapshot` from the Cloudflare Durable Object.
2. Upgrade to `/v1/live/stream` for WebSocket updates.
3. Continue polling the snapshot every ten seconds as transport recovery.
4. Keep the last valid edge snapshot visible during a transient failure.
5. Try the Oracle signal feed only after three consecutive edge failures and
   no more than once per minute.

The Worker snapshot now includes `generated_at`, lifecycle `counts`,
`last_heartbeat_at` and per-publisher `source_health`. A signed publisher
heartbeat is independent from incident delivery. Therefore a quiet period at
sea remains `live`, while a stale publisher becomes `degraded`.

### Deriva

Only an active, recent and defensibly geolocated Alarm Phone incident is a
browser-drift candidate. Area centroids and missing coordinates are rejected.

For an eligible incident the browser:

1. requests hourly wind, current and wave frames from `/v1/environment`;
2. falls back directly to the public Open-Meteo providers if the edge
   environmental gateway is unavailable;
3. computes the trajectory in a Web Worker;
4. labels the result as a model forecast, never an observed track;
5. removes both browser and legacy server trajectories immediately when the
   incident is no longer active.

No `/api/v1/live/drifts` polling runs on the public Live host.

### Archiviati

Incident archive state is part of the same edge snapshot and uses the canonical
`incident_lifecycle` contract: `active`, `resolved`, `needs_review`,
`archived`. The dashboard separates archived incidents from operational ones.
Public Live no longer loads simulation history from the Oracle database.

## Oracle calls removed from the normal public Live path

- signal REST polling and WebSocket;
- drift polling;
- source-health polling;
- simulation-history rehydration;
- platform and NGO vessel startup requests;
- automatic nearby-vessel queries;
- server weather requests.

Operator and non-Live profiles keep their existing backend behaviour.

## Verification gates

Before deployment all of these must pass:

```text
Python test suite
Cloudflare edge unit tests
Web simulation/lifecycle unit tests
TypeScript check
Vite production build
Wrangler deployment dry-run
```

After deployment verify:

```text
GET /health                         -> 200
GET /v1/live/status                -> live with fresh heartbeat
GET /v1/live/snapshot              -> generated_at close to browser time
WS  /v1/live/stream                -> initial snapshot
Live browser network panel         -> no routine api.seacommons.org requests
active event without coordinates   -> no trajectory
active geolocated event            -> browser trajectory
archived transition                -> archive section, trajectory removed
```

## Remaining operational risks

- The canonical collectors and publisher still run on the current node and
  still read the existing database. This release removes Oracle from the
  public serving path, not yet from acquisition.
- The heartbeat becomes authoritative only after the updated publisher service
  is deployed and restarted.
- Twikit/Alarm Phone collector credentials and process state must be verified
  on the acquisition node; they cannot be inferred from the public snapshot.
- The current browser worker is the operational drift engine. The Pyodide
  kernel in development is not yet the production browser path.
- Large Cesium/MapLibre chunks remain a performance budget risk and should be
  split after the reliability cutover.

## Rollback

The cutover is reversible. Removing `VITE_LIVE_EDGE_BASE` restores the legacy
frontend path. The publisher can be stopped independently, and no database
migration is required. Do not delete the edge state during rollback: it is
useful for reconciliation and incident-lifecycle inspection.
