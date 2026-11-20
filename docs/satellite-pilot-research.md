# SeaCommons satellite pilot: source research and implementation brief

Research snapshot: 20 November 2026. Scope: retrospective review of public
maritime and humanitarian dossiers in PLAY. CONTSHIP JET is the first case
to investigate for an additional scene. Historical Lampedusa scenes serve
as detector fixtures. An aperture footprint, a radar return, a vessel
identity and an incident attribution are four different observations or claims.

## Findings already verified

| Case | Finding | Interpretation |
|---|---|---|
| CONTSHIP JET, 28 October 2026 | The maritime notice records 10:00 UTC; AP places the event shortly before 13:00 local time. A letter circulated by the UN records the date and area. | Treat the notice time as a search reference with uncertainty. The news and letter do not establish an exact satellite target or acquisition. |
| CONTSHIP JET optical | Sentinel-2 at 09:00:59 UTC. The SCL value was 9 at the point in the maritime notice. | High-probability cloud at the sampled pixel. Tile-wide cloud percentage is a separate measurement. |
| CONTSHIP JET radar | Sentinel-1 RTC on 30 October at 04:13:22 UTC. The tested local crop returned zero detector candidates. | The acquisition is over 42 hours after the report reference. A zero on this crop carries no conclusion about presence during the event. |
| Humanitarian archive | Of 22 Sentinel-1 products already indexed in three pilot dossiers, zero fell within six hours either side of the first public report. | Coverage discovery is incomplete. Report time is a proxy where actual event time is unknown. |
| Lampedusa historical pilot | Five June 2024 RTC crops produced nine water-masked candidates. On 22 June the mask removed five land returns and retained one offshore return. | Verified processing fixture. No independently identified vessel or complete vessel inventory for these crops. |

Primary references: [maritime notice 759/26](https://www.sealagom.com/coastal/127/message/49690/759-26-black-sea/),
[AP](https://apnews.com/article/357e91838a3695acb39d3e361bc2fe72),
[UN correspondence](https://digitallibrary.un.org/record/4132352/files/A_81_472--S_2026_882-EN.pdf),
[optical catalog item](https://stac.dataspace.copernicus.eu/v1/collections/sentinel-2-l2a/items/S2B_MSIL2A_20261028T090059_N0513_R007_T35TPH_20261028T131234),
[radar catalog item](https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/S1C_IW_GRDH_1SDV_20261030T041309_20261030T041334_010109_0142D7_rtc),
[Sentinel-2 SCL semantics](https://s2.pages.eopf.copernicus.eu/msi/s2msi/1.3.0/sum/payload-l2a.html).

## Source decisions

| Source | Use in the pilot | Access, evidence and restrictions |
|---|---|---|
| Copernicus Data Space STAC + OData | Primary discovery for Sentinel-1 GRD and Sentinel-2 L2A. Get exact product IDs, geometries, time spans and band metadata. | STAC metadata and asset download are separate. Original OData product downloads require bearer authentication. Preserve Copernicus attribution and product provenance. [STAC](https://documentation.dataspace.copernicus.eu/APIs/STAC.html) · [OData](https://documentation.dataspace.copernicus.eu/APIs/OData.html) · [Sentinel terms](https://cds.climate.copernicus.eu/licences/ec-sentinel) |
| Microsoft Planetary Computer Sentinel-1 RTC | First operational raster path. Request bounded VV/VH COG windows from the catalog item. Use local GDAL with native resolution and valid-pixel masks. | Public item lookup and the signing route worked for the pilot. Sign just before reading. Persist the unsigned item URL, product ID and downloaded-window hash. Drop signed query strings from logs and output. [Signing documentation](https://planetarycomputer.microsoft.com/docs/concepts/sas/) |
| ASF OPERA RTC-S1 | Alternative calibrated archive to evaluate when Planetary Computer RTC coverage or availability is limited. | Validate collection, registration/download flow and pixel spacing before enabling. Match underlying Sentinel acquisition across providers so one pass counts once. [JPL product documentation](https://www.jpl.nasa.gov/go/opera/products/rtc-product/) |
| Sentinel-2 L2A | Optical complement where an acquisition is close and the actual area is visible. | Read the local SCL and valid-data mask. Use bands at their native resolution and preserve cloud and nodata limitations. Visual items and preview thumbnails are context. [CDSE Sentinel-2](https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-2) · [SCL](https://s2.pages.eopf.copernicus.eu/msi/s2msi/1.3.0/sum/payload-l2a.html) |
| Natural Earth and ESA WorldCover | Natural Earth reproduces the coastal pilot. WorldCover is a secondary candidate for improving shoreline review. | Compare quality around harbours and islands with independent coastline data. Land-cover classes and shoreline geometry have different meanings. Select and record one mask version per run. [Natural Earth](https://www.naturalearthdata.com/downloads/10m-physical-vectors/) · [WorldCover v200](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200) |
| Global Fishing Watch | Compare SAR returns and detection footprints. Use published AIS association as a separate record where its source permits. | API returned 401 on the earlier unauthenticated attempt. Raw AIS is commercial and unavailable as a public GFW download. A GFW detection on the same acquisition is an algorithm comparison, with one underlying satellite observation. [SAR datasets](https://globalfishingwatch.org/platform-update/2024-may-data-download-portal-new-dataset-released-featuring-vessel-detections-from-sentinel-1-sar/) · [Raw AIS FAQ](https://globalfishingwatch.org/faqs/can-i-download-raw-ais-data/) |
| xView3-SAR | Compare the local contrast baseline with an annotated historical benchmark. Add a held-out Mediterranean set with manual adjudication. | Labels combine manual and automated evidence and have confidence tiers. Split by acquisition and geography to limit leakage. Report results separately by label confidence and distance to shore. [Paper](https://proceedings.neurips.cc/paper_files/paper/2022/hash/f4d4a021f9051a6c18183b059117e8b5-Abstract-Datasets_and_Benchmarks.html) · [Label methods](https://proceedings.neurips.cc/paper_files/paper/2022/file/f4d4a021f9051a6c18183b059117e8b5-Supplemental-Datasets_and_Benchmarks.pdf) |
| Umbra Open Data and Capella Open Data | Read-only search for higher-resolution archival SAR examples, including the historical CONTSHIP JET window if items overlap. | Open programs are selected subsets. Confirm license and attribution on the item. Neither catalog has yielded a verified CONTSHIP JET acquisition in this research. [Umbra](https://umbra.space/open-data/) · [Capella](https://support.capellaspace.com/how-do-i-access-capellas-open-data) |
| ICEYE, Planet SkySat and Vantor | Commercial archive discovery after checking open sources. Request item IDs, time and footprint before considering an order. | Account access, pricing, historical inventory and redistribution rights vary. Historical archive discovery and new tasking are different workflows. Obtain explicit approval before an order. [ICEYE products](https://sar.iceye.com/) · [Planet Data API](https://docs.planet.com/develop/apis/data/) · [Vantor archive](https://pro-docs.maxar.com/en-us/Imagery/Imagery_ordering_archive.htm) |

## Codex implementation brief

Start from `scripts/play_satellite_analysis.py`, `scripts/run_satellite_pilot.py`,
`scripts/review_satellite_returns.py` and `scripts/export_humanitarian_archive.py`.
PLAY already renders selected satellite metadata and source links. Reuse the
existing public incident projection and keep acquisition jobs out of web requests.

1. **Discovery.** Introduce provider adapters with a common manifest: case ID,
   reference kind and time window, acquisition start/end, platform, product ID,
   geometry, unsigned source URL, polarization, and access/license status.
   Query by area and time, then intersect the actual footprint. Track partial
   coverage, missing observations and provider errors separately. Reuse scenes
   across overlapping historical dossiers without counting them twice. Start
   with the three existing humanitarian cases, then backfill the historical
   archive in bounded batches subject to provider quotas. Missing or uncertain
   case location stays explicit.
2. **Raster review.** Fetch bounded COG windows using short-lived credentials.
   Record CRS, pixel window, raster checksum, mask identity, algorithm version
   and dB stretch next to each reproducible candidate ID. Retain separate
   rejection reasons for land, cloud, nodata and out-of-window acquisitions.
3. **Validation.** Score the existing detector on held-out annotated scenes
   with one-to-one spatial matching. Report precision, recall, false positives
   per scene, evaluated area and excluded/no-data areas. Evaluate by shoreline
   distance and vessel size. A reviewer queue without complete labels can
   summarize decisions; it cannot estimate missed boats.
4. **PLAY review.** Import candidate records idempotently by scene and return ID.
   Show source, original time, footprint, peak pixel and authorized raster crop.
   Store reviewed vessel/non-vessel/inconclusive outcomes with audit provenance.
   AIS and DSC can supply time-compatible evidence with their own uncertainty.
   Coverage, an unidentified return and a match should each remain visible as
   distinct evidence states. Humanitarian public projections must use the
   existing location protection and source publication rules.
5. **Execution.** Run in bounded historical batches first, with resumable job
   state and read-only provider access. Defer periodic scheduling until the
   batch is validated and quotas and failure handling are known.

### Acceptance checks

- Replay CONTSHIP JET from the public dossier. Preserve both verified catalog
  references, distinguish high-probability optical cloud at the point from
  overall scene cloud, and preserve the radar time offset. If commercial
  access is unavailable, record that state explicitly rather than an empty
  inventory. A further confirmed scene may be one of the sources used for
  review, subject to its footprint, acquisition time and publication terms.
- Reproduce Lampedusa 22 June with and without the coast mask. Keep the
  surviving peak pixel and candidate ID stable. No output is attributed to a
  specific incident without evidence.
- Replay the three humanitarian dossiers and distinguish the first public
  report from a documented actual event time. An empty review window must stay
  separate from a successfully analyzed crop with zero detections.
- Exercise tests for provider timeout/auth failure, pagination, duplicate
  acquisitions, missing coordinates, partial coverage, masking and historical
  time cutoffs. Verify repeated ingestion preserves reviewer decisions.
- Keep credentials, signed links, private locations and licensed rasters out
  of git and public responses. Smoke-test the review surface against an
  explicitly authorized candidate before enabling ingestion in production.

## Follow-up research: independent acquisitions and detector limits

### Catalog experiment on CONTSHIP JET

A public NASA CMR granule search for collection `OPERA_L2_RTC-S1_V1` at the
position in notice 759/26 returned four records for 27–31 October 2026 UTC.
The search checked metadata availability, without downloading authenticated
ASF assets. The OPERA granules have 30 m pixel spacing.

| Acquisition start (UTC) | OPERA platform / swath | Interpretation |
|---|---|---|
| 30 Oct 04:13:13 and 04:13:14 | S1C, IW1 and IW2, burst group T036-075995 | Overlapping products from the same pass already examined in the Planetary Computer RTC crop. |
| 31 Oct 04:05:18 | S1D, IW3, T138-295085 | Later pass, also represented in the previous Copernicus GRD search. |
| 31 Oct 15:59:40 | S1C, IW2, T058-122686 | Later pass, also represented in the previous Copernicus GRD search. |

The fourth catalog row adds no independent observation. Grouping by platform,
acquisition and original scene or orbit prevents doubling the evidence when
CDSE GRD, Planetary Computer RTC and OPERA RTC expose the same pass. Preserve
the original product identifiers and individual release times in the manifest.
The observed first radar pass remains about 42 hours after the incident
reference. Commercial availability in the earlier window remains unverified.

Reproduction: use [NASA CMR](https://cmr.earthdata.nasa.gov/search/granules.json)
with `short_name=OPERA_L2_RTC-S1_V1`, the point from notice 759/26, and
`temporal=2026-10-27T00:00:00Z,2026-10-31T23:59:59Z`. Check the CMR hit
count, then compare each granule's acquisition time with the original Sentinel
products before actually ordering or downloading another copy.

[ASF access and coverage](https://docs.asf.alaska.edu/datasets/using_ASF_data/) ·
[OPERA RTC-S1 product specification](https://d2pn8kiwq2w21t.cloudfront.net/documents/ProductSpec_RTC.pdf) ·
[CDSE Sentinel-1 collection and deferred availability](https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-1)

### Small-craft detectability

Sentinel-1 IW GRD HR is sampled on a 10 m grid with approximately 20 × 22 m
spatial resolution. Pixel spacing is smaller than the effective resolution.
A radar-bright return can be spatially unresolved, so a bright cluster's
pixel count should not be used as a hull-length estimate. A small,
low-contrast craft can be missed due to material, orientation, waves,
incidence angle and available resolution. An empty detector output on a
technically valid scene is still inconclusive for a small craft.

Keep three classes of output in the evaluation: a candidate marker for review,
an analyzed acquisition with no qualifying return, and a failure to acquire or
evaluate usable pixels. Separate coastal false positives such as docks and
fixed infrastructure from radar artifacts. Evaluate how much real vessel
coverage an aggressive shoreline buffer would discard.

[Sentinel-1 product definition, table 5-1](https://sentiwiki.copernicus.eu/__attachments/1673968/S1-RS-MDA-52-7440-Sentinel-1-Product-Definition-2025-2.8.pdf) ·
[JRC SUMO manual, ship detection and ambiguity flags](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC107063/sumomanual2017_v17.pdf)

### What to implement and measure first

| Stage | Design choice | Evidence to record |
|---|---|---|
| Discovery | Use CDSE to discover and fingerprint original acquisitions, Planetary Computer for the first RTC raster route and ASF CMR as an alternate index. | Footprint overlap, acquisition start/end, report-time uncertainty, pixel access status and underlying acquisition key. |
| Calibration | Freeze the current contrast detector, then compare it against SUMO on a held-out slice of xView3. Establish offshore, coastal and port strata before tuning. Include reviewed small craft and shoreline negatives. | Scene counts, independent label availability, matches, unmatched annotations, false candidates per scene, masked area and input confidence tiers. |
| Association | Retain source-record and acquisition identifiers in PLAY. Evaluate AIS and DSC from original observation time and the published uncertainty, with event timing distinct from first report. | Compatible, conflicting or unavailable source evidence, with observed/modelled positions kept distinct. |
| Humanitarian review | Use original publisher chronology for reports, retain upstream references, and apply existing coordinate protections in public output. IOM Missing Migrants can add retrospective fatal or missing incident context for applicable cases. | Different sites may repeat one report. IOM includes estimated coordinates and describes counts as a minimum estimate. Do not substitute those coordinates for an observed vessel fix. |

Keep threshold selection on development scenes. Reuse fixed thresholds and
one-to-one matching rules for validation. Report omissions separately for a
whole-scene archive gap, a partly observed search region, an inaccessible asset,
and a usable crop with no qualifying return. Start the first PR implementation
with discovery and evidence provenance. Raster queues and publication should
depend on verified access and the existing case policy.

[xView3 benchmark and evaluation](https://proceedings.neurips.cc/paper_files/paper/2022/file/f4d4a021f9051a6c18183b059117e8b5-Paper-Datasets_and_Benchmarks.pdf) ·
[IOM methodology and estimated coordinates](https://missingmigrants.iom.int/sites/g/files/tmzbdl601/files/publication/file/fatal_journeys_3_part2.pdf)

## Historical PLAY re-review: image analysis and claim definitions

Review the whole archive in two passes. First inventory the public cases and
record which claims and phases can be searched. Then analyze eligible imagery,
with the original observations and review history preserved. The inventory
includes cases with missing location or time and never silently drops them.
For a full backfill, prefer a stable catalog snapshot and checkpoint by case ID.
Record the catalog time and keep accession coverage separate from image quality.

### One claim, one spatial and temporal scope

A review record must state the question (presence, identity, visible damage,
change, spill-like feature or historical outcome), phase (before, during or
after), reference source, UTC time/interval and its uncertainty, and the
public-safe area relevant to that phase. The first report time is a fallback
reference, explicitly labelled. A port phase needs an independent arrival or
tow corroborator and a berth, anchorage or sufficiently bounded harbour search.
The incident crop and a follow-up port crop have separate coverage results.

| Term | Definition in PLAY |
|---|---|
| Catalog overlap | Provider geometry intersects the search area. This guarantees neither valid pixels nor an acquisition in the relevant interval. |
| Usable coverage | Valid pixels cover the relevant area during the relevant interval, with instrument, resolution and conditions suitable for the stated feature. Record partial or unknown coverage. |
| Detected return | A georeferenced pixel cluster or reviewed visible object with a reproducible source, crop and algorithm. SAR brightness alone does not establish vessel identity. |
| Supported | An observation supports the stated claim within the recorded scope. Identity and incident attribution require their own evidence. |
| Conflicting | A usable observation contradicts a specific claim. Record the conflicting source, place, time and limits. |
| No qualifying detection | Usable pixels were evaluated and no return met the rule. Keep this distinct from a general absence finding. |
| Not evaluable | Missing case reference, no acquisition in scope, incomplete coverage, obscuration, insufficient resolution, or failed asset access. Preserve the reason. |

An absence finding can rule out a narrow presence claim only if the defined
area was adequately observed in the stated interval, the expected object
would be detectable, and independent review supports the finding. It does
not rule out movement outside the footprint or an event before or after the
acquisition. Never label historical distress disproved solely because the
detector returned zero.

### Pixel-level method

- **SAR:** select calibrated backscatter, record polarization, pixel spacing
  and effective resolution. Use nodata and a coastline mask for open water.
  Record the peak pixel, georeferenced crop, local contrast and review nearby
  structures and radar ambiguity artifacts. In ports, inspect the berth and
  compare against a pre-event view rather than treating a bright cluster as
  an identified ship. For change review, prefer comparable orbit/view,
  polarization and processing, align the rasters and retain both source IDs.
- **Optical:** inspect the local cloud, shadow and valid-data mask over the
  subject rather than relying on tile-wide cloud percentage. Review native
  pixels, source time, visible dimensions and shadows. Attribute visible
  changes only where resolution and viewing conditions support the feature.
- **Cross-check:** compare candidates against original AIS, DSC, port or
  operator records using their own timestamps, position uncertainties and
  provenance. Keep acquisition, publication and review times separate.
  Archive each review decision and its rationale without overwriting the
  original report. Apply existing protections to humanitarian location data.

[ESA ship detection capability](https://knowledge-hub-gda.esa.int/eo_capability/ship-detection/) ·
[JRC SUMO review and ambiguities](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC107063/sumomanual2017_v17.pdf) ·
[Copernicus EMS guidance on imagery](https://mapping.emergency.copernicus.eu/about/using-of-earth-observation-data/)

Backfill first produces coverage counts, not a new incident verdict:
total cases, searchable phases, usable scenes, unresolved candidates,
supported or conflicting claims and cases with no usable evidence. Use
CONTSHIP JET to verify that a delayed incident-site crop and any separately
documented follow-up location remain distinct. Retain the three humanitarian
dossiers as timing/reference tests and Lampedusa as the pixel fixture.

Initial inventory, 20 November 2026: all eight public API pages returned
3,879 distinct IDs (3,720 maritime and 159 humanitarian), including 3,827
records with a nonempty geometry and 106 with the public satellite flag.
The flag measures what the catalog marked, not whether usable imagery exists.
Geometry is an inventory field and must be checked for its source and
precision before being used as a search anchor. This inventory covers the
API catalog, which also includes recent reports and excludes separately
bundled reviewed entries. It is not an image review.

## LIVE detections and retrospective evidence

Treat a recent observation and its publication as separate clocks. A
satellite target in a near-real-time product represents the overpass time,
and may be unavailable until much later. An advertised delivery target
applies to eligible products and starts at sensing, not at the case report.
Show `acquired_at`, `available_at` when known, `ingested_at` and the data age.
Never substitute the ingestion timestamp when the acquisition time is missing.
[WMO satellite and product timeliness](https://space.oscar.wmo.int/satellitestatuses/status)

| Workflow | Eligibility | What the reviewer sees |
|---|---|---|
| LIVE · fresh satellite detection | A reviewed or qualifying observed feature with valid pixels, geographic overlap and age within the configured LIVE window for that product. Validate the policy for humanitarian publication first. | Sensor, acquisition UTC, age, crop and precise evidence claim. An unidentified return stays unidentified. No marker is created by cloud-free coverage or a catalog hit alone. |
| PLAY · at-event reconstruction | Acquisition overlaps the documented event window and search area. | Scene and claim side by side with timing uncertainty and the usable footprint. Historical replay does not create a new LIVE sighting. |
| PLAY · later follow-up | Source documents a new phase and location, such as a reported berth or tow destination. | Acquisition compared with the relevant phase, with time since event and time since phase reference shown separately. A later image can support presence or visible change at the later location. |
| No valid observation | Coverage, useful pixels, access or event timing is missing. | Explicit reason, provider query and interval. Keep this state distinct from an evaluated crop with no qualifying return. |

Late provider delivery can add evidence to a historical dossier while
preserving its original sensing time. A follow-up observation can be recent
in the LIVE feed and linked to an older incident in PLAY when independently
eligible as a new observation. That linkage still preserves separate claims
and acquisition IDs.

## Open visualizations by mission

A viewer is the human inspection surface. The analytical pipeline uses dated,
georeferenced source pixels and per-pixel quality masks. Public catalog
metadata, open-source viewer code and redistribution rights are three
separate properties.

| Mission | Viewer and access | SeaCommons visualization and role |
|---|---|---|
| EU · Sentinel-1 | [Copernicus Browser](https://dataspace.copernicus.eu/browser/) ([open-source code](https://github.com/eu-cdse/copernicus-browser)); [CDSE STAC](https://documentation.dataspace.copernicus.eu/APIs/STAC.html) and RTC COG routes for pixels | Dated VV grayscale in dB with source and footprint. Optional VH or VV/VH comparison with matched polarization and geometry. Use a candidate marker on the exact crop; show after/before alignment for port or coastline review. |
| EU · Sentinel-2 L2A | [Copernicus Browser](https://documentation.dataspace.copernicus.eu/Applications/Browser.html); [L2A SCL specification](https://s2.pages.eopf.copernicus.eu/msi/s2msi/1.3.0/sum/payload-l2a.html) | B04/B03/B02 natural colour with local SCL cloud and shadow overlay. A separately named SWIR composite may assist environmental context. Avoid equating upsampled SWIR with native 10 m visible detail. |
| EU · Sentinel-3 OLCI / SLSTR | [Copernicus Browser](https://dataspace.copernicus.eu/browser/) and product catalog | Regional ocean-colour or thermal context with date, units and quality flags. Keep on regional zoom and out of vessel-candidate ranking. |
| US · VIIRS (Suomi NPP, NOAA-20/21) and MODIS | [NASA Worldview](https://worldview.earthdata.nasa.gov/) ([open-source code](https://github.com/nasa-gibs/worldview)); [NASA FIRMS](https://www.earthdata.nasa.gov/data/tools/firms) for thermal anomalies | Dated corrected-reflectance basemap or regional smoke/thermal context. Display time and spatial scale. A FIRMS anomaly is a thermal anomaly and cannot on its own identify a ship or prove a ship fire. |
| US · Landsat 8/9 OLI/TIRS | [USGS EarthExplorer](https://earthexplorer.usgs.gov/) for search/preview/download. [LandsatLook](https://landsatlook.usgs.gov/) announces that its viewer is retired. | Use optical before/after and regional environmental or port changes. Render documented band combinations per product and preserve QA flags. US-hosted ASF OPERA RTC feeds the EU Sentinel-1 row because it processes that same European acquisition. |
| China–Brazil · CBERS-4A WPM | [INPE product page and Data Cube Explorer/STAC](https://data.inpe.br/dados/cbers-4a/) | View native 2 m panchromatic and 8 m multispectral as separate layers, or label a pan-sharpened view as derived. Promising for a historical footprint where an actual public item is present. Mediterranean product availability remains unverified. |
| China · SDGSAT-1 | [Open Science Program](https://www.sdgsat.ac.cn/) and [sensor description](https://www.sdgsat.ac.cn/satellite/describe) | Glimmer panchromatic 10 m / RGB 40 m can provide night-light context. Use acquisition-specific masks and compare with non-maritime light sources. Archive access and relevant pixels for this pilot remain unverified. |
| China · Gaofen | [CNSA's open-data announcement](https://www.cnsa.gov.cn/english/n6465652/n6465653/c6808065/content.html) covers 16 m multispectral Gaofen‑1/6; evaluate the linked catalog on an actual area and date. | Treat proposed optical views as archive discovery until access and terms are verified. The announcement does not establish open global Gaofen‑3 SAR access. Leave products requiring separate authorization disabled. |

Historical replay must retain the original styles and timestamps for the two
CONTSHIP JET references. The cloud-obscured optical pass and the later radar
crop belong to different questions. The 3,879-ID PLAY inventory can be
reprocessed in batches, with an explicit state for missing geometry, missing
time and unavailable pixels. Discovery puts priority on the three human
dossiers and known phases such as documented arrivals or rescue reports,
while preserving the full historical inventory.

### Acceptance checks for LIVE/PLAY and visualization

- A delayed scene never becomes a current observation by timestamp substitution.
  Missing acquisition time and unknown publication latency render explicitly.
- An at-event crop and a recovery/port crop use different reference windows,
  recorded coverage and evidence claims, even when attached to the same dossier.
- Each rendered layer exposes source, date, sensor/bands and rendition method.
  Regional composites, derived styles, original pixels and catalog footprints
  are labelled distinctly. Provider-specific access failures are visible.
- Verify one actual item, its pixel access and publication conditions before
  enabling a new mission. A catalog result outside the region stays out of
  the historical evidence review. Leave unverified adapters disabled.

## OSINT practice in PLAY: Landsat 8 quality flags

The historical CONTSHIP JET dossier includes the date and exact product ID of
the Landsat 8 pass on 29 October 2026 at 08:51:16 UTC, about 22 h 51 min
after the incident time in notice 759/26. The USGS Level-2 scene lists 3.9%
tile-wide cloud cover. A native-resolution crop of QA_PIXEL, red, green and
blue around the reported point covered 83 × 80 pixels. All 6,640 QA pixels
set bits 5 and 6 (high-confidence snow and clear of both specified cloud
bits), and zero set the water bit. The precise point held QA value 30048.
The central visible-band reflectances after USGS scaling were approximately
1.15, 1.17 and 1.23. They are an additional reason to withhold interpretation;
these values do not identify the material or the source of the inconsistency.

In the reviewed dossier the scene is context for a lesson, with no vessel
attribution and no inferred position marker. The expandable lesson separates
observation, interpretation and limits. The +42 h radar scene has a second
exercise about a detector result with zero qualifying returns. The questions
are visible before the explanation, so the display can be used for training
without changing the evidentiary status of the source record.

[Original Landsat product](https://planetarycomputer.microsoft.com/api/stac/v1/collections/landsat-c2-l2/items/LC08_L2SP_181030_20261029_02_T2) ·
[USGS QA bit definitions](https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands) ·
[Berkeley Protocol on Digital Open Source Investigations](https://digitallibrary.un.org/record/3973652/files/OHCHR_BerkeleyProtocol.pdf)
