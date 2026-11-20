# Historical satellite analysis in PLAY

The review pipeline reads the public case timeline and lists its Copernicus Sentinel‑1 GRD products. The detector accepts a georeferenced backscatter raster derived from the chosen product. Its outputs are review candidates and stay local until a reviewer has verified their provenance and interpretation.

## List the source scenes

From the repository root, pass one or more incident IDs:

```sh
python3 scripts/play_satellite_analysis.py scenes 09514982
```

The inventory includes the acquisition time, exact product ID and source record. It sorts scenes by their absolute time difference from the case where the archive provides that value. Coverage and timing alone do not identify a vessel.

## Review a coastal or offshore subset

Use the exact GRD product listed in the inventory. Open it in ESA SNAP, apply the appropriate orbit file, remove thermal noise, calibrate to Sigma0 and terrain correct. Export a single polarisation as a georeferenced GeoTIFF of the marine review area. Retain the pixel values, coordinate reference system and NoData mask. The script takes at most four million pixels. Use a Python 3.11+ environment with GDAL Python bindings, NumPy, SciPy and Pillow.

```sh
python3 scripts/play_satellite_analysis.py detect CASE_ID PRODUCT_ID calibrated-vv.tif review-output --scale linear
```

Use `--scale db` if the export already contains decibels. The output directory must be new. The JSON records the product supplied by the operator and the SHA‑256 of the local input. Verify the raster lineage against the source product before admitting a result as evidence.

For each return, the output contains a point in WGS84, an unmodified georeferenced GeoTIFF crop and a contrast-stretched PNG preview. Open the TIFFs and the GeoJSON in QGIS for review. Nearby published AIS fixes, when available in the same PLAY dossier, appear with their observed times and distances. The local contrast score ranks candidate returns and does not estimate identity or detection probability. Bright clutter, shoreline, structures and wakes can generate false candidates. The workflow leaves identity blank and makes no database writes.

## Shoreline and source review

Pass `--water-mask water.tif` with a single-band mask on the same grid as the SAR input. Water pixels have value 1. The detector leaves land and missing pixels out of its background estimate, excludes candidates near mask boundaries, and requires at least 5 dB of local contrast. Runs without a mask are marked for shoreline and human review.

Each result records nearby public case sources, including geolocated radio reports and updates when their own timestamps and coordinates are available. This comparison uses a one-hour and five-kilometre window for triage. The original radio association is preserved without promotion. Consult the original record before identifying a ship or opening a new incident.

## Validate on an independent archived scene

The `benchmark` command uses the Planetary Computer Sentinel‑1 RTC catalog to resolve an exact scene independently of a PLAY incident. For the test near Lampedusa on 22 June 2024, the VV asset was accessed through the provider's public signing endpoint. It was subset to the WGS84 window with west 12.53, east 12.62, south 35.46 and north 35.52, at native resolution.

```sh
python3 scripts/play_satellite_analysis.py benchmark \
  S1A_IW_GRDH_1SDV_20240622T170427_20240622T170452_054439_069FC6_rtc \
  historical-vv.tif benchmark-review --scale linear
```

The 800 × 686 pixel test subset produced six unreviewed returns without a water mask. This checks the read, analysis and export path on real SAR pixels. No vessel labels were available for this scene, so it does not measure detector precision or recall.

## Humanitarian history

Export the public PLAY humanitarian catalog to a SQLite snapshot. The exporter
includes reports older than 24 hours, their public status transitions, and links
to their source dossiers. Use one `--satellite-case` option per incident whose
Sentinel-1 products you want to index.

```sh
python scripts/export_humanitarian_archive.py humanitarian.sqlite --satellite-case 09514982
```

`humanitarian_cases` and `status_history` preserve the public case IDs.
`satellite_scenes` indexes scene metadata for the selected subset, with the
requested case IDs recorded in `archive_metadata`. A scene index is a starting
point for the radar review workflow. It does not assert a vessel sighting.

## Review detected returns

Combine any number of detector exports into a new CSV review queue. Repeated
candidate IDs are counted once. To extend an existing queue, choose a new output
filename and pass `--previous review.csv` to retain all earlier decisions.

```sh
python scripts/review_satellite_returns.py queue review.csv run-a/radar-returns.geojson run-b/radar-returns.geojson
python scripts/review_satellite_returns.py summarize review.csv
```

Open the preview and GeoTIFF from each row. Set `decision` to `vessel`,
`non_vessel`, or `inconclusive`. Cite the source supporting each conclusive
decision in `evidence_reference`. A vessel decision describes the detected
object class. It does not assign a vessel identity or confirm an incident.
The summary reports pending and inconclusive returns separately. The vessel
share among resolved reviews is descriptive and is not recall or a validation
of all unreviewed detections.

## Run the historical pilot

A pilot manifest is a JSON list with one entry per radar input. Each entry has
`product`, `raster` (relative to the manifest or absolute), and `scale` (`linear`
or `db`). Include `case_id` for a product from a PLAY dossier. Omit it for an
independent Sentinel‑1 RTC sensor benchmark. The pilot rasterizes a land vector
file or zipped shapefile directly onto each radar grid.

```sh
python scripts/run_satellite_pilot.py manifest.json land.zip pilot-output
```

The pilot writes one folder per scene with a GeoJSON, GeoTIFF crops and PNG
previews. A combined `review.csv` is written after all scenes finish. Use a new
output directory when comparing runs. Reviewers can add a decision and a
reference to the primary source for each candidate.

### Lampedusa coastal run

Five June 2024 Sentinel‑1 RTC VV subsets were processed on the same coastal
window using Natural Earth land polygons and the same detector settings.

| Date (UTC) | Returns after masking |
|---|---:|
| 4 June 2024 | 2 |
| 10 June 2024 | 1 |
| 15 June 2024 | 1 |
| 16 June 2024 | 4 |
| 22 June 2024 | 1 |

On 22 June, the mask removed five land returns from the six produced by the
unmasked run. The remaining return retains its original peak pixel and
candidate ID. This run validates the coastal filter and batch exports. The
scenes lack a complete independent vessel inventory, so they cannot establish
recall or vessel identities.

Before running on a schedule, evaluate on a held-out set with reviewed boat
and non-boat examples. Record detections matched to labels, missed boats and
false positives per scene, with results split by coastal and offshore settings.
For humanitarian cases, preserve the acquisition time and compare it with
independent, time-compatible sources before attributing a return to a case.

## Check the time window before processing

```sh
python scripts/play_satellite_analysis.py triage 09514982 4edefafb 4aa78b4a --window-hours 6
```

Triage orders the Sentinel‑1 records already indexed by PLAY relative to the
first public report, or to an explicit verified incident timestamp passed as
`--event-at` for one case. Report time may differ from incident time. An item
within the chosen window is eligible for review. Spatial coverage, usable
pixels and identification are evaluated separately. An empty time window
describes the currently indexed products.
