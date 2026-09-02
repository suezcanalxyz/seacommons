# OCR and drift-forcing pipeline audit — 2 September 2026

## Scope and evidence boundary

The investigation began read-only. After explicit operator authorization, the
confirmed fixes were committed and loaded by the production API and worker.
The findings below describe the pre-fix root causes; the final section records
the deployed state and verification evidence.

## Executive findings

1. **OCR is gated behind the text classifier.** In the Twikit live path it is
   scheduled only when `distress` is true, no numeric text coordinate was
   parsed, at least one allowed media URL was found, and Tesseract or EasyOCR
   appears installed. Tests explicitly lock in the non-distress skip.
2. **Images can be discovered and still skipped.** This happens for
   non-distress/resolved/context posts, posts with a parsed text coordinate,
   duplicates, unavailable OCR engines, queue overflow, disallowed hosts,
   oversize/non-image downloads, and several early-return tweet/thread paths.
3. **The code cannot currently prove whether OCR read usable-but-unparsed
   text.** Raw EasyOCR/Tesseract text is discarded and neither persisted nor
   summarized diagnostically. Parser coverage is demonstrably incomplete,
   but production occurrences cannot be counted from current telemetry.
4. **Operational Drift uses CMEMS currents when available plus an Open-Meteo
   wind/current/wave grid.** The final constant reader is a last resort, but a
   total Open-Meteo point-fetch failure is incorrectly labelled
   `spatiotemporal` because the grid object still exists after being filled
   entirely with constant fallback values.
5. **There is no bathymetry forcing.** “Depth” currently means the shallow
   CMEMS current slice (0.494–5 m) and an OceanDrift wind-drift-depth parameter,
   not seabed depth or a depth-varying water column.

## Alarm Phone / Twikit image path

The live call path is:

```text
Twikit timeline item
  -> repost / quote / reply routing
  -> own + quoted text
  -> is_direct_distress_call()
  -> extract_numeric_coords() (only if distress)
  -> _tweet_media_urls() for own and quoted tweet
  -> OCR eligibility gate
  -> bounded MediaOcrQueue
  -> _ocr_photo(url)
  -> HTTPS pbs.twimg.com download, <= 8 MiB, image/* only
  -> EasyOCR full-image pass
  -> optional Tesseract cross-check
  -> if needed, Tesseract multi-crop/multi-PSM sweep
  -> map-pin + landmark fallback
  -> extract_numeric_coords()
  -> evidence_from_ocr_method()
  -> intel_store.enrich_location()
  -> separately gated auto-drift
```

Primary evidence: `twikit_monitor.py:676-940`,
`x_media_utils.py:67-137,264-500`, `geoextract.py:443-625`, and
`media_ocr_queue.py:35-158`.

### Is OCR incorrectly gated behind `distress=True`?

**Yes, confirmed.** `twikit_monitor.py:732` only parses text coordinates when
`distress`; lines 740-742 set `ocr_pending` only when
`distress and not text_coords and media_count`; lines 885-889 schedule only
when that flag is true. `test_twikit_monitor.py:985-1000` expressly asserts
that a non-distress post with media never schedules OCR.

This makes image understanding downstream of text classification, so an
Alarm Phone post whose actionable content exists only inside an image cannot
correct a false-negative text classification. The repository contains no
counter or shadow analysis from which to calculate how many legitimate posts
are missed. A numerical miss count is therefore not supportable yet.

### Are images discovered but skipped?

**Yes, through multiple proven branches:**

| Condition | Result |
|---|---|
| Text is not direct distress, including resolved/context/news | URLs may be counted/stored, but OCR is not scheduled. |
| Explicit text coordinate parses | Image OCR is skipped by design; text wins. |
| Tweet text is under 10 characters | Ingestion returns before media discovery. |
| Repost, quote of an already-stored event, or reply to an existing event | Specialized thread/repost path returns before this OCR path. |
| Candidate media host is not HTTPS `pbs.twimg.com` | Discovered candidate is filtered out. |
| More than four candidate URLs appear in one media shape | Only `urls[:4]` are host-checked; a valid fifth image is skipped. |
| Twikit exposes some usable URL in `.media` | `extended_entities`, `entities`, and card fallbacks are not examined because they run only while `urls` is empty. |
| Live Twikit shapes yield no URL | There is no live syndication `fetch_tweet_photos()` fallback; it exists only in historical reprocessing. |
| Neither engine is importable/installed | OCR is not queued. |
| Bounded queue and deferred backlog are both full | Job returns `dropped`; no automatic retry is shown. |
| Download is non-HTTPS/wrong host, non-image, over 8 MiB, times out, or raises | That image produces no coordinate; the next URL is tried. |
| Duplicate event is not newly added | OCR is not scheduled for the existing event in the duplicate branch. |

Media discovery does include typed Twikit media, `extended_entities`,
`entities`, card images, and quoted-tweet media. It does not return structured
per-source diagnostics, does not deduplicate within `_tweet_media_urls()`, and
does not normalize every accepted URL to original resolution. Test fixtures
append `?name=orig` in their fake media objects; the production resolver itself
does not do that normalization.

### Can OCR read text that `extract_numeric_coords()` fails to parse?

**The architecture permits it; actual production instances are not
observable.** Both engines reduce detected text immediately to a coordinate:
EasyOCR joins text boxes then calls `extract_numeric_coords()`; Tesseract keeps
texts only in local memory and calls the same parser. On failure the persisted
result is merely `no_coordinate`/`ocr_attempted`, so “engine read nothing” and
“engine read text the parser rejected” are indistinguishable.

A read-only parser probe proves gaps for plausible OCR strings:

| OCR text | Raw parser result |
|---|---|
| `N 34° 16.2 E 011° 56.5` | `(34.27, 11.941667)` |
| `N 34 16.2 E 011 56.5` | `None` |
| `34° 16.2 N 011° 56.5 E` | `None` |
| `34 16.2N 011 56.5E` | `None` |
| `Latitude 34.2700 Longitude 11.9417` | `None` |
| `34.2700, 11.9417` | `(34.27, 11.9417)` |

The parser requires particular hemisphere ordering and, for DMM/DMS, degree
or quote glyphs. It handles several OCR confusions (`O/Q/@`, `I/|/!`, `Z`,
`B`) and comma decimals, but not missing glyphs or verbose labels between the
two decimal components. These are coverage facts, not proof that current
production OCR emitted those exact strings.

## Operational drift / forcing pipeline

The authoritative in-process path is `DriftEngine._opendrift()` to
`opendrift_pool.run_leeway()`. `opendrift_runner.py` is a separate legacy-style
stdin runner and is not called by `DriftEngine`.

### Providers and variables

| Quantity | Primary/runtime source | Use in OpenDrift | Fallback |
|---|---|---|---|
| Wind | Open-Meteo Forecast API, 10 m wind speed/direction | Converted from meteorological “from” direction to `x_wind`/`y_wind`; hourly field | Current-point response, stale/live cache, hourly cache, then 5 m/s from 270° constants |
| Currents | CMEMS `cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m`, `uo`/`vo` | CF NetCDF reader, inserted at highest priority | Open-Meteo Marine hourly current grid; ultimately current-point CMEMS result or zero constants |
| Waves | Open-Meteo Marine wave height/direction/period | Converted to a bounded deep-water surface Stokes vector; enabled only when non-zero wave data exists | Zero Stokes; CMEMS wave dataset is not used by the drift runner |
| Water temperature | CMEMS temperature dataset | Not used by Drift; used by other ocean/area code | None in Drift |
| Depth/bathymetry | No bathymetry provider | No seabed/depth reader or depth-dependent current selection | None |
| Land | OpenDrift `reader_global_landmask` | Beaching/land mask | Constant `land_binary_mask=0` if reader unavailable |

CMEMS point fetching in `CacheManager` obtains a base current before the run,
but does not receive the simulation timestamp from `DriftEngine`; it samples
around “now.” The actual CMEMS NetCDF reader requests the simulation window
and overrides that base current where coverage exists.

### OpenDrift models and leeway

- SAR objects use OpenDrift `Leeway` with object types: person in water 26,
  small life raft 27/29, inflatable boat 38, small wooden/fibreglass 46, and
  fishing vessel 52.
- Shipwrecks seed a 45% person / 30% raft / 25% wooden-debris mixture.
- Powered/large hulls use `OceanDrift`, with configured wind-drift factors from
  0.01 (tanker) to 0.04 (sailboat) and nominal wind-drift depths from 0.3 to
  3.0 m. Failure to set the version-dependent depth config is caught and only
  debug-logged.
- Each particle receives a deterministic current factor with nominal 8%
  standard deviation. OceanDrift hulls also receive nominal 20% relative
  windage variation.

### Readers, precedence, and fallbacks

1. A custom `_GridReader`, subclassing `reader_constant.Reader`, is built from
   Open-Meteo data and supplies wind, currents, and optional Stokes vectors.
2. A CMEMS `reader_netCDF_CF_generic` is added with `first=True`, intended to
   override current variables within its domain. Open-Meteo still supplies
   wind and waves.
3. `reader_constant` is added only if construction of the grid reader raises.
4. `reader_global_landmask` is added last when import/construction succeeds.

Important fallback defect: individual Open-Meteo failures never make
`_fetch_grid()` fail. Every point returns NaN arrays, which are filled from the
centre and then from the base constants. `_run_leeway_inner()` nevertheless
sets `grid_reader_added=True`, `forcing_resolution=1.0deg-OpenMeteo-grid`,
`forcing_quality=spatiotemporal`, and `operational_use=True`. Thus a wholly
constant, failed-provider run can be certified operational. The metadata
criterion measures reader construction, not successful time/space-varying
samples.

The CMEMS “hard” 90-second cap is also not demonstrably hard: the timed-out
future is inside a `ThreadPoolExecutor` context manager, whose normal exit
waits for running work. The timeout branch may therefore wait for the
underlying subset call before returning.

### Spatial and temporal resolution

| Layer | Spatial coverage/resolution | Temporal sampling |
|---|---|---|
| CMEMS currents | Dataset identifier declares 0.083°; requested slice is actually ±1° around origin (despite a ±2° docstring) and 0.494–5 m depth | Dataset identifier is P1D (daily); OpenDrift CF reader interpolates provider coordinates/times |
| Open-Meteo query lattice | 5×5 points at 1.0° spacing, ±2° around origin; bilinear interpolation, clamped at grid edges | Hourly values for `duration + 1`; custom reader linearly interpolates between hours |
| OpenDrift integration | Particle-level, not a forcing resolution | Default engine step is 1800 s unless env/config overrides it; example deployment sets 900 s; output default is 3600 s |

The reported `forcing_resolution` collapses mixed fields to one label. When
CMEMS is present it reports `0.083deg-CMEMS`, although wind and waves remain on
the 1° Open-Meteo query lattice. Also, 1° is the application's sampling
lattice, not proof of the native resolution of Open-Meteo's underlying model.

## Root causes and evidence still required

The missing-image root cause is architectural: image analysis is subordinate
to a text-only distress decision, and failures collapse to “coordinate or
None.” The false forcing-quality root cause is likewise architectural:
metadata is derived from reader presence rather than successful provider
samples and their per-variable provenance.

Before any production change, collect:

1. Shadow-mode per-post media diagnostics for all Alarm Phone posts, regardless
   of publication classification.
2. Privacy-safe OCR diagnostics distinguishing no text, text detected/parser
   rejected, coordinate rejected by range/landmask, and engine disagreement.
3. Per-variable forcing provenance and valid-sample counts for wind, current,
   and waves, including constant-fill percentage and actual provider times.
4. A production-like OpenDrift smoke run with CMEMS enabled, disabled, timed
   out, and with total Open-Meteo failure, verifying metadata in every case.
5. Current production package/config/service evidence from an authorized
   read-only host session; repository manifests alone cannot prove deployed
   state.

## Remediation and live verification

Deployed commit `af9bb5a` changes the Alarm Phone image decision from
classifier-gated to media-first V2, while retaining private publication for
non-distress content. Lone-engine, disputed, and pin-derived positions are
stored only as unverified evidence and atomically invalidate any stale drift
status; only EasyOCR/Tesseract consensus may seed a replacement drift.

For forcing, valid pre-fill sample coverage is now recorded independently for
wind, current, and waves. `operational_use` is true only when observed wind and
current coverage is complete (with CMEMS current accepted as observed current);
mixed and constant-filled runs are labelled non-operational. The CMEMS surface
request now starts at the provider's exact first level,
`0.49402499198913574 m`, eliminating the repeated clamp warning.

Verification on 2026-09-02 UTC: targeted OCR/forcing/CMEMS regressions passed;
the complete backend suite passed (`519 passed`); API and worker restarted
active; `/health` returned `status=ok`; multiple post-restart CMEMS fetches
emitted no depth warning; and live OCR logs showed unverified results rejected
from auto-drift. Production DB validation was read-only.
