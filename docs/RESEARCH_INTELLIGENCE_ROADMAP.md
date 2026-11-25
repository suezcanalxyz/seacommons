# SeaCommons — Research Intelligence Upgrade (2026-11-25)

Status: active execution roadmap, not a claim of completed functionality.
Owner: SeaCommons engineering / research. Scope: LIVE, PLAY, canonical evidence pipeline and research publication. Read alongside [updates.md](updates.md), [LEGACY.MD](LEGACY.MD), [ARCHITECTURE.md](ARCHITECTURE.md), and master program [#431](https://github.com/suezcanalxyz/seacommons/issues/431). This roadmap defines the next research upgrade; existing privacy, CI, evidence and migration invariants remain binding. Reuse existing issues and canonical objects rather than duplicate work.

## Mandate to the implementation agent

FIRST: sync main, establish the actual production status, and perform a legacy/dependency audit BEFORE adding any new architecture. Produce a written, reproducible status report and a before/after legacy inventory. Remove dead legacy and migrate internal consumers to one canonical path. Then implement this roadmap in small tested work packets, iterating until all nine maturity gates reach evidence-backed 5/5 or a specific blocker is documented. Do not stop at recommendations, mockups, dashboards or a sample-only analysis. The objective is retrospective analysis of ALL recoverable data and a useful, performant PLAY, not further accumulation of unprocessed records.

Work in dependency order, using existing PR/CI rules. Read the open master issues #334, #335, #336, #367, #431–442, #533 and current PRs before opening new work. Reuse or supersede obsolete work only after checking dependencies. No unreviewed bulk production writes, destructive migrations, unverified publication, forced merges, or fabricated evidence. Record real commands, revisions, tests, counts, failures and limitations; do not mark a gate complete because code exists.

## 0 — Baseline observed on 25 November 2026 (refresh before work)

Read-only Oracle and API audit at approximately 13:43 UTC. Snapshot, not a fixed target:
- LIVE and PLAY websites and edge health returned HTTP 200; API active, database ready. This does not establish correct rendered content.
- VM disk 85% used, approximately 6.9 GiB free. Checkout b919248; inspected GitHub main 1d1f663; runtime pipeline revision 790c460e30c2. Reconcile actual deployed code and running process, not just checkout.
- PLAY counts first returned 3,957; full subsequent paginated scan returned 3,962 distinct catalog IDs (3,799 maritime, 163 humanitarian). Dates 2024-10-19 to 2026-11-25, not continuous coverage. 172 humanitarian main_category vs 163 domain; reconcile the nine-record difference.
- Catalog status: 3,354 open, 435 resolved, 75 outcome_unknown, 72 needs_review, 21 review_ready, 3 published, 2 active. Maritime open 3,354; humanitarian 72 needs_review, 63 outcome_unknown, 26 resolved, 2 active. States currently mix lifecycle and review/publication; audit their semantics.
- 32 flagged corroborated (0.81%); 3,930 not flagged; 3,753 single_source_observed; 110 has_satellite flags, not validated imagery. 3,787 episode-backed records.
- 3,393 dark_transit case_type; 3,369 gap_episode family; 219 position_spoofing, 123 safety_event, 37 covert_rendezvous, 8 port_call, 7 infrastructure_pattern, 113 distress and 26 missing. Labels are candidates, not facts or accusations.
- Reason codes: LOCAL_AIS_COVERAGE_HEALTHY 2,646; PROLONGED_OFFSHORE_GAP 2,443; OPEN_GAP_COVERAGE_NOT_TRACK_CONTINUOUS 1,541; STRONG_RECEPTION_EXPECTATION 327; NEIGHBOUR_TRAFFIC_CONTINUED 327. These overlap; validate intersections. Only four BEHAVIOUR_EXPECTED counter-indicator entries visible in catalog.
- LIVE signals returned one feature from 600 memory candidates and 53 durable Alarm Phone candidates; hypotheses zero. Determine eligibility, lifecycle, deduplication, source freshness, API-vs-edge-vs-UI discrepancy before assuming suppression or broadening gates.
- Radio pipeline: 4/7 active, 87 validated/persisted DSC messages, zero strong AIS correlations, 27,216,477 processed frames, 19,606 continuity resets, 3,413 failovers (since process start). Partner/radio degraded; AIS reports legacy mode.
- Internal artifacts: 14 OSINT dossiers (13 area-report clusters, 1 historical incident candidate, all needs_review); 30 sanctions shipping dossiers; bounded 200 designation-row sample, 8 observed locally and 192 no recent local AIS. No extrapolation to fleet prevalence or intent.
- main gap-closure protocol requires exact reappearance identity/source attestation; producer not yet implemented in inspected documentation. Confirm runtime behavior and audit stored closures.
- Historic export of 2,582,479 source_observations was previously reported complete; independently verify manifests, actual recoverability and coverage, not an asserted current database count.

## P0 — Status, data integrity, legacy removal (mandatory first)

1. Produce dated status artifact: deployed SHA per surface/worker, DB schema/migration heads, CI, source health/freshness/coverage, queue lag, disk/CPU/RAM, R2 manifests/checksums, actual restore/replay test, live vs edge vs rendered UI, PLAY counts and cache behavior. Compare against this baseline and explain every material delta. Record unavailable evidence.
2. Inventory legacy routes, models, taxonomy, duplicated event paths, feature flags, fallback values, serializers, frontend adapters, unused scripts and stale docs using LEGACY.MD. Table: component / file / consumer evidence / replacement / migration risk / KEEP-MIGRATE-DELETE-INVESTIGATE / owner / exit proof. Delete dead code, migrate consumers, retain only documented boundary compatibility with explicit retirement conditions. Historical data/provenance are NOT legacy to delete. Prove no references or regressions after cleanup; do not destroy data to free disk.
3. Reconcile deployment safely and verify API, edge, UI and DB independently. Address storage/archive correctness (#335/#336) before large scans or migrations. Measure resource headroom; bounded batches, indexes, checkpointing, throttling, pause on pressure; keep LIVE available. No new always-on heavyweight service without capacity proof.
4. Build reproducible read-only inventory of all sources, observations, episodes, claims, hypotheses, timeline events, imagery, drift and radio records. Capture unique IDs, date ranges, missing fields, duplicate groups, known gaps, archive/hot-store coverage, manifest and schema/rule version. Freeze a cutoff and reconcile counts with API/DB/archive. Protect internal identifiers and humanitarian data.

## P1 — Full historical replay and evidence remediation

Process every recoverable canonical record, not just the 3,962 visible PLAY records: include original observations, archived AIS, historical radio/OSINT, related claims, imagery and episode revisions where accessible/permitted. Distinguish raw observations from independent evidence, duplicate deliveries and canonical episodes. Preserve original IDs and source data; merges/splits have redirects and audit trail. Never create evidence to fill an unavailable interval.

- Build resumable, idempotent batch replay using frozen manifest, versioned rules, stable keys and checkpoint ledger. Every record must finish as analyzed / duplicate-linked / excluded with reason / inaccessible with reason / pending review; reconcile totals and publish an aggregate progress ledger. Re-run deterministic batches to prove stability.
- For each episode: reconstruct timeline, source lineage, identity, geometry uncertainty, competing claims, coverage context, supporting and opposing evidence, alternative explanations, missing information, investigation/review state, publication eligibility, and method version. Store updates as revisions. Historical validation uses event-time evidence and explicitly labels later corroboration; avoid look-ahead bias.
- Review all 32 corroborated, 21 review-ready and 3 published records (deduplicate overlap), then prioritize unresolved humanitarian review and high-quality anomalous records. Review original sources and disconfirming evidence; distinguish unavailable from false. Expand to the remaining corpus, with automated triage and bounded human-review queues; unresolved is a valid outcome. Do not promise every case can be corroborated.
- AIS gaps: classify reception outage, weak/unknown coverage, vessel-specific missing observations, reappearance observed/unvalidated, reappearance validated, unresolved/outcome unknown; separate observation interval from hypothesis and publication. Implement independently reviewable source/identity attestation bound to exact track and observation, with tests against delayed/duplicate fixes and conflicts. Same MMSI or speed plausibility alone is not authentication. No fabricated gap track; retain observed endpoints and uncertainty; no time-only closure.
- Humanitarian: reconcile taxonomy, link later public updates where lawful, preserve disagreement and unknown outcomes, enforce current drift ownership and privacy. Do not infer fatalities/rescue from silence; never publish sensitive operational locations or private identifiers.
- Satellite: audit every flag for actual scene/artifact, acquisition time, georeferencing, quality, association confidence and provenance; distinguish unavailable, unusable, non-detection, contextual and later corroboration. Validate attribution independently. Respect licensing. No real-time sensitive targeting or tracking enrichment.
- Sanctions: use dated official designation grounds, stable identity and jurisdiction; differentiate listing, local observation and conduct; no association or non-observation proves evasion. For maritime security use retrospective public documentation, independent sources and redaction; avoid tactical operational detail and sensitive live positions.
- Radio: distinguish one transmission from multiple receivers; measure valid messages, independent lineage, continuity, duplicates and correlation false matches. Fix degradation before expanding receivers.
- Calibrate on labelled real/redacted fixtures with negative controls, unknown outcomes, stratified sampling by region/time/class/coverage, precision/recall, inter-reviewer agreement and error intervals. Reuse #440. Do not treat unlabelled cases as negatives.

## P2 — LIVE: evidence-first operational intelligence

LIVE is a current observation surface, not the permanent investigation store. Add a bounded follow-up/review queue using canonical episodes: detected -> contextualized -> competing hypotheses -> independent evidence -> counterevidence -> reviewed. Track freshness, source degradation, suppression reasons, queue age and incident transitions. Display stale vs unavailable vs zero distinctly. Audit the one-feature discrepancy before changing filters. Improve source stability, reconnection and evidence lineage. Keep publication gates fail-closed, privacy first; do not expose live sensitive identifiers/positions or investigative tactics. AI may extract, translate, summarize, propose and rank for review, never certify identity, causation, intent or legal responsibility.

## P3 — PLAY: analytical historical workspace (not a data dump)

Reuse the canonical dossier/timeline endpoint and episode IDs. Separate overview, thematic analysis, episode drill-down, evidence and review state. Use distinct lifecycle, evidence strength, review and publication dimensions. Make counts and filters consistent (domain, time, category, provenance, status, corroboration, coverage, satellite validity). Support aggregate comparisons, saved thematic views, readable summaries linked to evidence, uncertainty, counterevidence and reproducible exports. Show cluster counts, denominators, overlap, time series, coverage-aware geographic aggregates, unknowns and data availability. No misleading route interpolation or heatmaps implying exact sensitive locations.

Performance: profile baseline with realistic archive scale; server-side filtered/keyset pagination and indexed aggregates; versioned incremental materialization, bounded payloads and lazy dossier loading; do not download full history to browser by default. Keep map and charts responsive on mobile, accessible, consistent with LIVE; use cancellation, progress, cache freshness and failure states. Proposed release budgets (validate on representative hardware): warmed aggregate p95 <= 500 ms; filtered page p95 <= 1 s; meaningful first view <= 3 s on agreed mobile/network fixture; no regression in LIVE freshness during backfill. Document baseline, load-test size, p50/p95/p99 and failures; adjust only with documented evidence and review. Keep query totals consistent with pinned snapshot.

## P4 — Research clusters, metrics and reporting

Use versioned many-to-many membership referencing canonical episodes and frozen snapshots, not a parallel incident store. Define inclusion/exclusion, evidence threshold, denominator, source limitations, publication policy and uncertainty for each cluster:
1. AIS Gaps & Maritime Invisibility.
2. Shadow Fleet & Sanctions Monitoring (official designations vs observed context).
3. Position Integrity & Spoofing candidates.
4. Maritime Encounters & Trade Networks (documented historical relations, no intent inference).
5. Humanitarian Maritime Observatory.
6. Radio & Maritime Safety.
7. Critical Maritime Infrastructure (aggregate context only, no sensitive operational detail).
8. Maritime Security & Incident Verification (retrospective public evidence).
9. Satellite Intelligence & Observation Gaps.

Quantitative: independent lineages, completeness, provenance, corroboration rate by eligible cohort, source coverage and freshness, observed gap duration and censoring, recurrence normalized by adequately observed vessel-hours, resolution/outcome rates, time to corroboration, reviewed precision/recall and uncertainty, counterevidence coverage, duplicate rate, publication yield. Report missing denominators and coverage breaks; compare like-for-like, not counts alone. Separate evidence confidence, data quality, anomaly significance, review priority, publication readiness; no single risk score. Any proposed weights are experimental and must be calibrated, hard privacy/provenance gates override them.

Qualitative: precise claim; supporting/contradicting evidence; alternatives; unknowns; source lineage; assessment; reviewer decision and revision. Publish negative/null findings and corrections. Avoid sensational labels, assumptions of intent and inflated counts.

Implement research snapshots, membership, metric definitions, review decisions and report versions using existing canonical stores. Evaluate Parquet/R2/DuckDB for bounded historical aggregates only after verified retrieval and resource measurements; no second truth store. Public Research Library: reproducible web/PDF/data/methodology, immutable cutoff and revisions, permitted anonymized exports, accessibility. First reports: The Geography of Maritime Invisibility; Shadow Fleets and Maritime Opacity; The Unresolved Mediterranean. Then position integrity, radio and satellite methods. Weekly briefs, monthly thematic reports, case studies only when supported; annual synthesis. Every report includes question, sample, methodology, denominators, findings, alternatives, limitations, citations, reproducible query/version and review gate.

## P5 — Evidence-backed maturity gates (target 5/5 for every category)

Baseline scores below are qualitative starting estimates, NOT measured certification. Score 1 initial; 2 partial; 3 implemented; 4 operational with measured gaps; 5 validated against explicit gate. No averaging away weak areas. For 5/5 require reproducible evidence, regression tests, documented limitations, independent reviewer sign-off where appropriate, production verification and no unresolved critical blocker in that category. External/source constraints may make a gate unattainable; report honestly, never game counts.

| Category | Initial | 5/5 exit gate |
| --- | --- | --- |
| Collection | 4 | All configured source families have measured freshness/coverage, provenance, deduplication, health alerts, lawful collection and recovery tests; missing sources explicitly tracked. |
| Architecture/data models | 4 | One canonical path per concept; legacy inventory resolved or bounded exception; schema migration/replay tested, stable IDs and reconciled taxonomy/counts. |
| Geospatial visualization | 4 | LIVE/PLAY contract parity, validated geometry/uncertainty, observed vs inferred distinction, privacy and mobile/accessibility/render regression tests pass. |
| Infrastructure reliability | 3 | Verified archive restore, safe retention, monitored disk and queues, deployment reconciliation, tested recovery, representative load and freshness SLOs met. |
| Automated investigation | 3 | All recoverable historical records accounted for by manifest and replay ledger; incremental follow-up/review queues, deterministic replay, alternatives and audit trail; no auto-certification. |
| Independent corroboration | 2 | All published claims pass lineage/provenance checks; reviewed corpus and calibrated match rules; unsupported/unknown cases remain explicitly labelled. No arbitrary target for corroboration percentage. |
| Scientific validation | 2 | Stratified labelled benchmark, controls, error metrics and confidence intervals, reproducibility, independent review, documented bias and coverage limits; failure cases retained. |
| Quantitative analysis | 2 | Nine clusters with reproducible versioned metrics, denominator/coverage/censoring handling, reconciled snapshot totals and historical backfill completion ledger. |
| Scientific reporting | 1 | Three initial reviewed reports with evidence, reproducible snapshot/query, limitations, privacy checks, web/PDF and permitted exports; correction/version workflow tested. |

## Execution handoff and completion

At the start and end of every work cycle, update a dated status artifact in the repository (aggregate/redacted only) with deployed revision, packet, exact command/test evidence, old/new metrics, replay totals, remaining work, blocker, rollback and next packet. Keep issue #431 aligned; link each PR. Use a single canonical status location, discover existing status artifact before creating one. Update the maturity matrix after measured progress only.

Order: P0 baseline + legacy cleanup in safe slices -> P1 retrospective replay and validation -> P2/P3 operational improvements (parallel only when dependencies clear) -> P4 clusters and reports -> P5 independent verification. Do not delay safe baseline/fix work while waiting for external data. No broad destructive cleanups, no unrelated deployments, no publication without review. Continue through all recoverable history, not just a showcase cohort. If blocked, state what was attempted, why, and the smallest safe next action. Preserve LIVE availability throughout.

Definition of done: every record accounted for; PLAY useful for investigation and comparative research; reports traceable to evidence; all nine gates independently evidenced at 5/5 or explicitly blocked, not self-awarded.
