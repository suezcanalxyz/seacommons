# Cloudflare edge offload

The edge gateway removes environmental-feed traffic from Oracle and shields
the upstream providers with a ten-minute spatial/time cache. It never runs the
trajectory model: public simulation remains in the browser Worker.

## Responsibility split

| Component | Responsibility | Failure behaviour |
| --- | --- | --- |
| Browser Worker | 24-hour ensemble trajectory | Independent from Oracle |
| Cloudflare Worker | Normalize/cache weather and marine fields | Browser tries providers directly |
| Vercel/Pages | Static Play application | No simulation compute |
| Oracle E2 | AIS sockets, ingestion, optional OpenDrift validation | Play continues without validation |
| Future ARM 12 GB | Queue worker and larger OpenDrift jobs | Not a public critical dependency |
| Future GPU host | Unreal Pixel Streaming | UI returns to Cesium |

## Deploy the gateway

```powershell
cd apps/edge
npm install
npm test
npx wrangler login
npx wrangler deploy
```

Set the returned Worker URL in the frontend build environment:

```text
VITE_EDGE_API_BASE=https://seacommons-edge.<account>.workers.dev
```

Then rebuild/deploy `apps/web`. Configure a custom hostname such as
`edge.seacommons.org` only after the workers.dev smoke test passes.

The production `ALLOWED_ORIGINS` Worker variable must contain only the actual
Play origins. The checked-in localhost origin exists for development.

## Endpoints and cache policy

- `GET /health` reports the lightweight edge runtime.
- `GET /v1/environment?lat=...&lon=...` returns normalized current conditions
  and 72 hourly forcing frames.
- Input is sampled to 0.01 degrees, below the nominal marine product grid.
- Cache buckets last ten minutes. The immediately previous bucket can be
  returned as explicitly stale if both environmental providers fail.
- `X-SeaCommons-Cache` is `hit`, `miss`, or `stale`; stale results retain their
  original observation timestamp and must never be presented as current.

## Next storage increment

D1 and R2 are intentionally not on the simulation critical path. Add them
after account creation for shared scenario metadata and media respectively:

1. D1 stores `scenario_id`, ownership/publication state and compact JSON;
2. R2 stores images/audio using content hashes and short-lived signed uploads;
3. public reads use immutable URLs, while writes require authenticated roles;
4. the complete `scenario/v2` remains exportable and replayable without either
   service.

Do not put OpenDrift, xarray or Copernicus downloads inside a Worker. Those
belong on the Oracle/ARM queue worker.
