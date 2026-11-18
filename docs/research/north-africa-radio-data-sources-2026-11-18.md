# North African maritime radio and corroboration sources — research intake

Date: 2026-11-18. Status: **candidate data sources, none activated**. Do not treat free-to-view directory content as open-licensed API or permission to continuously connect to third-party radio hardware.

| Source | Kind | Geographic role | Integration action | License / validation gate |
|---|---|---|---|---|
| https://map-sdr.p00lack.cc/ | SDR map (Kiwi, OpenWebRX, WebSDR, PhantomSDR+, Web-888) | Additional discovery worldwide | Audit machine-readable feed and dedupe physical lineage | Data reuse, public automation, provenance, actual tuning/audio |
| https://sdr.shbrg.nl/sdr/ | SDR list / various receiver families | Global additional catalogue | Determine documented interface, rate limits | Terms, slots, reliability |
| https://rx-888.com/ | Web-888 directory | Potential additional HF stations | Adapter feasibility assessment | Protocol + operator permission |
| https://rx-tx.info/ | SDR locator directory | Geo-targeted North African discovery | Metadata ingestion, not active monitoring | Catalog license, receiver authorization |
| https://www.12db.de/websdr/ | Uptime/status directory | Availability ranking | Investigate published reuse mechanism | Rate limit, data reuse |
| https://www.itu.int/en/itu-r/terrestrial/mars/pages/default.aspx | ITU maritime station registry | Tunisia / Libya coastal station identities and frequencies | Join on MMSI / call sign and station identity | Official reference; not an RF feed |
| https://www.ommp.nat.tn/trafic-des-navires/ | Tunisia government port movement view | Tunisia port event corroboration | Review official publication and automation rights | Not confirmed open API |
| https://catalog.data.gov.tn/fr/dataset/les-services-de-securite-maritime | Tunisia government open data | Maritime safety service directory | Review data download/license/refresh | May be metadata, not live distress |
| https://lpma.gov.ly/en/statistics | Libya national port statistics | Libya historical traffic baselines | Manual metadata and historical aggregate import after license review | Not real-time |
| https://navtex.online/feeds | NAVTEX published feeds | Mediterranean safety messages | Evaluate feed schema, commercial/redistribution rights; label secondary copies | Not direct radio reception |
| https://navtex.online/legal/data-sources | NAVTEX provenance | Source classification | Preserve per-record upstream/source/copy status | Check each upstream conditions |
| https://www.sealagom.com/api/docs/ | Maritime warnings API and RCC/coast station reference | Coast station context | Evaluate integration with per-record attribution | CC BY 4.0 stated on provider page; confirm endpoint coverage |
| https://www.sealagom.com/navtex/ | NAVTEX messages | Safety context and enrichment | Evaluate non-duplicating ingest after license review | Secondary publication |
| https://globalfishingwatch.org/our-apis/documentation/ | Vessel identity, AIS/radar indicators | Correlating vessels near Tunisian/Libyan coasts | Integrate authorized API token, entitlement and geographical scope | Terms/API token |
| https://emodnet.ec.europa.eu/en/physical-parameters | Ocean observing network | Sea conditions / drift corroboration | Use standards-based services | Attribution |
| https://data.marine.copernicus.eu/product/MEDSEA_ANALYSISFORECAST_PHY_006_013/services | Mediterranean ocean models | Track/drift context | Use programmatic service | Copernicus licence |

## Findings
* No currently verified publicly accessible SDR receiver physically in Tunisia or Libya from researched directories. **Do not invent an SDR pin**.
* Existing Oracle receiver inventory: 421 catalogued, 322 HTTP reachable, 405 review_required, 8 eligible, 3 active (audit earlier on 2026-11-18). This is NOT evidence of 322 usable signal streams.
* Highest-value next moves: add Web-888 + PhantomSDR+ *discovery*, evaluate YaDDNet DSC logs (terms unknown), import ITU coast station metadata and licensed NAVTEX alerts as separate source classes, assess OMMP Tunisia port calls and Libyan government maritime aggregates. Provide adapters only after schema and rights verification.
* Explicitly distinguish coastal transmitter from independent SDR receiver; distinguish metadata, historical aggregates, crowdsourced receive copy, verified decode and incident.
* Planned North African geographies: Bizerte–Tunis–Kelibia–Sfax–Gabes–Djerba; Tripoli–Misrata–Sirte–Benghazi–Tobruk. These are survey regions, not known receiver coordinates.
