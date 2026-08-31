You are optimizing the SeaCommons live maritime intelligence dashboard and its backend/API architecture.

Your task is NOT to redesign the product from scratch. Preserve the existing working pipelines, data sources, routes and UI patterns wherever possible. The goal is to reduce semantic ambiguity, duplicate data, misleading labels, and unnecessary event volume while making the system easier to understand for non-maritime users.

Use the current production behavior and existing codebase as the source of truth. Before changing anything, inspect the relevant backend routes, event schemas, MDA logic, vessel identity enrichment, sanctions fusion, Live feed projection, and frontend map/panel components.

CURRENT VERIFIED CONTEXT

The platform currently combines:

- AIS vessel positions from AISStream
- MDA-derived anomalies including:
  - AIS gap
  - possible spoofing
  - rendezvous
  - infrastructure loitering
  - identity anomalies
- sanctions matching via OpenSanctions / OFAC
- NGO RSS / IOM humanitarian signals
- Sentinel-1 SAR / Global Fishing Watch dark-vessel context
- social / OSINT sources
- source-health reporting

The current architecture has an important semantic problem:

1. Vessel state / vessel attributes
2. Detected maritime anomalies
3. Humanitarian events
4. Source health
5. Security/compliance enrichment

are partially mixed together in the Live feed and map.

The optimization should clearly separate these concepts.

--------------------------------------------------
1. CORE DATA MODEL
--------------------------------------------------

Introduce or reinforce the distinction between:

A. VESSEL
A persistent entity.

Examples of vessel attributes:
- MMSI
- IMO
- vessel name
- flag
- ship type
- latest AIS position
- navigation status
- sanctions status
- watchlist status
- identity metadata

B. EVENT / SIGNAL
Something that happened at a point in time.

Examples:
- AIS gap
- possible spoofing
- rendezvous
- infrastructure loitering
- dark-vessel detection/cue
- distress
- SAR activity
- migrant incident
- maritime hazard

Do NOT model "sanctioned vessel" as an independent recurring Live event if it is simply a persistent property of a vessel.

Instead, sanctions should enrich the vessel entity.

Preferred conceptual schema:

vessel:
{
  mmsi,
  imo,
  name,
  flag,
  position,
  nav_status,
  sanctions: {
    matched: boolean,
    sources: [],
    matched_on: [],
    last_checked,
    details
  }
}

signal:
{
  id,
  type,
  domain,
  vessel_mmsi,
  timestamp,
  position,
  severity,
  confidence,
  evidence_level,
  context
}

Only create a sanctions-related event when something actually changes, for example:
- a vessel is newly added to a sanctions list
- a previous sanctions match changes
- a relevant maritime anomaly involves a sanctioned vessel

Do not duplicate a vessel on the map just because it has a sanctions match.

--------------------------------------------------
2. LIVE FEED DOMAINS
--------------------------------------------------

Create a clear semantic split between:

HUMANITARIAN

Examples:
- distress
- Search and Rescue activity
- migrant incidents
- Missing Migrants / IOM incidents
- NGO reports
- maritime hazards relevant to human safety

MARITIME SECURITY

Examples:
- AIS gap
- possible AIS spoofing
- rendezvous
- infrastructure loitering
- identity anomaly
- dark-vessel cue
- relevant sanctions context

Do not expose internal taxonomy such as "grey_zone" directly to normal users unless there is a specific reason.

Map existing internal domains to user-facing categories.

Example:

sar / safety / migration
→ humanitarian

mda / sanctions / grey_zone
→ maritime_security

Do NOT classify a generic AIS gap as "distress".

This is especially important.

"Distress" has a specific maritime meaning indicating danger/emergency and should not be used as a generic status for security anomalies.

--------------------------------------------------
3. SINGLE LIVE ENDPOINT WITH MODE SWITCH
--------------------------------------------------

Prefer keeping a unified Live API rather than proliferating unnecessary endpoints.

Target architecture:

GET /api/v1/live/signals?mode=humanitarian

GET /api/v1/live/signals?mode=security

Optional:

GET /api/v1/live/signals?mode=all

The frontend should use one Live panel with a simple switch:

[ HUMANITARIAN ] [ MARITIME SECURITY ]

Changing the switch should ideally change the server-side query/filter rather than downloading every event and hiding most of them client-side.

Preserve existing compatibility where practical.

If /api/v1/live/mda-anomalies already exists and is used elsewhere, do NOT remove it blindly. Determine whether:
- it remains a specialist endpoint,
- becomes an internal source for /live/signals?mode=security,
- or can be deprecated safely.

Document the decision.

--------------------------------------------------
4. MAP BEHAVIOR
--------------------------------------------------

The map may remain unified.

However, the selected Live mode should affect:

- visible/highlighted markers
- legend
- feed cards
- counts
- filters

Avoid plotting multiple markers for the same vessel merely because multiple enrichment records exist.

A vessel should normally have one current AIS marker.

Persistent attributes such as:

- sanctioned
- watchlisted
- identity mismatch

should appear as badges / visual enrichment on that vessel.

Examples:

VESSEL NAME
AIS active
[SANCTIONED]

If the vessel generates an actual anomaly:

AIS REPORTING GAP
VESSEL NAME [SANCTIONED]

This allows sanctions status to become useful context rather than map noise.

--------------------------------------------------
5. AIS GAP LANGUAGE
--------------------------------------------------

Audit all user-facing language around AIS gaps.

Current problematic example:

"AIS gap within 0.0 km of Malta bunkering / STS anchorage (sts_zone)"

This should NOT be shown literally when the event lies inside a polygon.

Implement human-readable geographic formatting.

If point is inside the zone:

"AIS reporting gap detected within Malta STS area"

or:

"AIS reporting gap detected inside Malta bunkering / STS anchorage"

If outside:

"AIS reporting gap detected 3.4 km from Malta STS area"

Do not say:

"within 0.0 km"

when the point is contained inside the polygon.

Investigate the actual geometry/distance calculation first and confirm whether 0.0 means:
- inside polygon
- touching polygon
- rounding artifact
- missing distance

Do not assume.

--------------------------------------------------
6. MARITIME TERMINOLOGY
--------------------------------------------------

Make terminology understandable to non-specialists without losing technical precision.

Preferred user-facing labels:

AIS gap
→ AIS reporting gap

STS
→ Ship-to-ship transfer

Bunkering
→ Vessel refuelling / bunkering

Loitering
→ Prolonged presence / loitering

Spoofing
→ Possible AIS position manipulation

Dark vessel
→ Vessel detected without corresponding AIS position

Distinguish carefully between:

SAR = Search and Rescue

and

SAR = Synthetic Aperture Radar

Do not expose both simply as "SAR" in the same interface without clarification.

--------------------------------------------------
7. OBSERVATION VS INTERPRETATION
--------------------------------------------------

Every anomaly should distinguish factual observation from algorithmic interpretation.

Example:

OBSERVATION
AIS reporting stopped for 43 minutes.

CONTEXT
Last known position was inside Malta STS area.

ASSESSMENT
Possible anomalous AIS interruption.

Do not imply illegality or malicious intent unless the data supports it.

An AIS gap does NOT automatically mean:
- AIS deliberately switched off
- illegal activity
- sanctions evasion
- distress

Likewise, rendezvous and loitering are contextual indicators, not proof of wrongdoing.

Where possible introduce fields such as:

confidence
evidence_level

Suggested evidence levels:

observed
derived
correlated
official_match
externally_confirmed

Example:

AIS gap:
evidence_level = observed

possible spoofing:
evidence_level = derived

sanctions match:
evidence_level = official_match

multi-source anomaly:
evidence_level = correlated

--------------------------------------------------
8. SEVERITY AND RELEVANCE
--------------------------------------------------

Review severity logic.

Severity should consider context rather than event type alone.

Example:

AIS gap
+ open sea
+ non-watchlisted vessel
→ LOW / MEDIUM

AIS gap
+ STS zone
→ MEDIUM

AIS gap
+ STS zone
+ sanctioned vessel
→ HIGH

AIS gap
+ sanctions match
+ rendezvous
+ long duration
→ potentially HIGH / CRITICAL depending on existing policy

Do NOT automatically implement these exact thresholds without checking current logic.

Instead:
1. locate current severity calculation
2. document it
3. propose the smallest coherent improvement
4. avoid arbitrary risk scoring

--------------------------------------------------
9. SANCTIONS OPTIMIZATION
--------------------------------------------------

Review the current sanctions fusion pipeline.

The current system may produce large numbers of sanctions-domain events.

Optimize so that sanctions matching primarily enriches vessels instead of continuously producing duplicate Live events.

Required behavior:

AIS vessel
→ identity matching
→ sanctions enrichment
→ vessel badge/state

Then:

anomaly involving sanctioned vessel
→ anomaly signal enriched with sanctions context

Avoid:

AIS marker
+
sanctions marker
+
correlated wrapper
+
same vessel rendered again

for the same underlying object.

Ensure no sanctions record without a valid vessel position gets plotted at fallback coordinates such as 0,0.

--------------------------------------------------
10. SOURCE HEALTH
--------------------------------------------------

Improve /api/v1/live/sources.

Current channel-level statuses may be misleading when a polling process runs successfully but individual tracked accounts are dead.

Move toward per-source / per-handle health.

Instead of:

Twitter
ACTIVE

prefer:

Twitter
DEGRADED
8 / 13 sources reachable

With optional detail:

alarm_phone        healthy
MSF_Sea            healthy
SeaEye4            unavailable
etc.

Clearly distinguish:

pipeline health

from:

source availability

Example:

{
  "channel": "twitter",
  "pipeline_status": "healthy",
  "source_status": "degraded",
  "configured": 13,
  "reachable": 8
}

Do the same where appropriate for other multi-source channels.

--------------------------------------------------
11. FRONTEND PANEL
--------------------------------------------------

Optimize the existing Live panel rather than replacing its entire visual identity.

Add a clear top-level mode switch:

LIVE FEED

[ HUMANITARIAN ] [ MARITIME SECURITY ]

Each card should prioritize:

1. What happened
2. Where
3. When
4. Which vessel, if applicable
5. Why this matters / context
6. confidence or evidence level when relevant

Example security card:

AIS REPORTING GAP

ROYAL STAR [SANCTIONED]

Malta STS area
43 min gap

Medium relevance
Derived from AIS track

Example humanitarian card:

DISTRESS REPORT

Central Mediterranean
Reported 8 min ago

Source: Alarm Phone

Do not mix humanitarian distress semantics with MDA anomaly semantics.

--------------------------------------------------
12. COUNTS AND METRICS
--------------------------------------------------

Ensure counts in the sidebar clearly correspond to the currently selected mode.

If:

Humanitarian selected

show counts for humanitarian signals only.

If:

Maritime Security selected

show counts for security anomalies only.

Avoid showing a total event count that includes invisible or filtered categories without explaining it.

If useful, show:

Humanitarian: 4 active
Security: 408 active

rather than one ambiguous total.

--------------------------------------------------
13. BACKWARD COMPATIBILITY
--------------------------------------------------

Before changing schemas or endpoints:

- find all current consumers
- inspect frontend usage
- inspect tests
- inspect external/public dependencies
- preserve old fields where cheap
- introduce compatibility mappings where necessary

Do not remove working API behavior unless you can demonstrate it is unused or safely migrated.

--------------------------------------------------
14. AUDIT BEFORE MODIFYING
--------------------------------------------------

Before writing code, produce a short architecture report containing:

A. Current event flow

AIS / RSS / external source
→ ingestion
→ normalization
→ correlation
→ Live projection
→ API
→ frontend

B. Current vessel representation

C. Current sanctions flow

D. Current MDA anomaly flow

E. Current severity calculation

F. Current public-domain filtering

G. Exact reason AIS gap events currently receive any misleading "distress" state, if confirmed

H. Exact origin of:
"within 0.0 km of Malta bunkering / STS anchorage (sts_zone)"

I. Duplicate rendering paths

J. APIs/components that would need modification

Do not guess.

Reference exact files/functions/lines.

--------------------------------------------------
15. IMPLEMENTATION STRATEGY
--------------------------------------------------

After the audit, implement the optimization incrementally.

Suggested order:

PHASE 1
Semantic fixes
- correct distress misuse
- improve AIS gap wording
- inside-zone vs distance formatting
- improve labels

PHASE 2
Sanctions normalization
- vessel enrichment
- deduplication
- remove duplicate sanctions map events where appropriate

PHASE 3
Live modes
- humanitarian/security server filtering
- panel switch
- mode-aware counts
- mode-aware map behavior

PHASE 4
Source health
- per-handle health
- degraded state
- clearer source metrics

PHASE 5
Confidence / evidence model
- normalize fields
- surface carefully in frontend

Avoid a large rewrite.

Keep each change independently testable.

--------------------------------------------------
16. TESTS
--------------------------------------------------

Add or update tests for at least:

- AIS gap inside STS polygon
  → "inside/within zone", never "0.0 km"

- AIS gap outside zone
  → correct distance

- AIS gap
  → not classified as distress by default

- sanctioned vessel
  → single vessel marker with sanctions enrichment

- sanctioned vessel + AIS gap
  → one anomaly card enriched with sanctions context

- duplicate raw/fused MDA results
  → one displayed signal when they refer to same underlying event

- invalid/missing vessel coordinates
  → never rendered at 0,0

- humanitarian mode
  → security events excluded

- security mode
  → humanitarian events excluded unless explicitly shared by design

- source channel partially unavailable
  → DEGRADED rather than ACTIVE

--------------------------------------------------
17. PRODUCT PRINCIPLE
--------------------------------------------------

The final system should answer three different questions cleanly:

1. WHAT IS HAPPENING TO PEOPLE AT SEA?
   → Humanitarian

2. WHAT IS HAPPENING IN MARITIME TRAFFIC?
   → Maritime Security

3. HOW RELIABLE ARE THE SOURCES TELLING US THIS?
   → Source Health

Do not collapse these into one generic concept of "alert".

The goal is not to make SeaCommons look more alarming.

The goal is to make it more precise, legible, trustworthy and useful.

--------------------------------------------------
FINAL OUTPUT REQUIRED
--------------------------------------------------

Return:

1. Current architecture findings
2. Problems found, ranked by impact
3. Proposed minimal architecture
4. Exact files/functions to change
5. Migration risks
6. Implementation plan
7. Code changes
8. Tests added
9. Before/after API examples
10. Before/after UI examples

For every architectural assumption, verify it against the code before implementing it.

Do not fabricate maritime semantics, positions, vessel activity, or external confirmation.

ADDITIONAL OPTIMIZATION MODULE:
HUMANITARIAN INTELLIGENCE LAYER

This module extends the previous SeaCommons optimization prompt.

Do NOT weaken, merge, or replace the Maritime Security / MDA architecture defined previously.

The goal here is to strengthen the Humanitarian side of SeaCommons so that it becomes a coherent, case-based, people-centered situational awareness layer rather than simply a collection of NGO/social/news signals.

Before implementing anything, inspect the current humanitarian ingestion, normalization, correlation, public policy, API projection and frontend rendering.

Do not assume the current schemas already support the concepts below.

Verify first.

--------------------------------------------------
1. PRODUCT PRINCIPLE
--------------------------------------------------

The Humanitarian layer should answer:

WHAT IS HAPPENING TO PEOPLE AT SEA?

It should NOT be primarily vessel-centric.

Maritime Security can remain:

VESSEL
→ behaviour
→ anomaly
→ context

Humanitarian should become:

CASE
→ people
→ situation
→ response
→ outcome

The same AIS and geospatial infrastructure may support both layers, but the underlying entity model should remain conceptually distinct.

--------------------------------------------------
2. CREATE A HUMANITARIAN CASE MODEL
--------------------------------------------------

Do not treat every incoming humanitarian source item as an independent Live event.

Introduce or strengthen the concept of a persistent humanitarian CASE.

A case represents one real-world situation that may accumulate multiple updates and multiple sources over time.

Example conceptual schema:

{
  "case_id": "MED-2026-08-30-017",

  "type": "distress_report",

  "status": "ongoing",

  "area": "Central Mediterranean",

  "position": {
    "lat": null,
    "lon": null,
    "precision": "approximate"
  },

  "people": {
    "reported": 47,
    "confirmed": null,
    "children": null,
    "medical_cases": null
  },

  "vessel_context": {
    "type": "rubber_boat",
    "identifier": null
  },

  "first_reported_at": "...",
  "last_updated_at": "...",

  "verification": {
    "level": "corroborated",
    "source_count": 3
  },

  "sources": [...],

  "timeline": [...],

  "outcome": null
}

Do not implement this exact schema blindly.

First inspect the existing data model and reuse compatible fields where possible.

--------------------------------------------------
3. HUMANITARIAN EVENT TAXONOMY
--------------------------------------------------

Create a more precise user-facing taxonomy.

Possible event/case types:

- distress_report
- rescue_operation
- rescue_completed
- interception
- disembarkation
- shipwreck
- missing_persons
- death_report
- medical_evacuation
- port_assignment
- ngo_operational_update
- border_authority_action
- weather_risk
- loss_of_contact

Avoid generic labels when a more specific humanitarian concept exists.

Important distinction:

REPORT
→ someone reports a situation

OPERATION
→ an intervention is taking place

OUTCOME
→ the result of that intervention or incident

Do not automatically convert a single-source report into a confirmed incident.

--------------------------------------------------
4. DISTRESS SEMANTICS
--------------------------------------------------

Use "distress" carefully.

A distress report should not automatically mean:

- independently confirmed distress
- confirmed rescue requirement
- confirmed emergency status

Preferred progression:

distress_report
→ reported

distress_case
→ corroborated

rescue_operation
→ operational response reported

resolved_case
→ known outcome

Example:

DISTRESS REPORT
Source: Alarm Phone
Verification: single-source

Then, if another independent or authoritative source confirms:

DISTRESS CASE
Sources: Alarm Phone + NGO
Verification: corroborated

Avoid overstating certainty.

--------------------------------------------------
5. CASE CORRELATION
--------------------------------------------------

This is a high-priority feature.

Multiple humanitarian sources may refer to the same incident.

Do NOT render five separate Live cards simply because five sources published about one case.

Investigate whether the current correlation system can be reused.

Correlation inputs may include:

- time window
- geographic proximity
- approximate coordinates
- reported number of people
- vessel/boat description
- named rescue vessel
- origin/departure area
- destination/port
- keywords
- source-provided case identifiers
- operational timestamps

Example:

Alarm Phone post
+
SOS MEDITERRANEE update
+
InfoMigrants report
+
IOM incident

may represent ONE CASE.

The desired output should be:

ONE humanitarian case
with
MULTIPLE source observations.

Do not merge automatically when confidence is low.

Support:

possible_match
probable_match
confirmed_same_case

or an equivalent internal mechanism.

--------------------------------------------------
6. SOURCE OBSERVATION VS CASE
--------------------------------------------------

Preserve original source observations.

Do not destroy provenance when correlating.

Model conceptually:

SOURCE OBSERVATION
→ raw/normalized report

CASE
→ correlated real-world situation

Example:

case.sources = [
  {
    source: "Alarm Phone",
    observed_at: "...",
    claim: "...",
    source_url: "...",
    reliability: ...
  },
  {
    source: "SOS Mediterranee",
    observed_at: "...",
    claim: "...",
    source_url: "...",
    reliability: ...
  }
]

The frontend may show the case as one card while allowing users to inspect the underlying sources.

--------------------------------------------------
7. HUMANITARIAN VERIFICATION MODEL
--------------------------------------------------

Introduce or normalize a verification state.

Prefer understandable categories rather than a false numerical precision.

Possible levels:

unverified
single_source
multi_source
corroborated
officially_confirmed

Do not equate:

"multiple social posts"

with:

"officially confirmed".

Also distinguish source reliability from event verification.

For example:

source = official NGO
does not automatically mean
case outcome = confirmed

The source may itself be reporting uncertainty.

--------------------------------------------------
8. PEOPLE-CENTERED DATA
--------------------------------------------------

The Humanitarian layer should prioritize people rather than vessels.

Where source material supports it, allow fields such as:

- reported_people
- confirmed_people
- children_reported
- medical_cases
- deaths_reported
- missing_reported
- rescued_reported

Never fabricate missing values.

Unknown should remain unknown.

Avoid converting approximate quantities into exact values.

Example:

"around 50 people"

should not become:

50 confirmed persons

Prefer:

reported_people:
{
  value: 50,
  qualifier: "approximate"
}

or an equivalent representation.

--------------------------------------------------
9. PRIVACY AND SAFETY
--------------------------------------------------

Audit whether humanitarian data could expose vulnerable people or active rescue situations.

Private partner reports must remain private by default.

Existing partner intake behavior should remain:

publish = false
unless explicitly approved.

Do not automatically expose:

- precise coordinates from private distress reports
- phone numbers
- personal names
- messaging metadata
- personally identifying information
- sensitive operational details

Consider location precision levels:

exact
approximate
area_only
withheld

Public API responses should use the appropriate precision.

Do not weaken existing privacy safeguards.

--------------------------------------------------
10. HUMANITARIAN TIMELINE
--------------------------------------------------

A major product goal should be reconstructing the progression of a case.

Each case should be capable of accumulating timeline events.

Example:

14:02
First distress report

14:37
Public alert issued

15:12
Second source corroborates case

16:04
SAR vessel observed nearby

17:46
Rescue operation reported

21:20
Port assigned

Next day
Disembarkation completed

This should be generated from actual timestamped observations, not inferred narrative.

Where the source relationship is uncertain, label it explicitly.

--------------------------------------------------
11. CASE STATUS
--------------------------------------------------

Introduce a clear lifecycle.

Possible states:

reported
ongoing
response_reported
rescue_reported
intercepted
disembarkation_pending
resolved
unresolved
lost_contact
archived

Do not use "resolved" merely because no new reports have arrived.

An absence of updates is not an outcome.

Potential distinction:

active
stale
resolved
archived

should be investigated against current system behavior.

--------------------------------------------------
12. UNRESOLVED CASES
--------------------------------------------------

Humanitarian dashboard metrics should prioritize unresolved situations.

Instead of optimizing for raw event volume, consider metrics such as:

ACTIVE CASES

UNRESOLVED CASES

PEOPLE REPORTED

RESCUES REPORTED TODAY

CASES WITH NO UPDATE > X HOURS

Do not calculate aggregate people counts by naïvely summing duplicated observations.

Counts must operate at CASE level after correlation.

If confidence is insufficient, expose qualifiers.

Example:

~418 people reported across 12 cases

rather than:

418 confirmed people

--------------------------------------------------
13. AIS AS HUMANITARIAN CONTEXT
--------------------------------------------------

Reuse SeaCommons' strong AIS infrastructure, but do not make humanitarian cases vessel-centric.

AIS can provide contextual information such as:

- nearby NGO SAR vessels
- rescue vessel position
- vessel movement
- distance from reported case
- port approach
- disembarkation context

Example:

DISTRESS REPORT

~47 people reported
Central Mediterranean

Nearby SAR assets:
Ocean Viking — 38 nm
Geo Barents — 76 nm

This does NOT mean those vessels are responding.

The UI must explicitly distinguish:

nearby

from:

responding

from:

confirmed involved

Never infer rescue intent from proximity alone.

--------------------------------------------------
14. HUMANITARIAN VESSEL RELATIONSHIPS
--------------------------------------------------

If a case becomes associated with a vessel, use explicit relationship types.

Examples:

nearby
reported_involved
confirmed_responder
rescued_by
intercepted_by
transporting_survivors
assigned_port

Do not use one generic "related vessel" field if the current architecture allows a richer relation.

--------------------------------------------------
15. WEATHER / SEA CONDITIONS
--------------------------------------------------

Where existing verified environmental data is available, allow humanitarian cases to show relevant context.

Potential fields:

- wind
- sea state
- wave height
- storm/hazard context

Only expose data from verified sources already available or explicitly integrated.

Weather should be contextual, not interpreted automatically as proof of distress.

Example:

Weather context
Wave height: 2.3 m
Wind: NW 18 kt

Avoid:

"dangerous conditions"

unless a defined threshold/policy supports it.

--------------------------------------------------
16. SOURCE STRATEGY
--------------------------------------------------

Strengthen humanitarian coverage by prioritizing robust first-party sources.

Audit the current source mix.

Preferred conceptual hierarchy:

TIER 1
Official/first-party operational sources

Examples:
- NGO official websites/RSS
- IOM
- UNHCR
- official coastguard / authority publications where available
- port authority notices
- official operational feeds

TIER 2
Verified NGO social accounts

TIER 3
Journalistic / OSINT reporting

TIER 4
Private partner reports

This is not necessarily a reliability ranking.

Private partner reports, for example, may be extremely valuable but require stronger privacy controls.

Use the hierarchy primarily to describe provenance and publication status.

--------------------------------------------------
17. SOCIAL SOURCES
--------------------------------------------------

Do not make X/Twitter or another social platform the structural foundation of humanitarian coverage.

Treat social channels primarily as:

early signals
and
source observations

rather than the canonical case database.

If Bluesky or other channels are added, they should enter the same source observation/correlation pipeline rather than becoming separate product silos.

--------------------------------------------------
18. PARTNER INTAKE
--------------------------------------------------

Review the existing WhatsApp / SMS / Telegram / external webhook architecture.

Do not build integrations merely because the code path exists.

However, prepare the humanitarian model so that verified partners can submit structured private reports.

Conceptual incoming report:

{
  "reported_people": 46,
  "boat_type": "rubber boat",
  "situation": "engine failure",
  "position": {...},
  "water_ingress": true,
  "last_contact": "...",
  "publish": false
}

This should become:

PRIVATE SOURCE OBSERVATION

not automatically:

PUBLIC LIVE CASE.

Operator approval / existing publication policy must remain authoritative.

--------------------------------------------------
19. HUMANITARIAN UI MODE
--------------------------------------------------

The existing Live dashboard should maintain the global mode switch:

[ HUMANITARIAN ] [ MARITIME SECURITY ]

When Humanitarian is selected, change the information architecture, not just marker visibility.

The primary object should be the CASE.

Example:

CASE #MED-031

DISTRESS REPORTED

~47 PEOPLE

Central Mediterranean

2 corroborating sources

STATUS
Ongoing

LAST VERIFIED UPDATE
18 min ago

The card should prioritize:

1. human situation
2. case status
3. reported number of people
4. location / area
5. time
6. verification
7. sources
8. operational context

Do not prioritize MMSI/IMO unless they are genuinely relevant to the humanitarian case.

--------------------------------------------------
20. MAP REPRESENTATION
--------------------------------------------------

Humanitarian markers should represent CASES where possible, not every source observation.

If three sources describe the same situation:

do not show three overlapping markers.

Show:

one case marker

with:

3 sources

Where coordinates are uncertain, indicate approximate location visually if the existing map architecture supports it.

Do not fabricate precise coordinates.

--------------------------------------------------
21. CASE DETAIL PANEL
--------------------------------------------------

Design or optimize the detail view around:

OVERVIEW

PEOPLE

STATUS

TIMELINE

SOURCES

VESSELS / OPERATIONAL CONTEXT

OUTCOME

Example:

DISTRESS CASE
Central Mediterranean

Reported people
~47

Status
Ongoing

Verification
Corroborated

First reported
14:02 UTC

Last verified update
17:46 UTC

Timeline
...

Sources
Alarm Phone
SOS MEDITERRANEE

Nearby assets
Ocean Viking — nearby, response not confirmed

This wording matters.

--------------------------------------------------
22. DO NOT OVER-AUTOMATE INTERPRETATION
--------------------------------------------------

The system should automate:

collection
normalization
deduplication
correlation
timeline construction
source provenance
geospatial context

It should be cautious about automating:

responsibility
intent
legality
causality
failure to rescue
state attribution

Those conclusions require stronger evidence and may belong in analytical/editorial layers rather than raw Live data.

--------------------------------------------------
23. HUMANITARIAN / SECURITY CROSSOVER
--------------------------------------------------

Allow the two modes to reference each other without collapsing them.

Example:

HUMANITARIAN CASE

Distress report
~47 people

Security context:
AIS gap detected on nearby vessel

This does NOT mean the AIS gap caused or relates to the distress case unless correlation evidence exists.

Likewise:

MARITIME SECURITY EVENT

AIS reporting gap
Sanctioned vessel

Nearby humanitarian case:
1 case within 20 nm

should be contextual only.

Never imply causality from proximity.

--------------------------------------------------
24. DATA QUALITY
--------------------------------------------------

Add explicit handling for:

unknown
approximate
conflicting
stale

Example:

people_reported:
source A = 47
source B = approximately 50

Do not silently resolve this to 48 or 50.

Represent the discrepancy.

Likewise:

one source says rescued
another says interception

should create a conflict requiring resolution, not silently choose one.

--------------------------------------------------
25. HUMANITARIAN SOURCE HEALTH
--------------------------------------------------

Source health matters especially for humanitarian monitoring.

For every important source, distinguish:

pipeline running

from:

source producing usable updates

Example:

Alarm Phone
pipeline: healthy
latest observation: 18 min ago

NGO RSS
pipeline: healthy
latest observation: 42 min ago

IOM
pipeline: healthy
latest dataset refresh: 2h ago

A successful poll is not equivalent to current coverage.

--------------------------------------------------
26. ARCHIVE / RESEARCH VALUE
--------------------------------------------------

Preserve enough structured history to make humanitarian cases usable later for research.

A resolved case should retain:

- original observations
- timeline
- source provenance
- status changes
- outcome
- relevant public vessel context
- confidence changes

Do not overwrite historical state with only the final status.

SeaCommons should be capable of reconstructing:

what was known
when it was known
from which source

This is important.

--------------------------------------------------
27. METRICS
--------------------------------------------------

Review current Humanitarian dashboard metrics.

Avoid vanity metrics based on number of scraped posts.

Prefer case-level metrics such as:

Active cases
Unresolved cases
Reported people
Cases resolved today
Median time since first report
Cases without update for >6h

Do not introduce metrics that cannot be supported reliably by current data.

Document which metrics are possible now versus which require additional integration.

--------------------------------------------------
28. IMPLEMENTATION PRIORITY
--------------------------------------------------

After auditing the current code, prioritize:

PHASE H1
Semantic cleanup
- correct humanitarian taxonomy
- stop generic misuse of distress
- distinguish report / operation / outcome

PHASE H2
Case model
- persistent humanitarian case entity
- source observations linked to case
- lifecycle/status

PHASE H3
Correlation
- deduplicate same incident across sources
- cautious confidence-based matching

PHASE H4
Timeline
- case event history
- first report / last update / outcome

PHASE H5
People-centered UI
- case cards
- humanitarian counts
- source provenance
- unresolved cases

PHASE H6
AIS / environmental context
- nearby vessels
- confirmed responder relationships
- weather context

PHASE H7
Partner intake readiness
- private source observations
- operator review
- publication controls

Do not attempt all phases as one monolithic rewrite.

--------------------------------------------------
29. REQUIRED AUDIT QUESTIONS
--------------------------------------------------

Before implementation, answer:

1. What humanitarian event types exist today?

2. What currently causes an event to be labelled "distress"?

3. Are NGO RSS, IOM, social posts and partner reports normalized into the same schema?

4. Does a persistent humanitarian case concept already exist?

5. Is there already correlation/deduplication between humanitarian sources?

6. How are people counts represented?

7. Can approximate quantities be represented?

8. How are location precision and privacy handled?

9. Is there an event lifecycle?

10. Are resolved events archived or overwritten?

11. Can the current API represent multiple sources for one case?

12. Can the current frontend render a timeline?

13. How are AIS vessels linked to humanitarian events?

14. Are nearby vessels currently interpreted as involved?

15. What are the current public-policy filters?

16. Which humanitarian sources are actually producing live data in production?

17. Which configured sources appear active but are stale/dead?

18. Which existing schemas/components can be reused instead of rewritten?

Reference exact files/functions/lines.

Do not guess.

--------------------------------------------------
30. TESTS
--------------------------------------------------

Add tests for scenarios such as:

SINGLE SOURCE

Alarm Phone reports 47 people in distress.

Expected:
one case
verification = single_source
not automatically officially_confirmed

MULTI-SOURCE SAME CASE

Alarm Phone + NGO report same area/time/people count.

Expected:
one case
two source observations
verification increases appropriately

POSSIBLE DUPLICATE

Two similar reports with insufficient evidence.

Expected:
do not merge automatically

PEOPLE COUNT

"around 50 people"

Expected:
approximate quantity preserved

CONFLICT

Source A reports 47
Source B reports 52

Expected:
conflict preserved
not silently averaged

AIS CONTEXT

SAR vessel 30nm from case.

Expected:
nearby
NOT responding unless confirmed

PRIVACY

Private partner report with exact coordinates.

Expected:
not exposed publicly without publication authorization

TIMELINE

Multiple updates to same case.

Expected:
historical updates retained in order

RESOLUTION

No new updates for several hours.

Expected:
case does NOT automatically become resolved

--------------------------------------------------
31. SUCCESS CRITERIA
--------------------------------------------------

The Humanitarian side is successful when:

- one real-world incident tends to become one case, not many cards
- source provenance remains visible
- uncertainty remains visible
- people, not vessels, are the primary subject
- users can understand what happened over time
- unresolved situations are easy to identify
- AIS enriches context without implying unsupported relationships
- private reports remain private
- humanitarian language remains precise
- raw social volume does not determine perceived importance

The goal is NOT to make the humanitarian feed busier.

The goal is to make it deeper, more coherent, more trustworthy and more useful.

--------------------------------------------------
FINAL OUTPUT FOR THIS MODULE
--------------------------------------------------

In addition to the outputs requested by the previous optimization prompt, provide:

1. Current humanitarian data-flow diagram

2. Current humanitarian schemas

3. Humanitarian taxonomy problems

4. Proposed Case / Observation model

5. Correlation strategy

6. Verification model

7. Privacy implications

8. Humanitarian API changes

9. Humanitarian UI changes

10. Metrics possible with current data

11. Metrics requiring new sources

12. Migration plan

13. Tests

14. Explicit list of things that should NOT be automated

Do not implement speculative integrations before showing the audit.