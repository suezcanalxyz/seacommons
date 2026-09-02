# OCR and Drift Runtime Stabilization Design

**Date:** 2026-09-02
**Status:** Proposed for implementation
**Scope:** Alarm Phone image extraction, location evidence, operational marine forcing, and Live projection

## Context

The production runtime is the current systemd deployment in
`/home/ubuntu/seacommons/apps/api`, running revision
`d48bb4011bbc368874c3f2df67c995d2c82a0d9d`. Read-only inspection confirmed
that EasyOCR, Tesseract, Pillow, OpenDrift, and Copernicus Marine are installed.

Eight recent Alarm Phone records had stored media but no image-derived
coordinate. Four were never scheduled for OCR because their text was classified
as non-distress. A read-only shadow replay recovered a valid Tesseract
coordinate from one of those four. All eight downloads succeeded and all eight
contained OCR-detected text, but the runtime stores only `ocr_attempted` and a
final coordinate-or-none result. It cannot distinguish text detection, parser
rejection, popup/pin failures, or engine disagreement.

The drift runtime combines CMEMS currents with Open-Meteo wind, current, and
wave inputs. It currently derives forcing quality from reader construction,
not successful per-variable samples. A completely fallback-filled
Open-Meteo grid can therefore be labelled spatiotemporal and operational.
Production logs also repeat CMEMS depth-selection warnings for `[0.0, 1.0]`
against a shallowest available level near `0.494 m`.

## Goals

1. Analyze eligible Alarm Phone images without requiring a prior positive text
   distress classification, initially in shadow mode.
2. Preserve structured, privacy-minimized evidence for every image-processing
   stage.
3. Prevent a coordinate from becoming operational merely because an OCR parser
   returned a numeric pair.
4. Permit Drift only from explicitly eligible, verified location evidence.
5. Record the source and derivation of every marine forcing variable.
6. Correct CMEMS depth selection against the dataset coordinates.
7. Make forcing quality describe actual data coverage, fallbacks, spatial
   resolution, and temporal resolution.
8. Keep public Live behavior unchanged until shadow evidence and tests support
   a separate cutover.

## Non-goals

- No production database mutation, service restart, systemd change, secret
  change, deployment, or merge.
- No automatic publication based solely on image analysis.
- No acceptance of arbitrary OCR numeric text.
- No claim that the Open-Meteo application's 1-degree query lattice is the
  provider model's native resolution.
- No bathymetry integration in this stabilization change.

## Design 1: Canonical X media resolution

Create one resolver used by live ingestion and historical reprocessing:

```python
def resolve_x_media(
    tweet: object,
    tweet_id: str,
    quoted_tweet: object | None = None,
) -> XMediaResolution
```

`XMediaResolution` contains a tuple of media items plus privacy-safe failure
diagnostics. Each item records `media_source`, `original_url`, and
`resolved_url`. The resolver checks typed Twikit media, extended entities,
entities, cards, syndication for the primary tweet, and syndication for the
quoted tweet. It never stops searching merely because an earlier shape
contained an unusable URL. It deduplicates normalized HTTPS URLs and permits
only the existing host allow-list. `pbs.twimg.com` images are normalized to the
original rendition before OCR.

Transport diagnostics record counts and enumerated failure reasons, not post
text, cookies, headers, or other personal data.

## Design 2: Structured image extraction

Create `core/intel/image_extraction.py` with immutable result types:

```python
@dataclass(frozen=True)
class CoordinateCandidate:
    coordinate: tuple[float, float]
    engine: str
    preprocessing: str
    parser_format: str
    parser_valid: bool
    region_valid: bool
    sea_valid: bool
    confidence: float | None

@dataclass(frozen=True)
class ImageExtractionResult:
    image_kind: str
    text_detected: bool
    detected_text_digest: str | None
    detected_text_length: int
    coordinate_candidates: tuple[CoordinateCandidate, ...]
    selected_coordinate: tuple[float, float] | None
    coordinate_method: str | None
    coordinate_confidence: float | None
    place_names: tuple[str, ...]
    people_counts: tuple[int, ...]
    distress_terms: tuple[str, ...]
    pin_detected: bool
    popup_detected: bool
    landmarks_detected: tuple[str, ...]
    landmarks_used: tuple[str, ...]
    ocr_engines: tuple[str, ...]
    downloaded: bool
    failure_reasons: tuple[str, ...]
```

Raw detected text is used transiently for parsing and semantic recognition but
is not logged. Diagnostics persist a digest, length, recognized safe landmark
names, parser formats, candidate coordinates, confidence, and failure reasons.
This differentiates download failure, no text, parser rejection, invalid
coordinate, engine disagreement, no popup, no pin, and insufficient landmarks.

The pipeline operates on the original-resolution image, identifies likely
regions of interest, then applies bounded preprocessing variants to regions
rather than multiplying full-image OCR indiscriminately. Existing EasyOCR and
Tesseract behavior remains available behind adapters so regression fixtures can
compare old and new extraction.

## Design 3: Coordinate parsing and consensus

Coordinate parsing returns every candidate with an explicit matched format and
validation state. It supports the already accepted formats plus observed OCR
variants such as missing degree/prime glyphs, suffix DMM, and labelled decimal
components. Candidate acceptance still requires:

- latitude/longitude numeric bounds;
- operational-region validation;
- hemisphere consistency;
- maritime/landmask validation recorded separately;
- contextual agreement when the post supplies a place constraint.

Consensus is calculated geodesically in metres. A single-engine parse may be
retained as review evidence but never becomes verified automatically.
Disagreement is preserved as competing candidates rather than resolved by
silently preferring one engine.

## Design 4: Popup, pin, and landmark analysis

Popup detection becomes an explicit result rather than an internal crop list.
Pin detection retains the current colour masks and adds a contour/connected-
component detector based on saturation, compactness, aspect ratio, and
circle/teardrop geometry. Every candidate retains its confidence and detector.
Selection requires an unambiguous best candidate.

Landmark geolocation uses Web Mercator coordinates, not an independent linear
fit in latitude and longitude. Three or more landmarks are preferred and use
robust outlier rejection. Two-landmark results are permitted only as low-
confidence review evidence with strict spread, extrapolation, residual, region,
and landmask checks. Results record landmarks detected/used, fit residual,
extrapolation distance, and estimated positional error.

## Design 5: Recognition and publication boundary

Alarm Phone media analysis eligibility is independent of the V1 text distress
decision. Two configuration flags control rollout:

```text
ALARM_PHONE_IMAGE_V2_ENABLED=false
ALARM_PHONE_IMAGE_V2_SHADOW=true
```

In shadow mode the image is analyzed and technical metrics are emitted, but
stored public classification, location, publication, notification, and Drift
behavior remain unchanged. Image semantic findings and text assessment feed a
future humanitarian recognition decision only after evaluation; image analysis
alone cannot publish an event.

The existing bounded queue remains the execution boundary. Queue rejection is
retryable and observable; `dropped` is not a terminal silent state.

## Design 6: Location evidence and Drift eligibility

`LocationEvidence` is the sole conversion boundary from extraction candidates
to a stored operational position. It includes coordinate source, review state,
uncertainty, engine agreement, parser validity, region validity, sea validity,
and whether human verification occurred.

The quality order is evidence-based, not source-string-only. A disputed or
single-engine candidate can be stored for review but cannot supersede verified
evidence. Drift uses one shared eligibility predicate for automatic, manual,
backfill, API, and recomputation paths. `force=True` may bypass job
deduplication only; it never bypasses evidence eligibility.

Initial automatic Drift allow-list:

```text
reported_exact
machine_ocr_consensus_verified
human_verified
```

Additional requirements remain: active operational SAR case, positioned
maritime location, uncertainty within the configured limit, in-region sea
coordinate, and no disputed/needs-review state.

## Design 7: Marine forcing observations

Represent each forcing component with a value plus provenance:

```python
@dataclass(frozen=True)
class ForcingObservation:
    variable: str
    value: float
    unit: str
    source: str
    derivation: str  # fetched | calculated | interpolated | cached | fallback
    provider_time: datetime | None
    fetched_at: datetime | None
    native_resolution: str | None
    sampling_resolution: str | None
    valid: bool
    fallback_reason: str | None
```

Wind and current vector components are recorded as calculated from fetched
speed/direction. Stokes components are recorded as calculated from fetched wave
height, period, and direction. Cache use and constant fills are explicit.
Provider-native resolution is separate from the application's query lattice.

## Design 8: CMEMS depth correction

Do not hardcode `[0.0, 1.0]` against a dataset whose shallowest coordinate is
`~0.494 m`. For point reads, omit the depth constraint when the client supports
nearest-coordinate selection, or first inspect the dataset depth coordinate and
request its shallowest available value. For subset files, retain a bounded
surface layer but derive the minimum from provider metadata and verify the
selected level after opening the result.

The selected physical depth and selection method are stored in forcing
metadata. Tests use datasets whose shallowest levels differ so the fix cannot
silently regress to a magic number.

## Design 9: Open-Meteo and OpenDrift reader quality

`_fetch_grid()` returns both arrays and a coverage report containing successful
point/time counts per variable, constant-fill percentage, cache/fallback use,
and provider errors. Building `_GridReader` is not itself evidence of valid
spatiotemporal data.

CMEMS governs currents only within its valid domain. Open-Meteo governs wind,
fallback current, and optional wave-derived Stokes. Constant forcing remains a
degraded last resort. The CMEMS timeout implementation must not block on
executor shutdown after timeout; cancellation/cleanup must be explicit and the
eventual provider task must not overwrite a discarded cache path.

Forcing quality is computed per variable and summarized conservatively:

- `observed-spatiotemporal`: required variables have valid varying provider
  samples over the simulation domain/time;
- `mixed`: at least one required variable is valid spatiotemporal and another
  relies on cache or constants;
- `degraded-cached`: required forcing is entirely cached/stale;
- `degraded-constant`: any required forcing is constant fallback with no valid
  provider coverage;
- `invalid`: required variables are missing or non-finite.

`operational_use` is true only for policy-approved quality states; initially
only `observed-spatiotemporal`. Missing waves mean zero Stokes and explicit
`wave_data_available=false`, not failure of the required current/wind forcing.

## Design 10: Live API and UI projection

Persist and project a compact forcing summary containing per-variable source,
derivation, provider/sampling resolutions, selected current depth, coverage,
Stokes status, and overall quality. Live never publishes a degraded or invalid
trajectory as operational. The UI labels mixed/cached/constant data accurately
and never presents calculated Stokes drift as a directly measured current.

Public semantics remain unchanged during shadow mode. A later cutover requires
fixture results, production shadow metrics, and explicit approval.

## Error handling and observability

All network, OCR, parser, and reader boundaries return enumerated failure
reasons. Logs contain event IDs, image counts, byte sizes, engine/stage names,
candidate coordinates, and technical states only. They exclude post bodies,
raw OCR text, cookies, authorization values, and image payloads.

Metrics cover media-source success, download outcomes, OCR engine attempts,
text-detected/parser-rejected counts, candidate/evidence outcomes, queue retry,
forcing valid-sample coverage, fallback derivations, depth selection, reader
activation, and projection rejection reasons.

## Testing strategy

Implementation follows red-green-refactor for every behavior change.

1. Media fixtures cover every Twikit shape, syndication fallback, quoted media,
   URL normalization, deduplication, and host rejection.
2. OCR fixtures cover text detected/no parse, newly supported formats, competing
   candidates, popup/no-popup, pin/no-pin, insufficient landmarks, robust
   landmark fitting, and privacy-safe diagnostics.
3. Location tests prove single-engine/disputed evidence cannot trigger Drift or
   supersede verified evidence, including forced recomputation and backfill.
4. CMEMS fake datasets cover dynamic shallowest-depth selection and prove no
   `[0.0, 1.0]` warning-producing request.
5. Open-Meteo grid tests cover full success, partial fill, total failure, unit
   conversion, hourly interpolation, and wave absence.
6. OpenDrift tests cover reader precedence, Leeway/OceanDrift selection,
   Stokes enablement, per-variable provenance, and every forcing-quality state.
7. Projection tests prove degraded results do not enter operational Live and
   mixed provenance is represented accurately.
8. Verification uses `apps/api/.venv/bin/python -m pytest` because the venv has
   the pytest module but no standalone pytest script, then the relevant full
   backend suite, frontend type/build checks if frontend code changes, read-only
   API/DB smoke checks, and service-log validation.

## Rollout and safety

Repository implementation and tests may proceed locally. No production action
is included. After review, production rollout would require a separate,
explicitly authorized sequence: deploy code, enable shadow flags only, observe
metrics, review false positives/negatives, approve semantic cutover, then enable
V2 behavior. Database backfills and service restarts remain separately gated.

## Acceptance criteria

- Every analyzed image yields a structured result explaining each pipeline
  stage without exposing raw sensitive text.
- A production-equivalent fixture reproduces the classifier-gated coordinate
  miss and passes under shadow analysis without changing publication.
- No OCR coordinate becomes Drift-eligible without verified evidence.
- CMEMS requests select a real available surface depth without repeated range
  warnings.
- Forcing metadata distinguishes fetched, calculated, interpolated, cached, and
  fallback values per variable.
- Total provider failure cannot be labelled spatiotemporal or operational.
- Targeted and full available checks pass from the project venv.
- No production data or service state is changed.
