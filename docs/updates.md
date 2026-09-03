# SeaCommons — Post-Stabilization Geospatial & Data Intelligence Upgrade Plan

> **Execution order:** `docs/fixes.md` remains authoritative until fully completed. Do not start this plan while any required `fixes.md` milestone, migration, replay, integration, privacy, CI, or production verification gate is still open.
>
> **Purpose:** raise SeaCommons from a stabilized maritime OSINT application to a production-grade geospatial data-intelligence infrastructure without accumulating another layer of legacy. This document is a migration program, not a feature wishlist.

---

# 0. Operating principle

Every milestone in this document must do at least one of the following:

1. remove an existing architectural limitation;
2. replace duplicated or ad-hoc logic with a canonical subsystem;
3. improve correctness, observability, performance, replayability, privacy, or interoperability in a measurable way;
4. delete legacy code or create an explicit and testable deletion path for it.

A new dependency, service, schema, abstraction, compatibility field, dual-write path, or fallback is not progress by itself.

**Hard rule:** every new subsystem must either replace, simplify, or measurably improve an existing path. Do not leave the previous path alive indefinitely.

---

# 1. Preconditions — `fixes.md` must be closed first

Before starting M0 below, the agent must prove all of the following on the exact `main` commit it intends to use as the upgrade baseline:

- every required milestone in `docs/fixes.md` is complete;
- backend full suite green;
- lint/typecheck/build green where applicable;
- DB migrations tested on PostgreSQL and SQLite-compatible test paths where retained;
- deterministic replay gates green;
- Humanitarian and Maritime live/public projections verified;
- privacy contracts verified;
- no unresolved P0/P1 stabilization defect remains hidden behind a skipped test, fallback, mock-only path, or compatibility branch;
- latest production verification is documented.

If any of those fail, return to `fixes.md`. Do not use this document as an excuse to bypass stabilization work.

---

# 2. Mandatory agent execution protocol

Every milestone must follow this loop:

```text
1. sync main
2. read docs/fixes.md and confirm it remains closed
3. read docs/updates.md
4. inspect current implementation before proposing edits
5. identify the exact legacy path being replaced or retained
6. write failing tests / migration tests / replay fixtures first
7. implement the smallest coherent vertical slice
8. run targeted tests
9. run the full relevant suites
10. measure query/performance impact when DB or map delivery changes
11. self-review for duplicate logic, compatibility leftovers and dead code
12. document what became canonical
13. document what legacy code was removed
14. document any temporary compatibility code and its deletion milestone
15. open one reviewable PR
16. merge only after green CI and explicit exit-gate evidence
17. update main and continue with the next dependency-ready milestone
```

For every PR, the agent must include this table in the PR description:

```text
Existing implementation:
Target implementation:
Legacy removed in this PR:
Temporary compatibility retained:
Compatibility deletion milestone:
Files touched:
Tests proving parity/correctness:
Migration/replay evidence:
Known limitations:
```

A milestone is not DONE if the new system exists but the previous authoritative path still silently controls production behaviour.

---

# 3. Global non-negotiable constraints

1. PostGIS does not replace evidence semantics, provenance, confidence, review or publication policy.
2. Spatial SQL performs retrieval, geometry operations and candidate generation; domain reasoning remains explicit and testable.
3. Raw, reported, derived, uncertainty and public geometries must remain distinguishable.
4. No inferred geometry may be presented as a reported position.
5. Humanitarian privacy constraints take precedence over analytical convenience.
6. Do not expose exact vulnerable-person locations merely because the canonical datastore contains them.
7. Never destroy original source geometry when producing corrected, snapped, generalized or public geometry.
8. Every derived geometry carries method/version/input provenance.
9. Every imported geospatial dataset records source, version/date, licence/terms and import version.
10. Unknown CRS is a validation failure, not an invitation to guess.
11. Never assume EPSG:4326 without explicit source knowledge.
12. No new spatial dependency enters production without deterministic tests.
13. No speculative index. Every non-trivial production index must correspond to a documented query path or measured plan.
14. No large GIS dataset is hardcoded in Python when it can be versioned as data.
15. No technology is added solely to match a job description or improve keyword coverage.
16. Every compatibility layer has an explicit removal milestone.
17. `legacy`, `deprecated`, `compat`, `fallback`, duplicate geometry helpers and obsolete schema fields are release-review targets, not permanent architecture.

---

# 4. Target architecture

Long-term data flow:

```text
SOURCE / SENSOR / DATASET
        ↓
CANONICAL OBSERVATION + PROVENANCE
        ↓
GEOSPATIAL NORMALIZATION
        ↓
REPORTED / DERIVED / UNCERTAINTY GEOMETRY
        ↓
SPATIAL + TEMPORAL CANDIDATE RETRIEVAL
        ↓
DOMAIN CORRELATION / INTELLIGENCE LOGIC
        ↓
INCIDENT / EPISODE / ASSESSMENT
        ↓
PRIVACY-AWARE PUBLIC GEOMETRY
        ↓
REST / WS / VECTOR TILE / GIS EXPORT
```

Canonical vector storage target:

```text
PostgreSQL + PostGIS
        ↑
GeoAlchemy2
        ↑
Python domain services
        ↔ Shapely / PyProj
```

Raster target where required:

```text
source raster / model output
        ↓
GDAL / xarray normalization
        ↓
Cloud Optimized GeoTIFF or equivalent object-storage artifact
        ↓
rio-tiler / TiTiler only when justified
        ↓
MapLibre / Cesium / analyst tooling
```

Do not store large raster archives in PostgreSQL by default.

---

# 5. M0 — Legacy eradication and architecture census

**Goal:** establish exactly what must disappear before new GIS infrastructure becomes authoritative.

This milestone is documentation/tests/audit first. Do not install PostGIS until the current geospatial paths are mapped.

## M0.1 — Repository-wide legacy inventory

Search and classify at minimum:

```text
legacy
deprecated
compat
compatibility
fallback
old_
TODO migration
remove after
remove once
dual write
dual-write
maritime_domain
lat / lon assumptions
area_geojson
_haversine
haversine
bearing
bbox
point_to_segment
GeoJSON stored in JSON
```

Audit:

- backend source;
- DB models;
- migrations;
- tests;
- frontend contracts;
- edge/live publisher;
- docs;
- deployment files;
- fixtures;
- environment variables.

Output a checked inventory inside this document or a linked `docs/architecture/legacy-inventory.md` before implementation starts.

Each item must be labelled:

```text
KEEP — still canonical and justified
MIGRATE — replaced by a named milestone below
DELETE — dead/obsolete
TEMP COMPAT — required temporarily, with explicit deletion milestone
```

## M0.2 — Geospatial duplication audit

Map every current implementation of:

- Haversine distance;
- bearing;
- bbox filtering;
- proximity checks;
- point-to-segment distance;
- land/sea tests;
- nearest-sea snapping;
- spatial clustering;
- area containment;
- track proximity;
- infrastructure proximity;
- GeoJSON parsing/creation;
- drift geometry representation;
- uncertainty representation.

The current shared `core.geo` module is a migration source, not automatically the permanent destination. Identify local duplicate helpers still present in AIS, fusion, zones, triangulation, drift or other code.

## M0.3 — JSON metadata schema audit

Find geospatial or analytical fields hidden in generic JSON/metadata that have become first-class domain data.

Examples to inspect:

```text
area_geojson
coordinate_source
area_confidence
location uncertainty
drift trajectory / cones
infrastructure geometry
subject geometry
public projection geometry
```

For each, decide whether it belongs in:

- typed DB column;
- typed geometry column;
- derived artifact;
- immutable provenance payload;
- compatibility metadata only.

## M0 exit gate

- complete inventory committed;
- no unclassified known legacy path related to spatial storage/query/projection;
- each TEMP COMPAT item points to a deletion milestone in this document;
- no production behaviour changed yet except safe dead-code removal proven by tests.

---

# 6. M1 — PostGIS geospatial foundation

**Goal:** introduce a canonical spatial database layer without breaking current contracts.

## M1.1 — PostgreSQL extension and dependency foundation

Add only the dependencies required for the first vertical slice:

```text
PostGIS
GeoAlchemy2
Shapely
PyProj
```

Do not add GeoServer, GDAL, H3, TimescaleDB, Kubernetes or tile servers in this milestone.

Requirements:

- production PostgreSQL enables PostGIS through a migration/provisioning path;
- local/dev setup documents how to enable the extension;
- CI has a PostgreSQL+PostGIS integration path;
- lightweight SQLite tests remain supported only where they still provide value;
- spatial behaviour is never considered verified solely through SQLite.

## M1.2 — Canonical point geometry

Introduce geometry/geography for one bounded entity class first, preferably the canonical observation/event location path.

Initial migration pattern:

```text
lat
lon
location_geom   <- new canonical spatial column
```

During migration only:

- existing lat/lon remain for public/API compatibility;
- writes must produce both through one canonical helper;
- reads must have an explicit authoritative source;
- divergence is treated as an error and tested.

Do not create independent dual-write implementations in different adapters.

## M1.3 — Spatial indexes

Create GiST indexes only for proven query paths.

At minimum benchmark:

- recent positioned events;
- events in bbox;
- events within radius;
- vessel positions within radius.

Record `EXPLAIN (ANALYZE, BUFFERS)` or equivalent evidence for representative PostgreSQL fixtures before and after.

## M1.4 — Backfill and rollback

Migration must:

- backfill geometry from valid lat/lon;
- reject/flag invalid coordinate ranges;
- preserve null/unpositioned states;
- be restart-safe;
- have a tested downgrade or explicitly documented irreversible boundary if a downgrade is unsafe;
- verify row counts and geometry counts.

## M1 exit gate

- PostGIS active in integration environment;
- one canonical location path is spatially backed;
- GiST query test exists;
- no frontend/public contract break;
- no duplicated dual-write path;
- rollback/backfill evidence captured;
- legacy lat/lon deletion remains deferred to M14.

---

# 7. M2 — Canonical spatial data model

**Goal:** stop treating all location as a single point.

Introduce explicit geometry roles.

Canonical conceptual model:

```text
reported_geometry
  geometry provided directly by source/sensor

derived_geometry
  geometry created deterministically from source evidence

uncertainty_geometry
  area in which the position/trajectory may plausibly lie

public_geometry
  privacy/publication projection only
```

A single entity may carry more than one of these. They are not aliases.

## M2.1 — Geometry evidence model

Prefer a dedicated typed record/table when geometry provenance becomes multi-valued rather than expanding one event table indefinitely.

Suggested fields:

```text
geometry_id
owner_type
owner_id
role
geometry
geometry_type
crs
method
method_version
precision_class
uncertainty_m
input_observation_ids[]
source_reference
created_at
```

## M2.2 — Tracks

Represent vessel trajectories as spatially queryable track geometry where beneficial.

Do not replace raw AIS position history with only a `LineString`.

Raw points remain evidence/time-series primitives. Derived lines are reproducible spatial products.

## M2.3 — Drift outputs

Current drift trajectory/cone JSON must migrate toward typed geometry/artifacts:

```text
trajectory -> LineString
cone_6h    -> Polygon/MultiPolygon
cone_12h   -> Polygon/MultiPolygon
cone_24h   -> Polygon/MultiPolygon
impact     -> Point or explicit uncertainty geometry
```

Preserve model version, forcing inputs, start time, simulation parameters and source observations.

## M2.4 — Operational regions and reference geography

Represent SAR regions, EEZs, territorial waters, ports, infrastructure corridors, AOIs and other durable reference geography as versioned data rather than ad-hoc Python constants where a real dataset exists.

## M2 exit gate

- reported/derived/uncertainty/public geometry semantics documented and tested;
- raw evidence never overwritten by derived geometry;
- drift and track migration strategy tested on fixtures;
- no generic metadata geometry remains authoritative where a typed replacement exists.

---

# 8. M3 — Spatial query migration

**Goal:** move candidate retrieval and geometry math into PostGIS while keeping evidence interpretation explicit in Python.

Priority conversions:

1. nearby events;
2. nearby vessels;
3. bbox selection;
4. point-in-zone;
5. infrastructure proximity;
6. track/area intersection;
7. drift/track or drift/event intersection;
8. nearest-object lookup;
9. spatiotemporal candidate generation for fusion;
10. deduplication shortlist generation.

Expected primitives include, where appropriate:

```text
ST_DWithin
ST_Intersects
ST_Contains / ST_Covers
ST_Distance
ST_ClosestPoint
ST_LineLocatePoint
ST_MakeLine
ST_Envelope
ST_Expand
ST_Simplify
```

Do not mechanically replace tested geodesic logic without validating units and geography-vs-geometry semantics.

## M3.1 — Fusion candidate generation

The DB should answer:

> Which recent events are plausible spatial/temporal candidates?

The domain layer should answer:

> Do these observations support the same incident, episode or hypothesis?

Never move evidence semantics into opaque SQL triggers.

## M3.2 — Remove duplicate math

After each successful migration:

- delete the superseded local helper;
- delete duplicate tests tied only to the old implementation;
- keep semantic parity/regression tests;
- update imports to one canonical path.

## M3 exit gate

- representative production-like query benchmark improved or justified;
- no semantic regression in fusion/replay;
- superseded local geometry code removed;
- query plans recorded for high-volume paths.

---

# 9. M4 — Humanitarian geolocation V2

**Goal:** make humanitarian location evidence explicit, uncertainty-aware and privacy-safe.

Supported location evidence types should include:

```text
reported coordinate
OCR coordinate
map screenshot coordinate
map pin inference
named place
relative location phrase
named region
operator-reviewed position
land humanitarian location
unpositioned
```

## M4.1 — Claim preservation

Do not collapse multiple location claims too early.

An event may include:

```text
text claim
OCR claim
image/map claim
thread/repost claim
external corroborating claim
```

Persist claim provenance and compare them before choosing a derived canonical geometry.

## M4.2 — Uncertainty geometry

Examples:

```text
exact reported coordinate -> Point + source precision
OCR coordinate -> Point + OCR confidence + uncertainty
place centroid -> derived Point + regional uncertainty Polygon
"south of Lampedusa" -> area/sector geometry, not fake precise point
map-pin fit -> derived Point + fit uncertainty
```

## M4.3 — Land/sea validation

Retain the existing semantic distinction between maritime humanitarian and land humanitarian incidents.

Rules:

- maritime location on land is suspicious evidence, not automatically deletable data;
- source coordinate remains preserved;
- corrected/snapped geometry is a derived geometry;
- land humanitarian remains visible under its own policy;
- never silently mutate source coordinates.

## M4.4 — Public projection

Public humanitarian geometry may be:

- exact only when policy explicitly permits;
- generalized;
- buffered;
- regionalized;
- cell-based;
- withheld.

The public projection must retain a machine-readable precision class.

## M4.5 — Replay corpus

Build/extend a labelled location corpus containing at minimum:

- Alarm Phone text coordinates;
- Alarm Phone map screenshots;
- coarse regional posts;
- contradictory text/image coordinates;
- land humanitarian cases;
- coastline ambiguity;
- invalid OCR number pairs;
- exact coordinate superseding stale region geometry;
- no-position negative fixtures.

## M4 exit gate

- no fake precision in replay corpus;
- public location policy tested independently from analyst location;
- source geometry preserved;
- location-method accuracy metrics reported.

---

# 10. M5 — H3 spatial intelligence layer

**Goal:** introduce a discrete spatial index only where it improves privacy, aggregation or scalable clustering.

Use H3 for:

- density aggregation;
- privacy-preserving humanitarian public cells;
- spatial statistics;
- coarse clustering;
- heatmaps;
- regional event summaries;
- cache keys where appropriate.

Do not use H3 as a replacement for original geometry.

Persist H3 resolution explicitly. Never compare cells of different resolutions without deliberate conversion.

Exit gate:

- geometry remains authoritative;
- H3 is reproducible from geometry;
- privacy behaviour tested across cell boundaries;
- no exact private position leaks through cell metadata or API payloads.

---

# 11. M6 — Geospatial dataset ingestion with GDAL/OGR

**Goal:** create a deterministic, provenance-aware import path for external vector/raster geography.

Only start after PostGIS schema and provenance conventions are stable.

## M6.1 — Vector ingestion

Support justified source formats such as:

```text
GeoJSON
GeoPackage
Shapefile
KML
CSV with explicit coordinate schema
```

Normalize using GDAL/OGR where beneficial.

Potential datasets:

- SAR regions;
- EEZs;
- territorial waters;
- coastlines;
- ports;
- subsea cables;
- pipelines;
- offshore infrastructure;
- protected areas;
- operational AOIs.

## M6.2 — Import manifest

Every imported dataset needs:

```text
source_name
source_url/source_id
source_version/date
licence/terms
retrieved_at
checksum
original_crs
canonical_crs
import_tool_version
transform steps
row/feature count
validation result
```

## M6.3 — Validation

Reject or quarantine:

- invalid geometry;
- unknown CRS;
- impossible coordinate ranges;
- malformed polygons;
- unexpected feature-count collapse;
- duplicate source version.

Do not silently `make_valid` and lose evidence of source defects. Preserve validation findings.

## M6 exit gate

- at least one real reference dataset imported reproducibly;
- same input checksum produces identical canonical feature identity;
- licence/provenance recorded;
- import can be replayed from scratch.

---

# 12. M7 — QGIS operational QA and analyst validation

**Goal:** make spatial correctness inspectable independently of the SeaCommons frontend.

QGIS is development/QA tooling, not a runtime dependency.

Create a documented read-only analyst/debug setup with layers for:

```text
raw/reported geometry
derived geometry
uncertainty geometry
public geometry
humanitarian events
AIS positions
vessel tracks
drift trajectories
6h/12h/24h cones
SAR/EEZ/reference zones
infrastructure
anomalies/correlated alerts
```

Where safe, provide a versioned QGIS project or a reproducible setup document.

Security:

- read-only DB role;
- no production secrets committed;
- vulnerable-person exact locations not exposed to general/shared analyst profiles;
- separate analyst/public connection examples.

Exit gate:

- representative geospatial bug can be independently reproduced/inspected in QGIS;
- QA procedure documented;
- no runtime coupling to QGIS.

---

# 13. M8 — Map delivery and vector-tile scaling

**Goal:** stop sending unnecessarily large GeoJSON payloads as spatial volume grows.

Do not implement until measurement shows a real map-delivery bottleneck.

Candidate architecture:

```text
PostGIS
  ↓
ST_AsMVT / Martin / pg_tileserv
  ↓
MapLibre
```

Choose the smallest system that satisfies actual requirements.

Requirements:

- tiles respect public/private projection rules;
- zoom-aware geometry simplification;
- no private attributes embedded in public tiles;
- deterministic cache invalidation strategy;
- bounded tile size;
- benchmark at representative event/AIS volumes.

Do not hide domain metadata needed by the event panel solely to optimize tiles; separate map geometry transport from detail APIs if necessary.

Exit gate:

- map benchmark shows material improvement;
- tile privacy contract tests green;
- legacy bulk GeoJSON endpoint removed or explicitly retained for export with documented limits.

---

# 14. M9 — Raster and ocean-data architecture

**Goal:** support oceanographic/satellite/model rasters without turning the core DB into a raster archive.

SeaCommons already uses scientific/ocean tooling. Treat large raster/model outputs as artifacts.

Preferred pattern where justified:

```text
Copernicus / model / satellite source
        ↓
xarray / GDAL processing
        ↓
Cloud Optimized GeoTIFF (COG) or equivalent
        ↓
object storage
        ↓
rio-tiler / TiTiler if dynamic tile delivery is required
        ↓
MapLibre / Cesium
```

Store metadata/provenance in PostgreSQL; store heavy raster payloads in object storage.

Do not introduce PostGIS Raster unless a measured query requirement specifically benefits from it.

Potential use cases:

- currents;
- wind;
- waves;
- sea-surface temperature;
- bathymetry;
- satellite detection layers;
- drift forcing context;
- model uncertainty layers.

Exit gate:

- one raster pipeline reproducible end-to-end;
- checksum/provenance recorded;
- no uncontrolled local-file dependency;
- public licensing verified.

---

# 15. M10 — AIS spatial/time-series scale

**Goal:** ensure vessel history remains performant as retention and coverage increase.

Do not add TimescaleDB first.

Start with native PostgreSQL/PostGIS:

- spatial index;
- temporal index;
- composite indexes from real query patterns;
- time partitioning where measured;
- retention/pruning strategy;
- VACUUM/ANALYZE expectations;
- representative query benchmarks.

Benchmark at increasing scales, e.g.:

```text
1M positions
10M positions
50M positions
100M positions where infrastructure allows
```

Key queries:

- track by MMSI/time;
- positions in bbox/time;
- nearby vessels at time window;
- rendezvous candidate generation;
- zone crossing;
- infrastructure proximity;
- recent history for multiple MMSIs.

Only evaluate TimescaleDB if native Postgres becomes an evidenced bottleneck that Timescale addresses without unacceptable operational complexity.

Exit gate:

- documented data-volume envelope;
- query-plan evidence;
- retention behaviour tested;
- no full-table spatial scans on primary operational paths.

---

# 16. M11 — Reproducible infrastructure with Docker + Ansible

**Goal:** replace manual VM configuration with a reproducible, auditable deployment.

Current/manual deployment concepts to automate include:

- base Ubuntu configuration;
- users/SSH;
- firewall;
- Docker/runtime dependencies;
- PostgreSQL;
- PostGIS;
- Redis where required;
- Nginx/reverse proxy;
- TLS integration;
- application services/workers;
- environment/secrets references;
- backups;
- log rotation;
- monitoring exporters;
- restart policies.

## M11.1 — Docker boundary review

Do not split services only for aesthetics.

Possible images if dependency weight or scaling justifies separation:

```text
seacommons-api
seacommons-worker
seacommons-geospatial-worker
seacommons-drift-worker
```

A single image remains valid if operationally simpler.

## M11.2 — Ansible

Create idempotent playbooks/roles that can provision a clean supported VM into a working SeaCommons node.

Requirements:

- no secrets in repo;
- second run is safe/idempotent;
- version-pinned critical services where appropriate;
- database migration is an explicit deployment step;
- backup/restore paths documented.

## M11.3 — Disaster recovery test

Prove restoration from backups into a fresh environment including PostGIS geometry and required object-storage metadata.

Exit gate:

- clean VM -> operational stack reproducibly;
- redeploy idempotency tested;
- restore test green;
- old manual instructions either updated to call automation or removed.

---

# 17. M12 — GIS interoperability

**Goal:** expose standards only when an external consumer needs them.

Potential requirements:

- GeoJSON export;
- GeoPackage export;
- WMS;
- WFS;
- WMTS;
- OGC API Features.

GeoServer is allowed only when there is a concrete interoperability requirement that the existing API/tile stack does not satisfy cleanly.

Before adding GeoServer, document an ADR comparing at least:

```text
existing FastAPI + PostGIS
pg_featureserv / equivalent lightweight service
GeoServer
```

Evaluate:

- protocol need;
- authorization;
- styling;
- operational cost;
- memory;
- caching;
- licence;
- maintenance burden.

Do not add GeoNode unless SeaCommons is deliberately becoming a generic GIS catalogue/portal, which is not currently the product direction.

Exit gate:

- interoperability feature is driven by a documented partner/user need;
- access/privacy policies hold through GIS protocols;
- no duplicate authoritative API semantics.

---

# 18. M13 — Explicit non-goals / prohibited premature dependencies

The following technologies must NOT be introduced into SeaCommons merely because they are common in GIS job descriptions:

```text
Django
.NET
Oracle Spatial
Microsoft SQL Server Spatial
ESRI Experience Builder
ArcGIS runtime dependencies
FME
GeoNode
Kubernetes
TimescaleDB
GeoServer
```

They may be reconsidered only with an ADR demonstrating:

1. the specific unsolved requirement;
2. why the existing stack cannot solve it cleanly;
3. alternatives evaluated;
4. operational cost;
5. migration/exit strategy;
6. test plan.

Learning a technology for professional development is not sufficient reason to introduce it into production.

---

# 19. M14 — Final legacy deletion

**Goal:** once the spatial architecture has proven parity, remove transitional architecture rather than preserving it forever.

This is a release milestone, not cleanup to do "someday".

## M14.1 — Remove spatial dual-write compatibility

If geometry has become canonical and all consumers have migrated:

- remove duplicate authoritative lat/lon write logic;
- retain lat/lon only as derived API projection fields where a contract still needs scalar coordinates;
- eliminate divergence possibility between scalar fields and canonical geometry.

Do not necessarily remove scalar API output; remove scalar persistence as an independent source of truth.

## M14.2 — Remove obsolete metadata geometry

Delete authoritative dependence on metadata such as legacy `area_geojson` once typed geometry evidence has full parity.

Migration may retain original raw payload metadata as provenance, but consumers must not route based on obsolete compatibility keys.

## M14.3 — Remove old geospatial helpers

Repository-wide prove that obsolete custom implementations are gone where PostGIS/canonical geometry replaced them.

Search again for:

```text
_haversine
point_to_segment
bbox manual comparisons
manual point-in-zone
manual infrastructure proximity
legacy geometry serialization
```

Keep a Python geometry helper only when it remains deliberately useful outside DB queries and has a documented canonical purpose.

## M14.4 — Remove stale taxonomy and compatibility fields

Coordinate with `fixes.md` canonical data-model migration.

Fields such as old routing/taxonomy compatibility values must not survive simply because old fixtures reference them.

Tests must migrate to canonical semantics before deletion.

## M14.5 — Remove stale docs/config/tests

Audit:

- obsolete env vars;
- old deployment docs;
- dead API examples;
- old frontend props;
- abandoned fixtures;
- skipped migration tests;
- compatibility comments whose removal condition has passed.

## M14 exit gate — legacy burn-down

Run a repository-wide legacy audit.

Every remaining occurrence of:

```text
legacy
deprecated
compat
fallback
old_
remove after
TODO migration
```

must be one of:

- legitimate historical/test documentation;
- necessary external compatibility with explicit justification;
- active temporary compatibility with an issue/milestone and deletion condition.

No unexplained compatibility path may remain in production code.

---

# 20. M15 — Production qualification

**Goal:** prove the upgraded system is more correct and operable than the stabilized baseline.

Required final qualification matrix:

## Correctness

- full backend suite;
- full web suite;
- spatial unit tests;
- PostgreSQL/PostGIS integration tests;
- geometry migration tests;
- coordinate/CRS validation tests;
- Humanitarian location replay;
- AIS/fusion replay;
- drift geometry replay.

## Privacy

- analyst vs public geometry tests;
- exact-location leakage tests;
- vector-tile privacy tests if tiles enabled;
- exports obey role/policy rules;
- humanitarian public projection review.

## Performance

Benchmark against the pre-upgrade baseline:

- nearby-event query;
- AIS bbox/time query;
- fusion candidate generation;
- track retrieval;
- map initial load;
- map pan/zoom under representative load;
- DB size/index overhead.

Do not claim improvement without numbers.

## Operations

- fresh deploy;
- migration from prior production schema;
- backup;
- restore;
- worker restart;
- DB reconnect;
- corrupted/invalid geodata rejection;
- object-storage/raster degradation where applicable.

## Observability

At minimum expose/record where relevant:

- ingestion failures;
- invalid geometry count;
- unpositioned event count;
- geometry derivation failures;
- spatial query latency;
- tile latency/cache metrics if enabled;
- AIS write/prune volume;
- drift artifact failures;
- geodata import version.

## Documentation

Final docs must describe:

- canonical spatial model;
- geometry evidence semantics;
- database/index architecture;
- geospatial ingestion;
- privacy projection;
- QGIS analyst workflow;
- deployment/restore;
- interoperability endpoints if enabled;
- removed legacy architecture.

---

# 21. Recommended milestone dependency graph

```text
fixes.md COMPLETE
      ↓
M0 Legacy census
      ↓
M1 PostGIS foundation
      ↓
M2 Canonical spatial model
      ↓
M3 Spatial query migration
      ↓
M4 Humanitarian geolocation V2
      ↓
M5 H3 (optional if justified)
      ↓
M6 GDAL/OGR ingestion
      ↓
M7 QGIS QA
      ↓
M8 Vector-tile scaling (only when measured)
      ↓
M9 Raster/ocean architecture (when required)
      ↓
M10 AIS scale
      ↓
M11 Docker/Ansible reproducibility
      ↓
M12 GIS interoperability (only on demand)
      ↓
M14 Legacy deletion
      ↓
M15 Production qualification
```

M13 is a standing non-goal gate throughout the program.

Parallel work is allowed only when two milestones do not modify the same schema/contracts and both can independently satisfy their exit gates. Never parallelize migrations that compete for authority over the same data path.

---

# 22. Definition of DONE

The upgrade program is DONE only when:

1. `fixes.md` remains green after all upgrades;
2. PostGIS is the canonical spatial query layer;
3. source/report/derived/uncertainty/public geometry are distinguishable;
4. high-value proximity/containment/intersection queries are no longer implemented through scattered ad-hoc loops;
5. humanitarian location is uncertainty-aware and privacy-safe;
6. imported geography is versioned and provenance-aware;
7. large map delivery is scalable if volume justified implementing tiles;
8. raster/model data has an explicit artifact architecture if used;
9. AIS scale limits are measured rather than guessed;
10. deployment is reproducible;
11. legacy compatibility introduced during migration has been removed;
12. repository-wide legacy audit has no unexplained production residue;
13. production qualification demonstrates correctness, privacy, performance and recovery on the final commit.

The target is not "more GIS tools". The target is a simpler, more rigorous SeaCommons whose geospatial capabilities are first-class, testable, reproducible and operationally credible.
