# Maritime-domain compartments

Status: **phase 1 implemented** (the tag, its inference, the operator filter, the
public allow-list). Phases 2–3 (AIS-anomaly detector extensions, free connectors,
public piracy layer, archived-drift recompute) are planned — see `docs/roadmap.md`.

SeaCommons started as a migrant search-and-rescue OSINT system. The same
pipeline — a shared AIS feed, OSINT ingestion, a canonical intel-event model with
fail-closed public/private policy, and OpenDrift trajectories — covers other
maritime-awareness "compartments". Migrant SAR remains the primary operational
lane; the compartment tag lets the other lanes coexist without changing how the
public Live map behaves.

## The tag

Every `IntelEvent` resolves a `maritime_domain` (in
`core/intel/store.py::IntelEvent.maritime_domain()`):

| Compartment | Covers | Default posture |
| --- | --- | --- |
| `sar` | migrant + general distress; the primary lane | **public** |
| `sanctions` | sanctions evasion / dark fleet — identity manipulation, spoofing, ship-to-ship transfers, shadow tankers | operator-only |
| `grey_zone` | infrastructure / grey-zone — undersea cables (anchor-drag), GPS jamming, sensitive-zone incursion | operator-only |
| `iuu_fishing` | illegal / unreported / unregulated fishing — EEZ & MPA incursion, AIS gaps, anomalous fishing effort | operator-only |
| `piracy` | piracy & armed robbery at sea | **public** (allow-listed) |
| `smuggling` | route deviation, dark operations, irregular port calls | operator-only |
| `environmental` | oil discharge, spills, illegal dumping | operator-only |
| `safety` | collision, grounding, fire, breakdown | operator-only |

An explicit `metadata["maritime_domain"]` always wins. Otherwise the domain is
inferred from `event.type` and, for `ais_anomaly`, from
`metadata["anomaly_type"]`. Unset / unknown → `sar`, so nothing pre-dating this
change moves compartment.

## Public Live posture

The public Live map stays SAR-distress-only by default. A non-`sar` event reaches
the public feed only if:

- its compartment is in `PUBLIC_MARITIME_DOMAINS` (env, comma-separated;
  default `sar,piracy`; `sar` is always included), **or**
- an operator explicitly set `publication_status="published"` on it.

The two privacy-absolute rules are unchanged: an explicit `private` mark can never
be overridden, and a blocked/unofficial source is never exposed
(`core/intel/public_policy.py`).

## Case taxonomy

`CASE_TYPES` (`core/api/routes/cases.py`) gains `sanctions_watch`,
`dark_rendezvous`, `subsea_infrastructure`, `piracy_incident`. Drift routing
(`core/drift/profiles.py`) treats most as monitoring-only; `dark_rendezvous` maps
to a tanker profile for spill-contingency drift.

## Sources per compartment (planned)

| Compartment | Free sources |
| --- | --- |
| `sanctions` | OpenSanctions Maritime (consolidated EU+UN+OFAC vessel/owner list, daily); Global Fishing Watch Events API (STS encounters, AIS gaps) |
| `grey_zone` | submarine cable route geometry (TeleGeography); gpsjam.org (already wired) |
| `iuu_fishing` | Global Fishing Watch (fishing effort, loitering, port visits); VIIRS boat detections |
| `piracy` | IMB Piracy Reporting Centre, ReCAAP ISC, UKMTO advisories |
| `environmental` | Sentinel-1 SAR oil-spill detection (Copernicus); NASA FIRMS thermal |
