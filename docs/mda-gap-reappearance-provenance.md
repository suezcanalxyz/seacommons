# AIS gap closure provenance gate (pilot)

`MdaWatch._resolve_reappeared_gaps()` previously closed a gap when the newest
`vessel_tracks` timestamp for the same MMSI was after the estimated original
last fix. This could be the *same* delayed AIS position that generated the gap,
or a spoofed/unverified report. It also wrote `gap_reappearance_confirmed`
without an identity or source validation decision.

The detector now fails closed. A newer track row alone is never a validated
reappearance. The IntelEvent metadata must contain a `reappearance_validation`
object with explicit `identity_validated: true` and `source_validated: true`
plus `track_id`, `mmsi`, `source`, and UTC `observed_at` bound to the exact
persisted row. The fix must be after the emitted gap report. A successful
closure records both decisions and its UTC last fix, and may close the
corresponding persisted episode. Otherwise the original case stays open;
its last known AIS position is not updated to an unverified reappearance.

**Not yet implemented:** a trustworthy producer for these validation decisions.
Neither a matching MMSI nor an `aisstream` source label authenticates a ship's
identity or a radio transmission. Do not backfill the booleans from raw track
rows, from prior alert validation, or from a simple speed/distance heuristic.
The producer must capture evidence provenance and a separately reviewable
identity/source validation result tied to the exact track row. Until then,
no automatic gap closures are expected. This conservative behavior is
intentional and must be visible in the operational monitoring dashboard.

Regression tests use disposable in-memory SQLite only; no production
observations or incidents are manufactured.
