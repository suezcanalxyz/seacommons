# SeaCommons maritime attack correlation — source-faithful identity linkage audit

Date: 2026-11-01 ~13:26 UTC. Branch: `feature/maritime-attack-correlation-20261030`.
Baseline: `58dc33e0`. Staging only. No production deployment, data mutation, new VM cron/timer/loop, or new recurring automation.

## Verified implementation

The Bulgarian Ministry of Defence bulletin `BG_MOD:news9664` names **CONTSHIP JET** and reports an attack at 12:00 Bulgarian local time on 28 October (10:00 UTC), but its public text does **not** print IMO 9348625 or MMSI 636019532: https://www.mod.bg/news9664 .

Previously, synthetic staging fixtures included those identifiers *inside* a simulated primary bulletin, risking incorrect provenance if the fixture were treated as an actual extraction. The new `maritime_attack_identity_evidence.py` provides a separate, explicitly reviewed external-identity assertion; `test_maritime_attack_identity_evidence.py` now exercises a source-faithful original bulletin with empty IMO/MMSI and a separately labeled **synthetic** registry record. No real registry URL or identity-verification source is claimed by that synthetic test.

`link_external_vessel_identity` checks source-record IDs, distinct HTTPS source URLs, matching ship names, IMO checksum, MMSI validity, explicit reviewer, receipt/publication clocks, conflicting external IDs and any IDs actually printed in the original. It returns `linked_for_review` or `blocked`; it **never** rewrites `OfficialMaritimeBulletin`, modifies `SourceObservation`, counts as a second attack witness, or allows publication. Contradictory and unreviewed enrichments fail closed. The existing `claim_from_source_observation` continues to reject injecting external IDs into an original bulletin extraction.

Six new identity tests cover original-source fidelity, successful isolated identity linkage, unreviewed/same-source/invalid URLs, name and ID mismatch, conflicting/duplicate evidence, and impossible publication clocks. The existing CI workflow was extended to trigger on the two new files; no new workflow or scheduler was created.

Commits:
- `fd612d426b04bc964a40679971f03eb7c04ee56c` — identity linkage module.
- `390bffc7b101034d0c76820121ba0c7d55720daf` — six source-faithful regressions.
- `c7c859fec493e247b3877339d6523c9bc3456e5f` — existing CI workflow path coverage.

GitHub Actions: https://github.com/suezcanalxyz/seacommons/actions/runs/41311296996 . **Success** on functional head `58393189`, completed 2026-11-01 13:27:31 UTC. Logs: 303 maritime Python tests + 19 bulletin tests + 3 SQLite + 6 isolated PostgreSQL = **331 Python tests PASS**. Frontend 5/5 PASS; Vite build PASS. These certify staging behavior, not Oracle data correctness or LIVE/PLAY promotion.

## Read-only production observations

At ~13:25–13:26 UTC, authorized remote device `instance-20260828-1159` requested public endpoints (HTTP 200):
- `https://play.seacommons.org/api/v1/play/counts`: **3,570** total, 3,442 maritime, 128 humanitarian; `generated_at=2026-11-01T12:20:11Z`.
- `https://play.seacommons.org/api/v1/play/incidents?limit=1`: **3,572** total; `generated_at=2026-11-01T13:25:06Z`.
- `https://live.seacommons.org/api/v1/live/pipeline`: generated 2026-11-01T13:26:02Z; two sources degraded and three live.

The 2-item PLAY discrepancy compares caches **~65 minutes apart**, not a synchronized snapshot. Do not infer data loss or a confirmed projection bug from this alone. Attack-specific LIVE/PLAY promotion remains unverified.

The permitted local PostgreSQL attempt `PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=3000' psql -X -Atqc 'SHOW transaction_read_only'` returned `FATAL: role "ubuntu" does not exist`. No alternate role, privilege escalation, or credential extraction was attempted. **Zero new Oracle SQL rows or table counts certified** this run. Required checks remain `intel_events`, `vessel_tracks`, `alert_events`, `anomaly_events`, `humanitarian_incidents`, `forensic_events`, `source_observations`, `maritime_episodes`.

Proposed authorized SQL, **not executed**:
```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '6000ms';
SELECT id, mmsi, ts, received_at, sog, lat, lon
FROM vessel_tracks
WHERE mmsi = '636019532'
  AND ts BETWEEN '2026-10-28 09:30:00' AND '2026-10-28 11:30:00'
ORDER BY ts, id LIMIT 257;
SELECT count(*) FROM intel_events WHERE created_at >= now() - interval '72 hours';
SELECT count(*) FROM alert_events WHERE created_at >= now() - interval '72 hours';
SELECT count(*) FROM anomaly_events WHERE created_at >= now() - interval '72 hours';
SELECT count(*) FROM humanitarian_incidents WHERE updated_at >= now() - interval '72 hours';
SELECT count(*) FROM forensic_events WHERE created_at >= now() - interval '72 hours';
SELECT count(*) FROM maritime_episodes WHERE created_at >= now() - interval '72 hours';
SELECT count(*) FROM source_observations
WHERE received_at >= '2026-10-01'
  AND (observation_type = 'official_maritime_bulletin'
       OR source_name ~* '(MSCIO|UKMTO|NAVAREA|NAVWARN|Bulgarian Ministry|MARAD|GDELT)');
ROLLBACK;
```

## Documentary candidates and lineage warnings

- **CONTSHIP JET** — 28 October 10:00 UTC, Black Sea; Bulgarian MOD source https://www.mod.bg/news9664 . IMO `9348625`, MMSI `636019532` remain **external identity references requiring source-specific provenance**; AIS speed change is context only. The Bulgarian Prosecutor Office itself published a 29 October procedural investigation notice: https://prb.bg/bg/news/aktualno/80101-voenno-okrazhna-prokuratura-sofiya-obrazuva-dosadebno-proizvodstvo-za-napadeniet . This is a separate procedural development, **not automatically an independent eyewitness**; possible dependence on the military-police report must be traced.
- **MSCIO 158/26** — 29 October 16:00 UTC, Hormuz, unknown tanker/IMO: https://mscio.eu/alerts/194 .
- **MSCIO 159/26** — 29 October 22:12 UTC, Hormuz, unknown tanker/IMO: https://mscio.eu/alerts/195 . Reuters reported the candidate name LOUISE 1 based on security sources (29/30 October reporting): https://www.reuters.com/world/tanker-strait-hormuz-hit-by-limpet-mines-security-sources-say-2026-10-30/ . Do **not** merge or promote without checking exact vessel identifiers, origin independence and incident geometry.
- **MSCIO 161/26** — AZINI fishing vessel hijacking reported 29 October ~09:00 UTC off Somalia; last reported position on 30 October is not necessarily the hijack site: https://mscio.eu/alerts/197 .
- **MSCIO 163/26** — published 30 October, incident date 28 October, Hormuz: https://mscio.eu/alerts/199 . Preserve event/publication separation.
- **MARAD 2026-012** — active Black Sea/Sea of Azov risk advisory, not an individual attack observation: https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations .

Public access does not imply unrestricted automated republication. Check publisher-specific reuse rights and upstream syndication before import. MSCIO/UKMTO copies cannot automatically count as independent origins. No attacker attribution.

## Next gates

1. Find a **permitted** read-only Oracle PostgreSQL role; verify CONTSHIP JET `received_at`, actual AIS integrity and October official-source gaps.
2. Obtain a real, license-compatible IMO/MMSI source record with URL, publication and receipt clocks; replace the synthetic identity fixture **only in a separately documented integration test**, not by rewriting the ministry report.
3. Test original bulletin + external vessel identity + AIS context on isolated staging, including duplicate and conflict negatives.
4. Certify reviewed PLAY -> incident, attack category/color distinct from humanitarian drift, snapshot freshness and source-independence gate.
5. Production deploy only after explicit approval.

## Additional primary-source adapter gate

The official Bulgarian Prosecutor Office notice (29 October 2026) confirms a pre-trial investigation referred by the Varna Military Police. The source is available at https://prb.bg/bg/news/aktualno/80101-voenno-okrazhna-prokuratura-sofiya-obrazuva-dosadebno-proizvodstvo-za-napadeniet . The staging bulletin adapter now permits issuer `BG_PROSECUTOR` only on `prb.bg`/`www.prb.bg`, with a distinct `investigation` kind. Its canonical observation retains publication-date semantics, no invented exact incident clock or IMO/MMSI, and `attack_corroboration_allowed=False`. The new regression asserts that even an extracted `attack` cannot reclassify this procedural document. This is a separate publication but **not automatically a second independent attack witness**.
