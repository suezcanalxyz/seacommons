# Alarm Phone image pipeline audit

> **Status:** deep trace of the live X/Twitter → image → coordinate path as it
> stands on `main` at `d412e92`, written before any threshold change (per
> `docs/prompt.md` §1). Companion to `docs/OCR_AND_DRIFT_PIPELINE_AUDIT_2026-09-02.md`
> (which covers the drift side) and `docs/fixes.md` F-01…F-05 (evidence gate,
> bounded queue, geodesic consensus).

## 0. Scope

Alarm Phone posts operational SAR information on X, very often as a **map
screenshot** (basemap + place labels + a coordinate popup, or just a drop
pin). SeaCommons frequently fails to turn those images into a usable
position. This document traces every stage and every condition that can stop
an image from being analysed, so the V2 work is grounded in the real failure
set rather than in "the OCR threshold is probably wrong".

---

## 1. Current live pipeline trace

```
twikit poll (≈45 s loop, TwikitMonitor._ingest)
  → retweet?  → _thread_repost (no new marker)                          [A]
  → quote of tracked incident?  → _thread_repost                        [A]
  → reply to tracked incident?  → _thread_reply                         [A]
  → own_text + quoted_text  → combined_text
  → distress = is_direct_distress_call(combined_text)                   [B]
  → text_coords = extract_numeric_coords(combined_text) IF distress     [C]
  → media_urls = _tweet_media_urls(tweet) + _tweet_media_urls(quoted)   [D]
  → translation twin?  → _thread_translation(…, media_urls)             [A]
  → ocr_available = which("tesseract") or find_spec("easyocr")
  → alarm_phone_image_v2 = handle in {alarm_phone,alarmphone}
                           AND config.ALARM_PHONE_IMAGE_V2_ENABLED
  → OCR SCHEDULED IFF:
        (distress OR alarm_phone_image_v2)
        AND NOT text_coords
        AND media_count > 0
        AND ocr_available                                               [E]
     else if (media_count AND not text_coords AND handle is Alarm Phone
              AND config.ALARM_PHONE_IMAGE_V2_SHADOW AND ocr_available)
        → shadow OCR (analyse, never enrich)                            [E]
  → relative_coords / place_coords / area_result (text only)            [F]
  → IntelEvent persisted with a *fallback* coordinate (place centroid / area)
  → added?  → _schedule_media_ocr(tweet_id, event.id, media_urls)
        → media_ocr_queue.submit("x-ocr:<event_id>", …)   (bounded pool) [G]
             → _apply_media_ocr(event_id, urls)
                  → _ocr_tweet_media: for each url → _ocr_photo(url)     [H]
                       → download (≤8 MiB, pbs.twimg.com only)          [I]
                       → _easyocr_image  (neural, small-text detection) [J]
                            → extract_numeric_coords(joined text)
                            → if coord: _tesseract_cross_check          [K]
                                 → consensus | disputed | easyocr_text
                       → else Tesseract sweep:
                            popup-band detection + 4 fixed bands
                            × 6 PSM/whitelist variants                  [L]
                            → consensus_ocr_coordinate
                       → else geolocate_pin_from_image                  [M]
                            → colour pin mask → 1 shape heuristic
                            → tesseract word boxes (2 pass + 2×2 tiles)
                            → _match_landmarks vs PRECISE_PLACES
                            → ≥2 landmarks → linear per-axis polyfit
                            → nearest_sea_point
                  → evidence_from_ocr_method(method, lat, lon, …)       [N]
                  → intel_store.enrich_location(…)                       [O]
                       → _COORDINATE_SOURCE_RANK gate + LocationEvidence
                       → nearest_sea_point (conditional, F-09)
                  → _auto_drift_if_live(force=True)
                       → is_auto_drift_eligible gate (F-01)             [P]
```

---

## 2. Failure points, by stage

### 2.1 Media acquisition — `_tweet_media_urls` (twikit_monitor.py:438) & `_x_photo_urls` (x_media_utils.py:146)

| ID | Failure | Detail | Severity |
| --- | --- | --- | --- |
| MA-1 | **`urls[:4]` truncation happens *before* the host allow-list filter** | `_tweet_media_urls` collects candidate URLs from `media` / `extended_entities` / `entities` / `card`, then does `for url in urls[:4]: if host in _ALLOWED_MEDIA_HOSTS`. If a shape yields ≥4 non-`pbs.twimg.com` URLs (t.co wrappers, a `card` thumbnail on a different CDN) before the real photo, the real photo is dropped. | High |
| MA-2 | **No syndication fallback in the live path** | `fetch_tweet_photos()` (syndication CDN, resolves media even when the twikit object shape changed) exists but is called **only** from `backfill_alarm_phone.py`. A live tweet whose media the twikit object doesn't expose is lost until a manual backfill. | High |
| MA-3 | **No original-resolution normalisation** | `pbs.twimg.com` URLs are used as-is. twikit commonly returns `…?format=jpg&name=small` (680 px) or `name=900x900`. The coordinate popup text is a handful of pixels tall at that size. There is no rewrite to `name=orig` / `name=4096x4096` before download. | High |
| MA-4 | **`card` thumbnail path is a guess** | Map-tool posts attach the screenshot as a link-preview card; `_tweet_media_urls` reads `card.thumbnail_url` / `card.image_url`, but a card thumbnail is a low-res crop and is often not on `pbs.twimg.com` at all, so it is then dropped by the allow-list (MA-1). | Medium |
| MA-5 | **Quoted-tweet media only merged in one branch** | `_ingest` merges `quoted` media, but a quote of an **already-tracked** incident routes to `_thread_repost` at [A] which does its own media handling; a quote-repost carrying a *new* map is not guaranteed to re-run OCR. | Medium |
| MA-6 | **No structured diagnostics returned** | `_tweet_media_urls` logs (`shapes_tried`) but returns only `list[str]`. The caller cannot persist *why* zero media were found (object-shape change vs. genuinely no image) — a silent centroid fallback with only a log line. | Medium |
| MA-7 | **Dedup by exact URL string** | `_x_photo_urls` dedups on the raw URL; the same image at `name=small` and `name=orig` counts as two, and after MA-3 is fixed the normalised form must be the dedup key. | Low |

### 2.2 OCR scheduling gate — `_ingest` (twikit_monitor.py:788-813)

| ID | Failure | Detail | Severity |
| --- | --- | --- | --- |
| SC-1 | **Text classifier runs before image understanding** | OCR is scheduled only when `distress OR alarm_phone_image_v2`. `is_direct_distress_call` is a strict regex classifier over the *caption*. Alarm Phone routinely posts a terse caption ("⚠️ #SOSMed", "Update ⬇️", a bare 🆘 quoting a report, a thread continuation) with the real content — including the GPS map — in the image or the quoted tweet. Every such post with a non-matching caption and no `text_coords` **skips OCR entirely** unless the `alarm_phone_image_v2` handle allow-list saves it. | **Critical** |
| SC-2 | **V2 bypass is Alarm-Phone-handle-only** | `alarm_phone_image_v2` requires `handle.lower() in {"alarm_phone","alarmphone"}`. Other tracked accounts that post Alarm-Phone-style maps (SosMedFrance, aegean_boat, Mare_Liberum, sea_watch relaying an AP position) get no image analysis on a non-distress caption. | High |
| SC-3 | **`text_coords` suppresses OCR even when the image is better** | If the caption contains *any* parseable coordinate, `not text_coords` is false and OCR never runs — even though the map screenshot usually carries a more precise / corrected position, and even though a caption coordinate can itself be a typo. | Medium |
| SC-4 | **Shadow mode is a dead-end analysis** | `_schedule_media_ocr_shadow` runs `_ocr_tweet_media` and only calls `record_ocr_result(...)` + `logger.info`. It does not persist the candidate coordinate, method, or a V1-vs-V2 comparison anywhere queryable. There is no way to evaluate shadow output without grepping logs. | Medium |
| SC-5 | **`ocr_available` false → warning only** | When neither engine is installed the code logs a warning and keeps the centroid. Correct, but there is no persisted `image_analysis_state = engine_unavailable` on the event for the operator UI. | Low |

### 2.3 OCR engines — `_ocr_photo` / `_easyocr_image` / `ocr_png_coordinate` (x_media_utils.py)

| ID | Failure | Detail | Severity |
| --- | --- | --- | --- |
| OC-1 | **`_ocr_photo` collapses everything to `coordinate or None`** | The return is `(coord, attempted, method, diag)`. `image_kind`, detected place names, people counts, distress terms, pin geometry, per-engine text, ROI list — none survive. A text card ("47 people, engine failure, position unknown") produces `(None, True, "none", {})` and is indistinguishable from a corrupt download. | **Critical** (blocks §4, §9 of the prompt) |
| OC-2 | **No ROI/text-region detection before OCR** | EasyOCR gets the whole image at `canvas_size=3200`. The Tesseract path scans the full image + 3 fixed horizontal bands + a brightness-run "popup" heuristic. There is no detection of *where* the coordinate text actually is, so small popups are diluted by basemap noise, and the fixed bands miss popups outside them. | High |
| OC-3 | **Only one preprocessing family** | `_ocr_photo` does `convert("L")` → autocontrast → SHARPEN → LANCZOS upscale to ~2400 px. No grayscale-vs-RGB comparison, no adaptive threshold, no inverted high-contrast pass for dark popups (Alarm Phone's dark-mode map cards), no per-ROI 2×/3× upscale. | High |
| OC-4 | **EasyOCR reader pinned to English** | `easyocr.Reader(["en"])`. Place labels on the basemap are fine, but the model is not asked for the language mix Alarm Phone maps show (FR/IT/TR town names, Arabic). Coordinate digits are language-neutral so this mostly hurts landmark matching. | Medium |
| OC-5 | **Cross-check is full-image only** | `_tesseract_cross_check` does one scaled/sharpened full-image multi-PSM pass. If EasyOCR read the popup but Tesseract can't find it in the noisy full image, the result is `easyocr_text_disputed` (wide uncertainty, no drift) even when EasyOCR was right — a false dispute. | Medium |
| OC-6 | **Consensus needs ≥2 agreeing candidates or exactly 1 total** | `consensus_ocr_coordinate` requires a cluster ≥2; `ocr_png_coordinate` otherwise accepts a lone candidate only if it is the *only* candidate across all passes. A map with the popup plus an unrelated number (a scale bar "50 km", a depth sounding) that also parses as a coordinate → 2 disagreeing singletons → **rejected**, no position. | Medium |
| OC-7 | **No confidence vector** | The prompt asks for confidence components (parser validity / engine agreement / OCR confidence / region validity / context agreement / landmask). Today confidence is implicit in the `method` string only (`consensus` = 400 m, `disputed` = 3500 m, `text` = 1500 m — hard-coded in `location_evidence.evidence_from_ocr_method`). | High |
| OC-8 | **`_MAX_IMAGE_PIXELS = 25_000_000` + 8 MiB cap** | An `name=orig` retina screenshot from a modern phone can exceed 25 MP; PIL then raises and `_ocr_photo` returns `none`. The cap must scale the image down rather than reject it. | Medium |

### 2.4 Pin detection — `_detect_marker_pixel` / `_blob_from_mask` (map_pin_geolocate.py)

| ID | Failure | Detail | Severity |
| --- | --- | --- | --- |
| PD-1 | **Colour masks only, single shape gate** | Four hard-coded HSV-ish RGB masks (red / blue / amber / yellow). `_blob_from_mask` is one compactness + fill-ratio + bbox-size heuristic. A pin that is a different hue (green, purple, black-outline-white-fill Leaflet default), a pin with a shadow, or a pin partly over dark water fails all four masks. | High |
| PD-2 | **No connected-components / contour detector** | The prompt asks for a second shape-based detector (HSV saturation → connected components → contours → compactness / aspect / teardrop geometry). Not present. `cv2` is a dependency but unused here. | High |
| PD-3 | **Returns one tip or nothing — no candidate list, no confidence** | `_detect_marker_pixel` returns `(x, y)` for the first mask that yields a blob, or `None`. Ambiguity (two red blobs) → `None`. No ranked candidates, no confidence, so a caller cannot fall back to "approximate, low confidence". | Medium |
| PD-4 | **Tip heuristic is aspect-ratio only** | `aspect 0.8–1.25 → centre, else → bottom`. A wide info-pin or a circle with a label tail is mis-located by tens of pixels → tens of km after the linear fit. | Medium |

### 2.5 Landmark geolocation — `geolocate_pin_from_image` (map_pin_geolocate.py:315)

| ID | Failure | Detail | Severity |
| --- | --- | --- | --- |
| LM-1 | **Linear per-axis `np.polyfit`, not Web Mercator** | `_fit_axis` fits `pixel = slope·lat + intercept` and `pixel = slope·lon + intercept` independently. Web maps are Mercator: the pixels-per-degree of latitude grows with latitude. Over a screenshot spanning >2–3° of latitude the fit is biased; the error grows toward the frame edges and with extrapolation distance (exactly the "boat 200 km south of Crete" case). | **Critical** |
| LM-2 | **`_MIN_LANDMARK_MATCHES = 2`** | Two points define an exact line per axis with zero residual — no way to detect a bad match. The prompt wants ≥3 preferred, 2 only with lower confidence + strict validation. | High |
| LM-3 | **No RANSAC / robust fit** | `_drop_worst_landmark` (leave-one-out residual, only with ≥4) is the entire outlier defence. One systematically mis-OCR'd label among 3 corrupts the fit and is not detected. | High |
| LM-4 | **Gazetteer is tiny and Central-Med / Crete biased** | `PRECISE_PLACES` ≈ 90 entries. A map of the Tunisian coast, the Alboran Sea, or the eastern Aegean may show 0–1 matchable labels. | Medium |
| LM-5 | **Records nothing** | The prompt wants `landmarks_detected`, `landmarks_used`, `fit_residual_px`, `extrapolation_distance`, `estimated_position_error_m`. None are computed or persisted. The result is a bare `(lat, lon)` with a fixed uncertainty applied later by method string. | High |
| LM-6 | **`nearest_sea_point` applied unconditionally** | The final line sea-snaps the pin. For a land Alarm Phone case (Evros, a reception centre on Lesvos) a pin-derived position is silently moved into the water — the same class of bug as `fixes.md` F-09, here in the pin path. | High |
| LM-7 | **`_MAX_KM_FROM_NEAREST_LANDMARK = 600`** | A guard against a wrong match, but also silently discards a legitimate far-offshore pin with a comment acknowledging that's the normal case. Should downgrade confidence, not return `None`. | Medium |

### 2.6 Tweet context as constraint

| ID | Failure | Detail | Severity |
| --- | --- | --- | --- |
| CX-1 | **Not used at all** | `text_coords` and `media_coords` are computed independently and the first non-null wins (`text_coords or media_coords or …`). The caption's place names (`#Sfax`, "Malta SAR", "off Lampedusa") are never used to (a) validate an image-derived coordinate, (b) boost its confidence, or (c) constrain landmark matching to the right instance of an ambiguous name. | High |
| CX-2 | **Risk if added naively** | The prompt is explicit: context must *constrain / validate*, never *move* the image pin to the text centroid. Any implementation must keep image evidence independent. | (design constraint) |

### 2.7 Structured non-coordinate extraction (§9 of the prompt)

| ID | Failure | Detail | Severity |
| --- | --- | --- | --- |
| EX-1 | **No extraction of people counts / vessel condition / distress terms from image text** | `humanitarian.py::_PEOPLE` runs on the *caption* only. A text-card image ("60 personnes, moteur en panne, prennent l'eau") contributes nothing. The OCR text EasyOCR already produced in `_easyocr_image` is joined, passed to `extract_numeric_coords`, and **discarded**. | High |
| EX-2 | **No OCR evidence string retained** | Even for coordinates, the raw OCR span that produced the number is not stored (F-10 asks for a bounded raw span). `geoextract` folds `O→0` etc. destructively before matching. | Medium |

### 2.8 Observability (§10 of the prompt)

| ID | Failure | Detail | Severity |
| --- | --- | --- | --- |
| OB-1 | **Per-image diagnostics not persisted** | `record_ocr_result(label)` increments a Prometheus counter with one label; queue depth/age gauges exist. But `media_discovered`, `media_source`, `image_fetch_ok`, `image_dimensions`, `image_kind`, `easyocr_box_count`, `tesseract_attempted`, `coordinate_candidate_count`, `pin_detected`, `landmark_count`, `selected_method`, `confidence`, `failure_reason` are not written to the event metadata or any diagnostics table. | High |
| OB-2 | **`ocr_attempted` is the only per-event flag** | Set to `True` on a miss. No breakdown of *how far* the pipeline got. | Medium |

### 2.9 Benchmark (§11 of the prompt)

| ID | Failure | Detail | Severity |
| --- | --- | --- | --- |
| BM-1 | **No benchmark harness** | `backfill_alarm_phone.py` has `--apply` / `--drift` / `--limit` but no `--benchmark` mode, no ground-truth set, no V1/V2 comparison report, no precision/recall metrics. `tests/test_x_media_utils.py` + `tests/test_map_pin_geolocate.py` are unit tests over synthetic PNGs, not an evaluation corpus. | High |

---

## 3. How many legitimate Alarm Phone image posts are missed before OCR

The dominant loss is **SC-1 + SC-2**: OCR is gated on a strict caption
distress classifier that runs *before* any image is looked at.

Post shapes that carry a map/coordinate image but do **not** reliably match
`is_direct_distress_call` on the caption alone:

- thread continuations / "Update ⬇️" / "⚠️⬇️" captions,
- a bare 🆘 or "#SOSMediterranee" quoting the actual report (the quote text is
  merged, but if the quote is a *tracked* incident it routes to
  `_thread_repost` first — MA-5),
- position-correction posts ("New position:" with the number only in the new
  screenshot),
- "in contact with the boat" / "the people called us" openers,
- interception / pushback updates that include the last known map,
- non-`alarm_phone` relays of an Alarm Phone position.

`alarm_phone_image_v2` (default **on**) catches the first group *for the
`alarm_phone` handle only*. Everything from another handle, and every
tracked-incident quote-repost, still depends on the caption classifier.

**Estimate:** on the historical corpus this should be measured, not guessed —
that is what §5 / BM-1 is for. Qualitatively, the caption-first gate is the
single biggest recall hole and the shadow-mode data (SC-4) is currently not
captured well enough to size it.

---

## 4. Proposed V2 architecture

```
core/intel/image_extraction.py         NEW  — orchestrator + ImageExtractionResult
core/intel/x_media.py (resolve_x_media) NEW  — canonical media acquisition + diagnostics
core/intel/image_pin.py                NEW  — colour + shape pin detectors, ranked candidates
core/intel/image_geolocate.py          NEW  — Web-Mercator landmark fit + RANSAC + residuals
core/intel/image_kind.py               NEW  — map_screenshot / text_card / infographic / photo / unknown
core/intel/image_text_fields.py        NEW  — people/vessel/needs/place spans from OCR text
core/intel/ocr_engines.py              NEW  — thin wrappers: easyocr_read(), tesseract_read()
                                              (moved out of x_media_utils, keep the locks)
```

`x_media_utils.py` keeps `_TESSERACT_LOCK` / `_EASYOCR_LOCK`, `haversine_m`,
Snowflake helpers, `_syndication_token`. `_ocr_photo` becomes a thin
compatibility shim over `image_extraction.extract_from_url` returning the old
4-tuple, so `twikit_monitor` and `backfill` keep working during the cutover.

### `ImageExtractionResult` (frozen dataclass)

```
image_kind: Literal["map_screenshot","text_card","infographic","photo","unknown"]
detected_text: str                      # bounded, joined OCR text
coordinate_candidates: list[CoordinateCandidate]
selected_coordinate: tuple[float,float] | None
coordinate_method: str                  # printed_text | ocr_consensus | pin_landmark | none
coordinate_confidence: float            # 0..1, from ConfidenceComponents
confidence_components: dict[str,float]
place_names: list[str]
people_counts: list[PeopleSpan]         # {kind, count, approx, raw}
distress_terms: list[str]
pin_detected: bool
pin_candidates: list[PinCandidate]      # {x,y,confidence,detector}
landmarks_used: list[str]
landmarks_detected: list[str]
fit_residual_px: float | None
estimated_position_error_m: float | None
ocr_engines: list[str]
evidence: dict[str,Any]                  # media_sha256, source_post_id, raw spans (bounded)
failure_reasons: list[str]
diagnostics: dict[str,Any]              # the §10 observability keys
```

### Decoupling (§3)

`_ingest` schedules image analysis when:

```
media_count > 0
AND NOT text_coords          (or: text_coords present but low-trust — later)
AND ocr_available
AND ( handle in TRACKED_IMAGE_ACCOUNTS  OR  distress  OR  humanitarian-ish caption )
```

`TRACKED_IMAGE_ACCOUNTS` replaces the two-name `alarm_phone_image_v2` check
and is config-driven (`ALARM_PHONE_IMAGE_V2_ACCOUNTS`, default the AP handles
+ the main relays). Image analysis **never auto-publishes**: it enriches
location + attaches `image_assessment` metadata; the existing publication
policy and F-01 drift gate are unchanged. `ALARM_PHONE_IMAGE_V2_SHADOW`
becomes a real shadow: run V2, persist `image_assessment_shadow` +
`v1_v2_delta`, change nothing public.

### Confidence model (§5)

```
ConfidenceComponents:
  parser_validity      # regex tier: printed DMS/DMM > decimal > OCR-folded
  engine_agreement     # easyocr↔tesseract geodesic distance → 0..1
  ocr_confidence       # mean box confidence over the coordinate span
  region_validity      # in_operational_region + expected AP corridor
  context_agreement    # distance to caption place-name centroid (bounded bonus)
  landmask_validity    # sea for maritime case / land for land case
selected_coordinate accepted for public exact point only when
  parser_validity high AND (engine_agreement high OR printed_text) AND region_validity
false coordinate → fail closed (selected_coordinate=None, method="none", reason logged)
```

### Web-Mercator landmark fit (§7)

```
lat/lon → mercator_y/x   (y = ln(tan(π/4 + φ/2)))
robust affine pixel↔mercator fit:
  ≥4 labels → RANSAC (2-pt models, inlier px threshold, refit on inliers)
  3 labels  → least-squares + residual gate
  2 labels  → axis-aligned fit, confidence ≤ 0.35, region + context gate mandatory
pin pixel → inverse fit → mercator → lat/lon
record landmarks_detected/used, fit_residual_px, max_extrapolation_px,
       estimated_position_error_m (residual + extrapolation propagated)
sea-snap ONLY when image_kind=map_screenshot AND case is maritime AND
       displacement < conservative bound   (fixes LM-6)
```

---

## 5. Exact files to modify

| File | Change |
| --- | --- |
| `core/intel/x_media_utils.py` | extract `resolve_x_media`; add `name=orig` normalisation; keep locks + helpers; `_ocr_photo` → shim |
| `core/intel/x_media.py` *(new)* | `resolve_x_media(tweet, tweet_id, quoted_tweet=None) -> MediaResolution` (ordered sources, dedup on normalised URL, syndication fallback, structured diagnostics) |
| `core/intel/image_extraction.py` *(new)* | orchestrator, `ImageExtractionResult`, `extract_from_url`, `extract_from_bytes` |
| `core/intel/image_kind.py` *(new)* | classifier |
| `core/intel/image_pin.py` *(new)* | colour + connected-component/contour detectors, ranked `PinCandidate` |
| `core/intel/image_geolocate.py` *(new)* | Web-Mercator + RANSAC fit, residual/error metrics |
| `core/intel/image_text_fields.py` *(new)* | people/vessel/needs/place span extraction from OCR text |
| `core/intel/map_pin_geolocate.py` | delegate to `image_geolocate`; keep a thin `geolocate_pin_from_image` |
| `core/intel/twikit_monitor.py` | `_tweet_media_urls` → `resolve_x_media`; widen the OCR gate; persist diagnostics + `image_assessment`; real shadow |
| `core/intel/location_evidence.py` | accept a `confidence_components` / `estimated_position_error_m` and size uncertainty from it, not a fixed per-method constant |
| `core/intel/backfill_alarm_phone.py` | `--benchmark` mode: run V1 + V2, emit comparison report, no DB writes |
| `core/config.py` | `ALARM_PHONE_IMAGE_V2_ACCOUNTS`, ROI/threshold knobs |
| `core/observability.py` | per-image histogram/counters; `image_kind`, `pin_detected`, `landmark_count` labels |
| `tests/fixtures/alarm_phone_images/` *(new)* | synthetic PNG generators + ground-truth JSON |
| `tests/test_image_extraction.py`, `test_image_geolocate.py`, `test_image_pin.py`, `test_resolve_x_media.py` *(new)* | |

---

## 6. Evaluation strategy

- **Synthetic fixture generators** (committed): programmatically render PNGs
  with Pillow for each row of §13 of the prompt (coordinate popup, tiny text,
  dark popup, quoted-tweet map, red/blue/yellow pin, no-coord + 3 labels,
  unrelated numbers, insufficient landmarks, low-res preview, false place).
  Ground truth stored beside them as JSON (`expected_coordinate`,
  `tolerance_km`, `has_pin`, `image_type`).
- **Local benchmark set** (not committed — licensing): a runner that reads a
  local `benchmark/alarm_phone/*.json` (operator-provided `tweet_id` +
  ground truth), resolves media via syndication, runs V1 and V2, and reports:
  media-retrieval recall, OCR-attempt rate, coordinate recall, coordinate
  precision, **false-coordinate rate**, median error km, pin-detection recall,
  V1↔V2 disagreement list.
- **Gate:** V2 must not increase false-coordinate rate vs V1. Precision is
  optimised before recall. A wrong coordinate must fail closed.

---

## 7. Ordered PR plan

| PR | Title | Risk |
| --- | --- | --- |
| 1 | `test(image): synthetic Alarm Phone image fixtures + ground truth` | none (test-only) |
| 2 | `feat(image): resolve_x_media canonical media acquisition + diagnostics` | low (behind existing gate; adds syndication fallback + `name=orig`) |
| 3 | `refactor(image): ImageExtractionResult + extract_from_url orchestrator` | low (`_ocr_photo` shim keeps callers stable) |
| 4 | `feat(image): image_kind classifier + persist per-image diagnostics` | low (metadata only) |
| 5 | `feat(image): decouple image analysis from caption distress classifier` | **medium** (recall change; shadow-first, `ALARM_PHONE_IMAGE_V2_SHADOW` default until benchmark) |
| 6 | `fix(image): Web-Mercator landmark fit + RANSAC + residual/error metrics` | medium (changes pin coordinates; covered by fixtures) |
| 7 | `feat(image): shape-based pin detector + ranked candidates + confidence` | medium |
| 8 | `feat(image): confidence model + evidence-sized uncertainty` | medium (feeds F-01 gate — must not loosen it) |
| 9 | `feat(image): tweet context as validation constraint (never a move)` | low |
| 10 | `feat(image): structured people/vessel/needs extraction from image text` | low (metadata only; classifier decides semantics) |
| 11 | `feat(image): conditional sea-snap in the pin path (F-09 parity)` | low |
| 12 | `feat(backfill): --benchmark V1/V2 comparison report` | none (no DB writes) |
| 13 | `feat(image): promote V2 out of shadow after benchmark sign-off` | **gated on benchmark** |

Each PR: own regression test, full `pytest` + web suite green, no change to
the F-01 drift gate's strictness.

---

## 7a. Implementation progress

| PR | Commit | State |
| --- | --- | --- |
| 1 — synthetic fixtures + ground truth | `669640a` | landed |
| 2 — `resolve_x_media` + diagnostics | `127b587` | landed |
| 3 — `ImageExtractionResult` + `extract_from_url` | `318ead3` | landed (also folded in PR 4's per-image diagnostics persist + a first-cut `classify_image_kind`) |
| 4 — `image_kind` classifier (dedicated module) | — | first-cut only, inside `image_extraction.classify_image_kind`; a dedicated refined classifier is still pending |
| 5 — decouple image analysis from the caption distress classifier | *this branch* | landed. `_tracked_image_accounts()` wires `ALARM_PHONE_IMAGE_V2_ACCOUNTS` into the `_ingest` OCR gate and the shadow branch. Default (`""`) keeps today's behaviour — only the two Alarm Phone handles. Operators add relay handles (and may run them through `ALARM_PHONE_IMAGE_V2_SHADOW`) until the PR 12 benchmark signs the recall change off. |
| 6 — Web-Mercator landmark fit + RANSAC + residual/error | `6765a37` | landed. Also gave `geolocate_pin_from_image` a `sea_snap` opt-out (partial PR 11). |
| 7 — shape-based pin detector + ranked candidates | *this branch* | landed. New `core/intel/image_pin.py`: colour masks + a colour-independent HSV shape detector, numpy connected components, per-blob geometry (fill / aspect / pointed-down teardrop tip / circle centre), ranked `PinCandidate` list. `select_pin` returns a pin only when one candidate is unambiguous (single, or all detections agree in pixel space, or a clear confidence margin) — two confident separate blobs fail closed. `map_pin_geolocate._detect_marker_pixel` now delegates; `image_extraction` records the ranked candidates for diagnostics. |
| 8 — confidence model + evidence-sized uncertainty | *this branch* | landed. New `core/intel/image_confidence.py`: six named components (`parser_validity`, `engine_agreement`, `ocr_confidence`, `region_validity`, `context_agreement`, `landmask_validity`) combined under a weighted sum, with `region_validity` a hard multiplier and a per-family ceiling (a disputed read can never be rescued by the soft components). `image_extraction` replaces the per-method constant, records the components, and **fails closed** — a coordinate outside the operational envelope is dropped (`selected_coordinate=None`, `method="none"`, reason recorded). `location_evidence.evidence_from_ocr_method` takes `estimated_position_error_m` from the pin fit and uses it only to *widen* the per-method uncertainty (F-03 floor). `_easyocr_image` boxes now carry `confidence`. F-01 drift gate untouched. `landmask_validity` stays a neutral constant until the humanitarian case class is wired (PR 10). |
| 9 — tweet context as validation constraint | *this branch* | landed. `twikit_monitor` persists the caption's gazetteer place names (`context_place_names`); `_apply_media_ocr` and the shadow path pass them to `image_extraction`, which resolves them to centroids and feeds `context_agreement` a bounded bonus when the coordinate is near a caption place (≤120 km → 0.75, name overlap → 0.9) and a bounded penalty when it is far from every one (≥400 km → 0.35). The coordinate is **never moved** toward the caption centroid — a regression test asserts identical lat/lon with and without context. |
| 10 — structured people/vessel/needs extraction | *this branch* | landed. New `core/intel/image_text_fields.py`: `extract_people` (aboard / rescued / missing / dead / injured / children / women — each a distinct span with its count, approx flag and raw OCR text, so "45 aboard, 12 rescued, 3 missing" is three spans not one), `extract_vessel_conditions` (engine_failure / taking_water / capsized / overcrowded / adrift / deflating / rubber_boat), `extract_needs` (rescue / medical / food_water / fuel / disembarkation), all EN/IT/FR. `image_extraction` populates `people_counts` / `vessel_conditions` / `needs` and surfaces them (bounded) in the assessment metadata. Candidates only — the humanitarian classifier still decides semantics. |
| 11 — conditional sea-snap in the pin path | *this branch* | landed. PR 6 gave `geolocate_pin_from_image` the `sea_snap` flag; this PR threads it from the case class: `twikit_monitor._event_sea_snap` returns `False` when the event is `humanitarian_case_type == "land_humanitarian"` or `location_status == "withheld_from_maritime_map"`, and `_apply_media_ocr` / the shadow path pass it through `_ocr_tweet_media` → `image_extraction` → `_extract_coordinate_from_bytes` → `geolocate_pin_from_image`. An Evros / reception-centre pin keeps its reported position (F-09 parity, audit LM-6). |
| 12 — `--benchmark` V1/V2 comparison report | *this branch* | landed. New `core/intel/image_benchmark.py` (`BenchmarkItem`, `evaluate` → `BenchmarkReport`): runs V1 (raw coordinate core) and V2 (structured + confidence + fail-closed) over a set of images with ground truth, reports OCR-attempt rate, coordinate recall / precision / **false-coordinate rate**, median error km, pin-detection recall, and the V1↔V2 disagreement list. `backfill_alarm_phone --benchmark [--benchmark-dir]` reads local ground-truth JSON, resolves media live from syndication and prints the report — **no DB access, no writes**. `benchmark/alarm_phone/README.md` documents the JSON schema; third-party images are never committed. |
| 13 — promote V2 out of shadow | — | gated on PR 12 |

## 8. Invariants this work must not break

- Disputed / low-confidence OCR → **0** auto-drift (F-01). A wider OCR gate
  must not widen drift eligibility.
- `force=True` never bypasses the evidence gate.
- Land humanitarian case → never sea-snapped, never a maritime marker (F-09).
- A wrong coordinate fails closed (returns `None`), never a confident guess.
- Image analysis never auto-publishes; publication policy is unchanged.
- `pbs.twimg.com`-only host allow-list stays; no new outbound hosts.
