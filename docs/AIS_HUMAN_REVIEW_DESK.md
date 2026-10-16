# SeaCommons AIS review desk

Status: code implemented, production acceptance pending CI and rollout.

## Workflow

Futures > Intelligence > AIS cross-check provides a two-pane workstation.
Left: the current, public-eligible maritime Live cases (15s refresh), with
a selectable GeoJSON map and searchable case list.
Right: the official VesselFinder third-party widget, re-created for the
selected ship's verified IMO/MMSI. A direct IMO/MMSI input is available.
The script only runs inside an isolated, sandboxed iframe. We neither read
nor scrape its DOM, JavaScript or network responses. No automatic provider
data extraction, equivalence check or independent corroboration is claimed.

The event location and latest SeaCommons AIS fix have different meanings,
clocks and lifecycles. Both are displayed separately. A missing or stale AIS
fix must never be relabelled as a current position.

## Human evaluation contract

The reviewer selects one label for each independent dimension:
- inference quality: `supported`, `false_positive`, `inconclusive`
- position comparison: `consistent`, `inconsistent`, `unavailable`

A written rationale of at least 20 characters is required. Review storage is
append-only through the HTTP interface (`ais_case_reviews` SQLAlchemy table).
Each revision has a UUID, signed reviewer subject, UTC time, case ID, vessel
identity, case geometry and event time, actual registry AIS fix available at
submission, and explicit self-attestation of visual inspection.

No labels enter the Live public feed, the AIS source-observation lineage,
case publication decisions, the inferred event confidence, the MDA detection
thresholds, or any model training procedure. A separately approved offline
evaluation protocol must examine multiple reviewer opinions, contradictory
evidence and time-window stratification before thresholds/models change.

## Access control and deployment

The UI is within the OIDC-protected Futures workspace. Its review API is
granted to every signed-in Futures viewer. Backend verifies the provider-signed
Futures identity again and permits all authenticated Futures users to read and submit reviews.
Each entry is attributed to the signed OIDC subject. Unauthenticated
requests fail closed with HTTP 401. Do not add reviewer tokens to public source.

The new `ais_case_reviews` table is created on API startup via
`init_database` / SQLAlchemy metadata. Deploy only after CI, schema-init
verification and signed account testing. Client requires
`/api/v1/operator/ais-reviews` GET and POST to reach the same protected
origin as other operator ingestion tools. A remote API gateway must not cache
the feedback endpoint.

## Vendor and UI limitations

VesselFinder's documented embed parameters (`imo` / `mmsi` and
`show_track`) allow selecting one ship, but the provider retains control
of its own map viewport/zoom. Browser cross-origin isolation prevents
synchronizing the provider's mouse events or extracting its coordinates.
The sandbox may be blocked by the provider or content-security policy: if so,
show the official external-link alternative, not a scraped fallback.

License any machine-readable VesselFinder API integration separately,
including approval of SeaCommons' intended maritime-intelligence use.
This desk is a manual visual reference, not a licensed data feed.

## Validation gates

- unit test for identifier parsing and selection of vessel-linked Live cases
- signed-reviewer/allowlist tests, forged ID/invalid label rejection
- frozen AIS source snapshot / append-only review persistence test
- JS lint and production frontend build
- browser test selecting a Live case and verifying a newly targeted iframe
- CI completed and production test using a real authorized reviewer
- preservation of historical Play dossier geometry and isolation from AI training

## Futures gateway contract

The frontend uses `GET /api/v1/live/signals?mode=maritime` through the
existing public-only Live rewrite. A separate *signed, narrowly scoped*
`GET /api/v1/operator/ais-reviews/lookup?imo=...` or `?mmsi=...`
serves a single canonical registry vessel snapshot to Futures; full fleet
enumeration and `/api/v1/vessels/search` stay blocked at the Futures
gateway. `GET/POST /api/v1/operator/ais-reviews` are also explicitly
allowed through the proxy with a bearer, but the upstream API separately
validates the signature and reviewers-only write allowlist.
The proxy has negative allowlist tests for untrusted methods and paths.
