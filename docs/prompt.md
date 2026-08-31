Act as a Senior Computer Vision / Data Extraction Engineer on:

suezcanalxyz/seacommons

Focus exclusively on:

Alarm Phone X/Twitter
→ Twikit ingestion
→ media acquisition
→ image understanding
→ coordinate extraction

The current problem is that many Alarm Phone tweets contain operational
information and/or map screenshots but SeaCommons fails to extract useful
image data.

DO NOT begin by changing OCR thresholds.

First audit the complete media pipeline.

==================================================
1. TRACE CURRENT LIVE PIPELINE
==================================================

Trace:

Twikit tweet
→ tweet media discovery
→ quoted tweet media discovery
→ OCR scheduling
→ image download
→ EasyOCR
→ Tesseract
→ map pin detection
→ landmark matching
→ coordinate result
→ intel_store enrichment

Document every condition that can prevent an image from being analyzed.

Create:

docs/ALARM_PHONE_IMAGE_PIPELINE_AUDIT.md

Pay particular attention to the fact that image OCR is currently scheduled
only when:

distress == True
AND no explicit text coordinates
AND media_count > 0

Determine how many legitimate Alarm Phone image posts can be missed because
the text classifier runs before image understanding.

==================================================
2. FIX MEDIA ACQUISITION FIRST
==================================================

Create one canonical function:

resolve_x_media(tweet, tweet_id, quoted_tweet=None)

Sources in order:

1. Twikit media objects
2. extended_entities
3. entities
4. card images
5. fetch_tweet_photos(tweet_id) syndication fallback
6. quoted tweet syndication fallback

Deduplicate URLs.

Do not silently discard an image because Twikit changed object shape.

For pbs.twimg.com photos:

normalize requests to the highest available/original image resolution before
OCR.

Preserve only allowed HTTPS media hosts.

Return structured diagnostics:

media_source
original_url
resolved_url
media_count
failure_reason

==================================================
3. DECOUPLE IMAGE EXTRACTION FROM DISTRESS CLASSIFICATION
==================================================

Alarm Phone images must be eligible for image analysis even when the tweet
text has not yet been classified as distress.

Do not auto-publish based on image analysis.

Instead:

text assessment
+
image assessment
→ humanitarian recognition
→ publication policy

Add optional shadow mode:

ALARM_PHONE_IMAGE_V2_SHADOW=true

In shadow mode analyze images but do not alter public output.

==================================================
4. CREATE STRUCTURED IMAGE EXTRACTION
==================================================

Introduce:

core/intel/image_extraction.py

with a typed result:

ImageExtractionResult

Fields:

image_kind
detected_text
coordinate_candidates
selected_coordinate
coordinate_method
coordinate_confidence
place_names
people_counts
distress_terms
pin_detected
landmarks_used
ocr_engines
evidence
failure_reasons

image_kind:

map_screenshot
text_card
infographic
photo
unknown

Do not reduce the image pipeline to "coordinate or None".

==================================================
5. MAP SCREENSHOT PIPELINE
==================================================

For map screenshots run:

A. original-resolution fetch

B. ROI detection

C. multiple preprocessing variants:
   - original RGB
   - grayscale
   - autocontrast
   - adaptive threshold
   - inverted high-contrast
   - 2x / 3x ROI upscale

Avoid multiplying full-image OCR unnecessarily.
Detect likely text regions first.

D. EasyOCR region detection

E. Tesseract coordinate-specific passes

F. coordinate candidate parser

G. consensus scoring

A coordinate should have confidence components including:

parser validity
engine agreement
OCR confidence
Mediterranean/operational-region validity
context agreement
landmask validity

Do not accept arbitrary numeric text.

==================================================
6. IMPROVE PIN DETECTION
==================================================

Current color masks are useful but fragile.

Keep them as one detector.

Add a second shape-based detector using:

HSV/high saturation
connected components
contours
compactness
aspect ratio
teardrop/circle geometry

Return every candidate with confidence.

Only select a pin when evidence is sufficiently unambiguous.

==================================================
7. IMPROVE LANDMARK GEOLOCATION
==================================================

Replace raw linear latitude fitting with Web Mercator.

Process:

known landmark WGS84
→ Web Mercator
→ robust pixel transform
→ pin pixel
→ inverse Mercator
→ candidate coordinate

Prefer >= 3 landmarks.

Allow 2 landmarks only with lower confidence and strict validation.

Use RANSAC / robust outlier rejection when enough labels exist.

Record:

landmarks_detected
landmarks_used
fit_residual_px
extrapolation_distance
estimated_position_error_m

Never fabricate a location when fit quality is poor.

==================================================
8. USE TWEET CONTEXT AS A CONSTRAINT
==================================================

Tweet text may mention:

Sfax
Tunisia
Libya
Crete
Lampedusa
etc.

Use those only as constraints on image interpretation.

Example:

OCR map candidate near Sfax
+
tweet says "#Sfax"
→ stronger confidence.

Do NOT move the image-derived pin to the text centroid.

Image evidence remains independent.

==================================================
9. EXTRACT MORE THAN COORDINATES
==================================================

For text cards / image annotations, extract structured candidates for:

people aboard
people rescued
missing
dead
injured
vessel condition
engine failure
taking water
distress
rescue requested
place names

Every extracted value must preserve its OCR evidence string.

The humanitarian classifier decides semantics later.

==================================================
10. OBSERVABILITY
==================================================

For every Alarm Phone image persist safe diagnostic metadata:

media_discovered
media_source
image_fetch_ok
image_dimensions
image_kind
easyocr_attempted
easyocr_box_count
tesseract_attempted
coordinate_candidate_count
pin_detected
landmark_count
selected_method
confidence
failure_reason

Never log/private-store unnecessary image contents.

==================================================
11. BUILD A BENCHMARK
==================================================

Use a controlled local evaluation set of historical PUBLIC Alarm Phone tweets.

Do not commit third-party image files unless licensing clearly permits it.

For each test item store ground truth:

tweet_id
image_type
has_coordinate_text
has_pin
expected_coordinate
tolerance_km

Measure V1 and V2:

media retrieval recall
OCR attempt rate
coordinate recall
coordinate precision
false coordinate rate
median coordinate error km
pin detection recall

False coordinates are more costly than missing coordinates.

Optimize precision first.

==================================================
12. REUSE BACKFILL
==================================================

Update:

core/intel/backfill_alarm_phone.py

to optionally run both V1 and V2 and output a comparison report.

Example:

python -m core.intel.backfill_alarm_phone \
  --benchmark \
  --limit 100

Output:

media found
map images
text coordinate extracted
pin coordinate extracted
failed
confidence distribution
V1/V2 disagreements

No database changes in benchmark mode.

==================================================
13. TESTS
==================================================

Add synthetic regression fixtures representing:

- coordinate popup
- tiny coordinate text
- dark popup
- quoted tweet map
- red pin
- blue pin
- yellow circular pin
- no coordinate + 3 map labels
- image with unrelated numbers
- map without sufficient landmarks
- low-resolution preview
- false place OCR

A wrong coordinate must fail closed.

==================================================
FIRST RESPONSE
==================================================

Before implementing, report:

1. current media acquisition failure points
2. current OCR failure points
3. current pin-geolocation failure points
4. why images can be skipped before OCR
5. proposed V2 architecture
6. exact files to modify
7. evaluation strategy
8. ordered PR plan

Then wait for approval.

You are acting as a Senior Maritime Data / Detection Engineer working on:

suezcanalxyz/seacommons

GOAL

Improve SeaCommons alert recognition and interpretation without increasing
false positives or weakening privacy/publication safeguards.

This work has four objectives:

1. Replace generic per-type "Interpretation" text with case-specific,
   evidence-based interpretations.

2. Build a substantially stronger Humanitarian Recognition V2 pipeline.

3. Restore "Vessel unable to manoeuvre" / AIS nav status 2 to public Live
   as SAFETY CONTEXT, not as a distress alert.

4. Re-audit and recalibrate AIS spike/anomaly detection and taxonomy.

DO NOT start by changing thresholds.

First establish a measurable baseline.

==================================================
PHASE 0 — AUDIT CURRENT DECISION PIPELINE
==================================================

Trace the full lifecycle for:

- Alarm Phone distress report
- humanitarian update
- AIS nav status 2 / not_under_command
- AIS nav status 6 / aground
- sudden_stop
- vessel_loiter
- rescue_cluster
- ngo_search_pattern
- AIS gap
- impossible_speed
- dark_zone_entry
- correlated_alert

Document:

raw observation
→ detector/classifier
→ IntelEvent
→ metadata
→ maritime_domain
→ severity
→ publication_status
→ public policy
→ Live feed
→ frontend category
→ report interpretation

Create:

docs/ALERT_RECOGNITION_AUDIT.md

For every signal record:

- source
- raw evidence
- rule that fired
- thresholds
- confidence
- current category
- current publication behaviour
- known false-positive modes
- known false-negative modes

Do not modify behaviour until the audit exists.

==================================================
PHASE 1 — STOP USING STATIC TYPE DESCRIPTIONS
==================================================

Current problem:

ConePanel displays:

Interpretation = descriptionOf(props.type)

This produces nearly identical interpretation text for every event of the
same type.

Keep descriptionOf() only as a CATEGORY EXPLANATION.

Create a separate case-specific assessment layer.

Suggested architecture:

apps/api/core/intel/assessment.py

and/or a corresponding frontend presentation adapter.

Introduce a structured model similar to:

EventAssessment:
    observation
    interpretation
    evidence_level
    confidence
    confidence_basis[]
    supporting_evidence[]
    contradicting_evidence[]
    caveats[]
    recommended_action
    rule_ids[]
    classification_version

Do NOT generate generic prose from event.type.

Interpretation must use the actual evidence attached to that event.

Examples:

NOT UNDER COMMAND:

Observation:
"AIS navigation status 2 persisted across 4 reports over 13 minutes."

Interpretation:
"The vessel is reporting itself as not under command, meaning it may be
unable to manoeuvre as required. This is an AIS-transponder observation,
not confirmation of mechanical failure."

If GNSS jamming is present:

"Position also overlaps a current GNSS interference area, increasing the
operational relevance of the navigation-status report but not proving
causation."

SUDDEN STOP:

Observation:
"Speed changed from 8.2 kn to 0.2 kn between observations."

Interpretation:
"An abrupt stop was detected outside the current port exclusion model.
This can indicate an incident, rendezvous, anchoring, traffic conditions
or ordinary manoeuvring; additional track evidence is required."

RESCUE CLUSTER:

Interpretation must state exactly:

- number of vessels
- distances
- which vessel is NGO/SAR
- freshness of positions
- whether vessels were actually converging
- proximity to active humanitarian distress

Never call proximity alone a confirmed rescue.

AIS GAP:

Interpretation must include:

- last AIS position
- silence duration
- previous speed
- local AIS coverage health
- nearby-vessel reporting state
- whether the location is a known low-coverage area

Never describe a reception outage as intentional dark activity.

==================================================
PHASE 2 — HUMANITARIAN RECOGNITION V2
==================================================

Current humanitarian_case_metadata() is too shallow.

Do not simply add more regexes into one function.

Create a dedicated module:

core/intel/humanitarian_recognition.py

with explicit extraction stages.

Create a HumanitarianAssessment schema containing:

incident_type:
    distress
    shipwreck
    missing_persons
    interception
    pushback
    medical_emergency
    rescue
    disembarkation
    arrival
    death_report
    retrospective_incident
    humanitarian_update

lifecycle:
    active
    ongoing
    needs_review
    resolved
    concluded

people:
    aboard
    rescued
    missing
    dead
    injured
    children
    women
    approximate

vessel:
    type
    condition
    engine_failure
    taking_water
    capsized
    overcrowded

needs:
    rescue
    medical
    food_water
    fuel
    disembarkation

actors:
    reporting_source
    authorities_contacted[]
    rescue_actor
    interception_actor

location:
    source
    precision
    uncertainty
    explicit_vs_inferred

temporal:
    report_time
    incident_time
    last_contact_time
    retrospective

evidence:
    source_type
    direct_report
    corroborating_sources
    confidence
    uncertainty_reasons[]

Never infer unavailable facts.

Distinguish carefully:

"rescued" != automatically "case resolved"

For example:

rescued + denied disembarkation
rescued + pushback risk
rescued + people still missing

must remain ongoing where appropriate.

Handle multiple quantities correctly.

Example:

"45 people aboard, 12 rescued, 3 missing"

must NOT become simply:

people_reported = 45

Store semantically distinct counts.

Support at least:

English
Italian
French

using deterministic normalization first.

==================================================
PHASE 3 — BUILD A REAL EVALUATION DATASET
==================================================

Before "fine tuning", build an evaluation corpus.

Create:

tests/fixtures/alert_recognition/

humanitarian.jsonl
ais_status.jsonl
ais_behaviour.jsonl
ais_integrity.jsonl

Use real PUBLIC examples already available to SeaCommons where legally and
ethically appropriate.

Sanitize anything private.

Each fixture must contain:

input
expected classification
expected lifecycle
expected entities
expected public/private decision
expected confidence range
notes

Include hard negatives.

Examples:

"SOS Mediterranee published its annual report"
must NOT be distress.

"A vessel is moored in Valletta"
must NOT be a sudden-stop alert.

"Not under command" sustained for 12 minutes
IS a vessel-status observation.

"Restricted manoeuvrability" from a dredger
must NOT be treated as unable-to-manoeuvre casualty.

A cluster of NGO vessels inside a port
must NOT be labelled rescue operation.

A feed-wide AIS outage
must NOT create hundreds of vessel-specific AIS gaps.

Measure per-class:

precision
recall
F1
false-positive count
false-negative count

For auto-public decisions, optimize primarily for precision.

Do not claim an improvement unless the evaluation corpus demonstrates it.

==================================================
PHASE 4 — RESTORE "UNABLE TO MANOEUVRE" CORRECTLY
==================================================

Current behaviour:

AIS nav status 2
→ not_under_command
→ medium
→ publication_status=internal
→ maritime_domain=grey_zone
→ absent from Humanitarian Live

Change the semantics.

AIS navigation status 2 should normally be:

type = vessel_incident
ais_nav_status_kind = not_under_command
maritime_domain = safety
kind = context
severity = medium
verification_status = ais_transponder

It must NOT automatically become:

distress
grey_zone
security threat
mechanical failure

Only promote/relate it to grey_zone when independent evidence exists, e.g.:

- GNSS jamming
- spoofing
- impossible movement
- infrastructure correlation
- another independent security signal

Keep the sustained-observation requirement.

Do not reduce it blindly.

Initially retain:

>= 3 reports
>= 10 minutes

but make thresholds configurable and evaluate them from the fixture dataset.

Public presentation:

"Unable to manoeuvre — AIS reported"

Caveat:

"AIS navigation status reported by the vessel; operational cause is not independently confirmed."

It should be visible as contextual vessel safety information,
NOT rendered as a red humanitarian distress call.

==================================================
PHASE 5 — FIX HUMANITARIAN LIVE POLICY
==================================================

Current architecture contains blanket Alarm Phone filtering in both:

- useLiveFeed.js
- live_edge_publisher.py

Humanitarian mode must not mean "Alarm Phone only".

It should mean:

HUMANITARIAN PRIMARY SIGNALS
+ RELEVANT MARITIME SAFETY CONTEXT

Define one canonical server-side policy.

Suggested:

core/live/mode_policy.py

humanitarian mode may contain:

A. Direct humanitarian distress / updates
   from explicitly permitted humanitarian sources.

B. Relevant vessel safety context:
   - not_under_command
   - aground
   - distress beacon

C. Carefully selected SAR-response context once detection quality is proven.

It must NOT include by default:

- sanctions matches
- grey-zone intelligence
- IUU fishing
- generic AIS anomalies
- arbitrary news
- low-confidence security correlations

Do not rely on frontend filtering for security/privacy.

The backend/public projection is authoritative.

Remove alarmPhoneOnly() as an authorization/publication mechanism.

The frontend may filter presentation, never decide data eligibility.

Ensure VM Live and Edge Live use the SAME canonical policy.

Add parity tests.

==================================================
PHASE 6 — SEPARATE AIS TAXONOMY
==================================================

Current frontend category:

"AIS anomaly / spike"

is too broad.

Separate at least:

1. AIS VESSEL STATUS
   vessel_incident
   - not_under_command
   - aground
   - distress beacon

2. AIS BEHAVIOURAL CUE
   ais_spike
   - sudden_stop
   - vessel_loiter
   - ngo_search_pattern
   - rescue_cluster

3. AIS INTEGRITY / SIGNAL ANOMALY
   ais_anomaly
   - gap
   - impossible_speed
   - dark_zone_entry
   - duplicate identity / spoofing indicators

4. FUSED ALERT
   correlated_alert

5. VERIFIED / DIRECT HUMANITARIAN EVENT
   distress / humanitarian incident

Never use "spike" as the primary human-facing explanation.

The UI should show the specific subtype.

==================================================
PHASE 7 — RE-AUDIT AIS SPIKE DETECTOR
==================================================

Audit AISSpikeDetector carefully.

Known questions that MUST be checked:

A. RESCUE_CLUSTER

CLUSTER_AGE_S exists but _check_clusters() currently does not appear to
enforce vessel-position freshness.

Fix this.

A rescue cluster must require fresh positions.

Also distinguish:

proximity
vs
convergence.

Two vessels merely being within 3 nm is not proof of convergence.

Evaluate:

- relative movement
- decreasing distance
- vessel speeds
- course
- time together
- port/anchorage context
- active distress proximity

Rename low-confidence result if necessary:

possible_rescue_cluster

not:

rescue_cluster

B. SUDDEN_STOP

Current rule is approximately:

previous speed >= 3 kn
current speed <= 0.4 kn
outside known port

This is too weak alone.

Evaluate:

- AIS nav status
- persistence
- track displacement
- port/anchorage proximity
- traffic separation areas
- vessel type
- feed freshness

A one-sample speed transition should normally be a cue,
not a high-confidence alert.

C. VESSEL_LOITER

The documentation says anchored vessels should be excluded.

Verify that the implementation ACTUALLY has nav-status evidence to do this.

Exclude, where appropriate:

at anchor
moored
restricted manoeuvrability caused by known vessel work
port/anchorage operations

D. NGO_SEARCH_PATTERN

A large course change at low speed can occur normally.

Require sufficient track history.

Evaluate:

- number of fixes
- time window
- turn sequence
- area covered
- repeated pattern
- proximity to distress
- known operational role

Proximity to an active distress should increase relevance,
but never prove response.

==================================================
PHASE 8 — FIX AIS GAP LOGIC
==================================================

A vessel-specific AIS gap cannot be inferred reliably from silence alone.

Before calling something a vessel AIS gap, compute local/feed coverage health.

Compare the missing vessel against nearby vessels.

If nearby AIS traffic also disappears simultaneously:

classify as:

coverage_gap / source_outage

NOT:

vessel_gap

Useful features:

nearby_vessels_reporting_before
nearby_vessels_reporting_after
local_reporting_ratio
feed_health
last_known_speed
silence_duration
distance_from_known_low_coverage_area

Only escalate vessel-specific gaps when surrounding coverage remains healthy.

==================================================
PHASE 9 — CONFIDENCE MODEL
==================================================

Do not assign confidence ad hoc.

Introduce a traceable score.

Example dimensions:

source_reliability
observation_freshness
rule_strength
persistence
location_precision
independent_corroboration
coverage_quality
context_support
contradicting_evidence

Store:

confidence
confidence_components
rule_id
classification_version

Every alert must be explainable.

==================================================
PHASE 10 — OPTIONAL AI / LLM CLASSIFIER
==================================================

Do NOT fine-tune or introduce an LLM before the deterministic benchmark exists.

If humanitarian-language ambiguity remains high after deterministic parsing,
introduce an OPTIONAL second-stage classifier.

It must:

- accept only the public report text + structured source metadata
- return constrained JSON
- never invent locations/counts/actors
- include evidence spans from the original text
- include confidence
- support abstention
- never auto-publish an event by itself

Suggested output:

{
  "incident_type": "...",
  "lifecycle": "...",
  "people": {...},
  "needs": [...],
  "evidence": [
    {"field": "...", "quote": "..."}
  ],
  "confidence": 0.0,
  "abstain": false
}

The deterministic pipeline remains authoritative for hard safety/privacy gates.

==================================================
PHASE 11 — SHADOW MODE
==================================================

Add:

ALERT_RECOGNITION_V2=true|false
ALERT_RECOGNITION_V2_SHADOW=true|false

Shadow mode:

- run V1
- run V2
- store/log decision differences
- DO NOT change public Live output

Produce metrics:

classification disagreement
publish disagreement
severity disagreement
lifecycle disagreement
category disagreement

No sensitive text in logs.

Use shadow mode before switching production behaviour.

==================================================
PHASE 12 — TESTS
==================================================

Add regression tests proving at least:

- every case gets event-specific interpretation
- two events of the same type can produce different interpretations
- NUC becomes safety context
- NUC remains non-distress
- sustained NUC appears in Humanitarian Live context
- NUC with jamming does not automatically become a confirmed security event
- restricted manoeuvrability is distinct from not under command
- stale vessels cannot create rescue clusters
- mere proximity is not labelled convergence
- anchored/moored stop is not a sudden-stop casualty
- feed-wide AIS outage is not interpreted as vessel-specific gaps
- Alarm Phone distress remains visible
- non-humanitarian security data remains excluded from humanitarian mode
- VM and edge mode policies remain identical

==================================================
PHASE 13 — OUTPUT
==================================================

Do NOT immediately implement everything.

First return:

1. exact current root cause for generic Interpretation
2. exact current root cause for Humanitarian mode behaviour
3. exact current root cause for missing not_under_command on Live
4. current AIS spike rules and their false-positive risks
5. proposed new taxonomy
6. proposed HumanitarianAssessment schema
7. proposed EventAssessment schema
8. proposed evaluation corpus
9. files to change
10. ordered PR plan

Then implement as separate PRs:

PR 1 — recognition benchmark + fixtures
PR 2 — EventAssessment + dynamic interpretation
PR 3 — Humanitarian Recognition V2
PR 4 — canonical Live mode policy + restore NUC as safety context
PR 5 — AIS taxonomy split
PR 6 — spike detector calibration
PR 7 — AIS coverage-aware gap detection
PR 8 — shadow-mode metrics and production cutover

Do not merge PRs automatically.

Preserve current production behaviour until tests and shadow-mode evidence
justify each cutover.