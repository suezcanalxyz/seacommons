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
