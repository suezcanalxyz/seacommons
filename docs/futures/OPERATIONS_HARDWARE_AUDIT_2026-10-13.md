# SeaCommons Futures: engineering incident audit and hardware expansion

Snapshot: 13 October 2026. This is a retrospective engineering register, **not a live incident feed**. A merged fix is not equivalent to verified production closure. The Futures Operations page renders the detailed issue register in `apps/web/src/futures/operationalAudit.js`.

## Runtime evidence (13 October 2026)

- Oracle API service `seacommons-api`: systemd `active`, `NRestarts=0` at the check; memory `2,391,932,928` bytes (about 2.23 GiB). Disk `/dev/sda1`: 31 GiB used of 45 GiB, 69%.
- Local canonical API on port 8100: `/ready` HTTP 200; `/api/v1/status?hours=24` HTTP 200 (1.36s); `/api/v1/live/pipeline` HTTP 200; `/api/v1/play/cache-status` HTTP 404; `/api/v1/ops/data-status` HTTP 401 without authentication, which is expected and not evidence of failure.
- `api.seacommons.org/ready` HTTP 200 at check.
- Systemd log recorded `AISStream (NGO fleet (global)) disconnected: timed out in 60.0s retry in 2s` on 13 Oct at 11:46 UTC.
- Earlier attempts against port 8000 returned connection errors; service unit actually binds to localhost port 8100. Do not count the port-8000 probe as an outage.

## Risk register and closure policy

1. **P0 passenger/ferry/HSC classification**: historical LIVE false positives and partial fixes. Recheck every ingest/cache/overlay/publication path with adversarial vessel classes and regex boundary cases.
2. **P0 recurring disk and DB pressure**: repeated service interruptions and weekly cleanup. Disk at 69% does not indicate a present disk outage, but no verified quota/retention and recovery SLO was observed.
3. **P1 AIS disconnects**: source-health, reconnection and authorized fallback; verify station-specific freshness and degraded-mode alerting.
4. **P1 PLAY archive/cache**: stale or incomplete dossiers, ID/geometry errors, missing cache-health endpoint; verify archive completeness and contract parity.
5. **P1 scheduler contention**: darkship cue overlap, cold-cache retained-history scans and long jobs; verify distributed single-flight, timeouts and resource limits.
6. **P0 evidence overstatement**: AIS nav-status false positives, gap-based dark-vessel attribution and lineage independence; test counter-evidence and publication gates.
7. **P1 humanitarian geolocation/drift**: OCR provenance, region-only and land geometry, translated duplicates, resolved incident lifecycle.
8. **P2 radio reliability**: receiver offline history, DSC/NAVTEX decode rates and receiver telemetry; test before adding more stations.
9. **P1 Futures auth and metrics**: mobile OIDC renewal, dashboard host routing and period-switch races; verify with end-to-end tests.
10. **P2 release/edge**: edge/VM version drift, browser E2E and Vercel deployment failures; require revision parity and smoke tests.

**Closing an issue** requires: linked patch or configuration change, deployed runtime revision, before/after observation, regression test, and 24–72h observation window as appropriate. Do not infer closure from a successful build or merge.

## Hardware strategy

A proposed network of open-source-friendly hardware and partner sites: receive-only AIS stations; receive-only VHF/DSC/NAVTEX SDR stations; GNSS-tracked solar drifter buoys with temperature, pressure, IMU and optional hydrophone; coastal weather/tide sensors; field validation kits; donated compute/storage/connectivity. All sensors must emit timestamp, location/uncertainty, station ID, health, calibration/version and provenance. Ingest must keep raw observation separate from claims and independent corroboration.

### Phase 1: prove ingestion and stewardship

Select 1–2 legally authorized coastal AIS sites, one radio receiver with structured decode, and one donated compute/storage partner. Provide installation instructions, remote health checks, edge buffering, signed source identity, uptime reports, operator runbooks and a clear revocation/maintenance plan. Do not confuse Volpedo development tests with permanent coastal AIS coverage.

### Phase 2: drifter and environmental pilots

Prototype one recoverable buoy with GNSS, solar battery, LoRa where gateway coverage exists and cellular/satellite as feasible. Evaluate drogue, mooring/marking and navigation safety, retrieval and marine pollution risk. Test data latency, location uncertainty and OpenDrift validation. Add hydrophones only after acoustic research and privacy approvals.

### Phase 3: repeatable network

Publish open firmware and schemas, calibration and field installation guides, public-safe station health, and partnership onboarding. Replicate sites only after reliable maintenance, security and operational utility have been demonstrated. Track hardware uptime and data quality separately from case outcomes.

### Partner contributions

Host an antenna or receiver; donate SDRs, marine antennas, filters, GNSS modules, low-power computers, batteries, solar hardware, environmental sensors, hydrophones or rugged enclosures; provide safe deployment/retrieval vessels; maintain receivers; contribute open-source firmware, radio decoding, calibration, field engineering, connectivity, VM/storage and backups. Every partner arrangement should define equipment ownership, custody, permitted radio use, environmental permissions, security, maintenance, and publication rights. No implied authorization to transmit on maritime frequencies or monitor restricted communications.
