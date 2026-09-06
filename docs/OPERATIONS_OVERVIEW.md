# Operations overview — what it takes to run SeaCommons

Status: canonical operations reference. Last reviewed: 2026-09-06.

This is the ground-truth picture of the running system: the real data that
flows in, what each source costs, the compute footprint, and where it
breaks under load. `GET /api/v1/ops/data-status` returns the live version of
most of this.

## Deployable pieces and where they run

| Piece | Host | Cost |
| --- | --- | --- |
| Institutional site + console (`apps/web`) | Vercel static + serverless `/api` proxy | Free tier |
| Operational API + monitors + scheduler (`apps/api`) | Oracle Cloud "Always Free" VM (1 GB), systemd + uvicorn | Free |
| Public demo API | same VM, second service (port 8101, 320 MB cap) | Free |
| Public Live edge (`apps/edge`) | Cloudflare Worker + Durable Object | Free tier |
| Live edge publisher (`core.live_edge_publisher`) | same VM, systemd | Free |
| Object storage (attachments) | S3 / MinIO | per use |
| Database | PostgreSQL (SQLite for dev) | per use |

Production currently runs the API, monitors, scheduler, drift engine and
edge publisher **on one 1 GB VM**. `JOB_EXECUTION_MODE=inline` — drift runs
in the API process. This is the binding constraint (see Compute below).

## Ingested data sources

| Source | What it gives | Auth | Cost / limit | Failure behaviour |
| --- | --- | --- | --- | --- |
| **AISStream** (`wss://stream.aisstream.io`) | live vessel positions + nav status | free API key | **one open socket per key** | reconnect/backoff; stall detector; source-health tracking |
| **Open Waters / aiscast** (`wss://ais.openwaters.io/v1/stream`) | free/open-first second AIS transport with upstream source/station provenance | anonymous for bounded subscriptions | anonymous limits: bounded area/MMSI/message-rate; not whole-Mediterranean parity | disabled by default; used first in `shadow`; reconnect/backoff and shared provider health |
| AISStream NGO key (optional) | a second global socket tracking the SAR fleet by MMSI | a **separate** free key | as above | skipped if unset |
| **CMEMS / Copernicus Marine** | ocean current field (0.083°) for drift | free account (`CMEMS_USERNAME`/`PASSWORD`) | rate-limited; `open_dataset` ~25 s | 90 s timeout → Open-Meteo grid fallback → zero-current (flagged `degraded`) |
| **Open-Meteo** forecast + marine | gridded wind, currents, waves for drift; also the browser drift engine | none | 10 000 calls/day soft | drift falls to constant forcing (flagged `degraded`) |
| **twikit** (X via a real account session) | Alarm Phone + NGO distress posts, incl. the map-screenshot coordinates | cookies file, opt-in | tiered polling to protect the account | monitor stays disabled without a usable cookies file |
| X official API | secondary X channel | paid Basic+ tier | metered, can 402 | optional; the distress feed does not depend on it |
| **News / RSS** monitor | NGO articles, IOM Missing Migrants | none | 30 min refresh | degrades to last cache |
| **GDACS** | disaster / maritime alerts | none | hourly-ish | optional |
| **Image OCR** (tesseract + Pillow) | coordinates and drop-pins from Alarm Phone map screenshots | host binary | local CPU | **silently off if `tesseract` is not installed** — see `ops/summary.image_ocr` |
| Meta WhatsApp / Telegram / partner webhooks | inbound operator and partner reports | per-channel secrets | free | fail closed without verification config |

AIS consumers now sit behind a compatibility-preserving normalized layer. In `legacy`, AISStream remains exactly authoritative. In `shadow`, aiscast is compared without canonical writes. In `fused`, accepted reconciled fixes feed the same downstream consumers: vessel registry/track history, AIS spikes, vessel incidents, anomaly/MDA scans, SourceObservation sampling, and SAR response analysis.

Provider count is not evidence independence. `aiscast(source=aisstream)` collapses to the AISStream upstream lineage. Provider/station health is used to distinguish likely vessel silence from reception/provider degradation, while the existing neighbour-based gap classifier remains authoritative.


### AIS fusion rollout / rollback

Configuration is intentionally staged:

- `AIS_FUSION_MODE=legacy` — historical AISStream canonical path; aiscast not started.
- `AIS_FUSION_MODE=shadow` + `AISCAST_ENABLED=true` — aiscast/reconciliation/metrics run, but AISStream still owns canonical writes.
- `AIS_FUSION_MODE=fused` — accepted reconciled fixes own canonical AIS writes.

Rollback is configuration-only: return to `AIS_FUSION_MODE=legacy`. No database rollback is required by Free/Open AIS Fusion v1. Open Waters transport software licensing does not override per-upstream AIS data terms; event-level upstream/source terms must remain attached to provenance.

### Humanitarian verification operations

Humanitarian source roles are policy-driven: Alarm Phone is `operational_origin`; operational SAR NGOs are `verification`; IOM Missing Migrants is `archive_reference`. Verification sources never open a new Humanitarian incident by default. They can add deterministic claims and association decisions to an existing Alarm Phone incident when matching evidence is strong enough.

Tracked X handles such as `SOSMedIntl`, `openarms_fund`, `seawatchcrew`, `SOShumanity`, `seaeyeorg`, `ResQship` and `emergency_ong` normalize to organization-level verification identities before transport/lineage reasoning. Verification posts with no deterministic Humanitarian claim stop before correlation.

Derived state is stored in existing `ClaimDB`, `CorrelationDecisionDB` and `AssessmentDB`; no new schema migration is required by Humanitarian Verification v1. `sar_mission` and `resolution` assessments are replayable derived evidence, not a second canonical lifecycle. Automatic lifecycle resolution remains disabled.

Operator-safe verification state is available at `GET /api/v1/audit/humanitarian-verification/{incident_id}`. Metrics use only bounded semantic labels (`stage`, `source_role`, `outcome`) and never MMSI, IMO, callsign, station/message IDs, email addresses or source text.

## Compute footprint

| Cost centre | Reality |
| --- | --- |
| OpenDrift import | ~50 s cold; done once in a background thread at startup (`prewarm`) |
| One drift run | seconds to tens of seconds; **one at a time** — `_drift_semaphore` is a single slot |
| CMEMS slice download | ~seconds, cached per 0.5° cell + cycle |
| Drift memory | ~600 MB headroom needed; the scheduler **skips queuing a drift when `MemAvailable < 400 MB`** and queues at most one per 15 min run |
| AIS hooks | microseconds per message; ~500–1800 msg/s peak → a few ms/s of hook time |
| Intel monitor memory | bounded — the AIS anomaly detector and vessel-incident monitor prune per-vessel state on a cadence |
| API process cap | `MemoryMax=650M` (systemd); demo API `320M` |

**What this means:** on the current VM, "run a drift for every active
incident" is throughput-limited to roughly one every 15–20 minutes when
memory is tight. Backfilling history or a busy day both need the ARM 12 GB
worker (`JOB_EXECUTION_MODE=queue`, `python -m core.worker`).

## What to check when something looks wrong

`GET /api/v1/ops/data-status` and `GET /api/v1/ops/summary`:

- `ingestion.ais.connected` false → AIS feed down (check VM logs for
  reconnect loop)
- `ingestion.image_ocr.available` false → install `tesseract-ocr` on the VM;
  every map-screenshot coordinate is being lost until then
- `ingestion.monitors` all false with `monitors_enabled: true` → the intel
  engine failed to start
- `drift.by_status.failed` climbing, `drift.recent_forcing_quality` all
  `degraded-constant` → CMEMS + Open-Meteo both unreachable
- `compute.available_ram_mb` low and `drift.engine.queue_depth` > 0 → the
  single drift slot is the bottleneck; the ARM worker is the fix
- `intel_record.events_last_24h` at 0 during an active period → a monitor
  stalled

## Scaling path

1. **ARM 12 GB worker** (Oracle Ampere A1, still free): move drift to
   `JOB_EXECUTION_MODE=queue` + `core.worker`, raise the OpenDrift slot
   count and particle count, unblock the backfill and daily-analysis modes.
2. **Postgres off the API VM** so the 1 GB VM is just the API + monitors.
3. **Gridded GFS wind** (Phase 15c) from the NODD AWS S3 bucket — adds one
   more cache-per-cell download to the drift path.

## Related documents

- [Architecture](ARCHITECTURE.md) · [Deployment](DEPLOYMENT.md) ·
  [Configuration](CONFIGURATION.md) · [Realtime architecture](REALTIME_ARCHITECTURE.md)
- [Production runbook](PRODUCTION_RUNBOOK.md) — procedures and commands
