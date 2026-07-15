# Seacommons — Research, Product and Technical Audit

Date: 2026-07-15  
Scope: repository `suezcanalxyz/seacommons`, product positioning, research readiness, and transition to `seacommons.org`.

## Executive assessment

Seacommons has the raw material for a strong practice-based PhD or research fellowship: a socially relevant problem, a working software artefact, heterogeneous maritime data, trajectory modelling, edge sensing, and a forensic provenance layer. Its strongest defensible identity is not a generic maritime intelligence dashboard. It is an open, research-grade observatory for producing accountable evidence about distress, mobility, risk, and response at sea.

The current repository is a credible pilot, but not yet a research instrument or production system. The main gap is epistemic: the interface presents scores, forecasts, classifications, and forensic claims with more certainty than the documented methods and validation support. The second gap is product architecture: public research communication, datasets, methods, operational tooling, and experimental sensor work are combined in one application and one narrative.

Recommended strategic move: make `seacommons.org` the independent research institution and knowledge commons; keep the operational console as a clearly labelled, access-controlled research demonstrator at `console.seacommons.org`; publish methods, data provenance, limitations, experiments, and releases as first-class outputs.

## Scorecard

| Dimension | Current | Target (12–18 months) | Main evidence/gap |
|---|---:|---:|---|
| Problem relevance | 8/10 | 9/10 | High-stakes Mediterranean SAR and maritime accountability |
| Originality | 6/10 | 8/10 | Promising combination, but contribution is not yet isolated against prior work |
| Research question | 2/10 | 8/10 | No explicit hypothesis, unit of analysis, or falsifiable claims |
| Methodological rigour | 3/10 | 8/10 | Heuristic weights and simplified survival model lack calibration/validation |
| Data governance | 2/10 | 8/10 | No data management plan, retention model, lawful-basis analysis, or sensitivity tiers |
| Reproducibility | 4/10 | 8/10 | Containers exist; dependency/version, test, fixture, and experiment practices remain incomplete |
| Software architecture | 5/10 | 8/10 | Useful modular backend; frontend monolith and deployment/documentation drift |
| Security/readiness | 2/10 | 8/10 | Mutating endpoints and WebSockets have no implemented authentication |
| UX/accessibility | 5/10 | 8/10 | Functional map-first console; no documented user research or accessibility audit |
| Open-science readiness | 2/10 | 9/10 | AGPL is stated, but no root licence file, citation metadata, releases, DOI, or governance |
| Impact pathway | 4/10 | 8/10 | Plausible users exist, but partnerships, adoption measures, and theory of change are absent |
| Overall readiness | **4/10** | **8/10** | Strong prototype; pre-validation research infrastructure |

## What exists today

- FastAPI backend with alert ingestion, drift simulations, weather/ocean integrations, AIS/vessel state, OSINT/intelligence ingestion, probability scoring, anomaly modules, and signed forensic packets.
- React/Vite/MapLibre operational console with a map-first interface and mobile-specific behaviour.
- Docker and pilot deployment assets, edge-node scripts, sensor modules, and operational notes.
- Approximately 12.3k lines of Python and 3k lines of JavaScript/JSX across 117 source files.
- A small smoke suite containing four backend tests.
- A production frontend that type-checks and builds successfully.

This breadth is an asset for exploration and a liability for evaluation: reviewers cannot yet tell which part is the scientific contribution, which is validated infrastructure, which is experimental, and which is only a future integration.

## Critical findings

### 1. Claims exceed evidence

The documentation says every event is suitable as verifiable evidence for international courts. Cryptographic integrity can show that a packet has not changed and that a key signed it; it does not establish truth, chain of custody, lawful acquisition, model validity, identity of the signer, or admissibility. Replace legal-certainty language with a scoped claim: the system provides tamper-evident provenance records whose evidentiary value depends on documented custody, identity, collection, and validation procedures.

The survival probability module cites broad sources but implements an undocumented simplification, interpolated lookup values, heuristic multipliers, and arbitrary composite weights. This must be labelled experimental and must not drive real rescue prioritisation before calibration, uncertainty analysis, domain-expert review, and prospective validation.

### 2. No explicit scientific object

The repository contains multiple possible theses: drift accuracy, multi-source event verification, humanitarian OSINT, distributed sensing, forensic provenance, or decision support. A PhD cannot treat all of them as equal primary contributions. Select one primary object and treat the rest as infrastructure or case studies.

Recommended primary object:

> Accountable data fusion for maritime distress: how can heterogeneous, incomplete, and politically contested signals be transformed into calibrated, traceable, and operationally useful evidence without concealing uncertainty?

### 3. Authentication and trust boundaries are missing

`SUEZCANAL_AUTH` is documented but not wired into the API. Mutating routes, exports, operational records, intelligence injection, image extraction, and WebSockets are not protected by a common identity/authorisation layer. In-memory rate limiting does not work reliably across replicas. Before public launch, define roles, isolate public read APIs, protect operator functions, validate inbound webhook signatures, move rate limiting to shared infrastructure, and add immutable audit logs.

### 4. Architecture documentation is stale

The architecture page describes Next.js, Celery, PostgreSQL/PostGIS, and a WebSocket flow, while the current frontend is React/Vite and significant work runs in process/background threads with a pilot SQLite mode. Documentation must distinguish:

- current deployed architecture;
- validated optional integrations;
- experimental modules;
- target architecture.

An academic reviewer will interpret an inaccurate diagram as weak research hygiene.

### 5. Reproducibility is partial

Strengths include Docker assets, a lockfile for the frontend, environment examples, a runbook, and smoke tests. Gaps include very limited test coverage; no experiment manifests or fixed datasets; no random seed policy; no benchmark baselines; no CI visible in the repository; no data/version lineage; broad Python dependency ranges; and a local test path that fails before collection when development dependencies are absent.

Create one canonical command that provisions and tests the complete research environment. Every published result should record code commit, container digest, dataset snapshot/DOI, model parameters, random seeds, spatial/temporal extent, exclusions, and generated outputs.

### 6. Product scope is too broad

SAR, ballistic/threat awareness, social media intelligence, vessel tracking, physical sensors, forensic evidence, TimeZero integration, and probability scoring currently share the same product surface. This creates ethical, security, procurement, and reviewer ambiguity. Separate the humanitarian research programme from dual-use experiments. A dedicated ethics and dual-use review should govern any military/threat module.

### 7. Frontend needs decomposition

The main React entry is roughly two thousand lines and mixes network access, map lifecycle, domain transformation, operational state, layout, and interaction logic. The production build succeeds, but MapLibre is emitted as a chunk above 1 MB before gzip. Split by route/mode and extract API, map sources/layers, domain models, and workflows. Add component/unit tests, end-to-end tests for critical alert flows, error telemetry, accessibility checks, and performance budgets.

### 8. Open-source and institutional files are incomplete

The README states AGPL-3.0, but the repository lacks a root `LICENSE`. It also lacks `CITATION.cff`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, governance/maintainer rules, a changelog, and a formal data licence. Software, documentation, derived datasets, and sensitive/raw data need separate, explicit licences.

## Proposed PhD framing

### Working title

**Accountable Maritime Data Commons: Calibrated Multi-source Evidence for Distress Detection and Search-and-Rescue Decision Support**

### Core research question

How can heterogeneous maritime distress signals be fused into timely decision support while preserving uncertainty, provenance, contestability, and safeguards for vulnerable people?

### Sub-questions

1. Which combinations of AIS, official incident feeds, environmental data, NGO reports, and public-source observations improve detection lead time and precision over single-source baselines?
2. How should uncertainty propagate from source reliability, geolocation, environmental forcing, and trajectory ensembles into operator-facing outputs?
3. Which provenance representation makes an analytical result independently reproducible and meaningfully contestable?
4. How do operators and civil-society investigators interpret uncertainty visualisations, and which designs reduce overconfidence without delaying action?
5. Under what governance model can sensitive humanitarian data be shared as a commons without increasing surveillance or harm?

### Candidate contribution

The contribution should be a method plus evaluated artefact, not merely the platform:

- a calibrated evidence-fusion model with explicit uncertainty;
- a provenance schema connecting observations, transformations, parameters, models, and outputs;
- an interaction model for communicating contested uncertainty;
- an evaluated open reference implementation and benchmark protocol;
- governance patterns for a humanitarian maritime data commons.

### Falsifiable hypotheses

- H1: multi-source fusion reduces median verified-event detection latency relative to official-feed and AIS-only baselines without unacceptable loss of precision.
- H2: ensemble drift using time-aligned operational forcing improves containment probability against historical endpoints compared with constant-forcing and Gaussian baselines.
- H3: provenance-plus-uncertainty views improve calibrated operator confidence and error detection compared with single-score dashboards.
- H4: tiered access and data minimisation preserve research utility while materially reducing re-identification and operational-security risk.

### Evaluation design

- Retrospective, time-split benchmark using documented historical incidents; no random leakage across the same incident or route.
- Baselines: single-source alerting, rules-only fusion, constant-forcing drift, and established drift configuration.
- Metrics: precision/recall and time-to-detection; Brier score and calibration error; geodesic endpoint error; search-area containment at 6/12/24 hours; provenance completeness; system latency/availability; and human factors measures.
- Ablations: remove each source, provenance feature, environmental reader, and confidence component.
- Robustness: missing data, delayed reports, adversarial/duplicated posts, location error, API outage, and seasonal/geographic shift.
- Qualitative work: semi-structured interviews and scenario-based studies with SAR practitioners, NGOs, maritime lawyers, and data stewards.
- Ethics: data-protection impact assessment, threat modelling, trauma-aware research, dual-use assessment, and an incident/withdrawal protocol.

## Research work packages

### WP1 — Scoping, prior art, and stakeholder governance

Systematic/scoping review; stakeholder map; theory of change; ethics and dual-use register; advisory group. Output: research protocol and preregistered questions.

### WP2 — Data model and governed corpus

Canonical observation/event/entity schema; source registry; provenance graph; sensitivity classification; data management plan; labelled benchmark with annotation guidelines and inter-rater agreement. Output: versioned, citable dataset or controlled-access data package.

### WP3 — Calibrated fusion and drift uncertainty

Baselines, fusion model, environmental forcing, ensemble trajectory evaluation, calibration, missingness and ablation studies. Output: methods paper and reproducible experiment package.

### WP4 — Human-centred decision support

Participatory design, uncertainty visualisation experiments, accessibility and multilingual workflows, operator studies. Output: HCI/design research paper and validated interface patterns.

### WP5 — Provenance, accountability, and deployment

W3C-aligned provenance mapping, identity/key governance, chain-of-custody procedure, security assessment, field pilot, and independent replication. Output: reference implementation, operational protocol, and impact evaluation.

## `seacommons.org` information architecture

The domain should signal an institution and a research commons, not open directly into a high-density console.

| Host/path | Purpose | Audience | Access |
|---|---|---|---|
| `seacommons.org` | Mission, research questions, team, partners, ethics, latest outputs | Public/funders | Public |
| `seacommons.org/research` | Programmes, methods, work packages, field sites | Academic/practitioner | Public |
| `seacommons.org/publications` | Papers, preprints, posters, software/data citations | Academic | Public |
| `seacommons.org/data` | Dataset catalogue, datasheets, licences, access tiers | Researchers | Mixed |
| `seacommons.org/methods` | Models, validation, limitations, provenance, changelog | Researchers/operators | Public |
| `seacommons.org/observatory` | Aggregated public indicators and stories, never sensitive live operations | Public/media | Public |
| `console.seacommons.org` | Operational/research demonstrator | Approved users | Authenticated |
| `api.seacommons.org` | Versioned API with public and protected surfaces | Developers/partners | Tiered |
| `docs.seacommons.org` | Technical and API documentation | Contributors | Public |
| `status.seacommons.org` | Availability and incidents | All users | Public |

Recommended identity line:

> Seacommons is an open research infrastructure for accountable maritime evidence, uncertainty-aware search-and-rescue analysis, and the governance of shared ocean data.

Avoid presenting live personal/vessel locations or unverified distress reports on the public observatory. Publish delayed, aggregated, redacted, or synthetic views according to an explicit release policy.

## Target system boundaries

1. **Public research site:** static, accessible, indexable, multilingual; no operational secrets.
2. **Public observatory:** curated/aggregated read models with methodology and timestamps.
3. **Protected operations:** authenticated case management, sensitive positions, manual ingestion, exports, and partner integrations.
4. **Research pipeline:** immutable raw zone, governed transformations, versioned feature/benchmark datasets, experiment tracking, and publishable artefacts.
5. **Edge programme:** separately versioned hardware/firmware, calibration records, device identity, signed telemetry, and field maintenance protocol.

## Technical priorities

### P0 — Before exposing `seacommons.org`

- Remove or qualify unsupported medical, operational, and legal claims.
- Implement authentication/authorisation and deny-by-default protection for all mutations and WebSockets.
- Validate Twilio/Telegram/generic webhook authenticity and add request/body limits.
- Replace fixed HTTP IP rewrites with TLS service discovery on `api.seacommons.org`.
- Define public/private data fields, retention periods, deletion/withdrawal procedures, backups, and incident response.
- Add secrets management, key rotation, signer identity policy, and environment validation at startup.
- Add root licence/security files and a visible “research prototype—not for operational reliance” status until validation gates are met.

### P1 — Research foundation (0–3 months)

- Freeze the primary research question and write a 5–10 page concept note.
- Build the prior-art matrix and source bibliography with persistent identifiers.
- Create the canonical event/provenance schema and data management plan.
- Establish CI for lint, unit/integration tests, container build, dependency scanning, and OpenAPI compatibility.
- Pin runtime dependencies; create deterministic fixtures and a one-command research environment.
- Split experimental threat modules from the humanitarian core.
- Align README, architecture, deployment, metadata, and branding with Seacommons.

### P2 — Validation (3–9 months)

- Assemble an ethically governed historical benchmark and annotation handbook.
- Replace uncalibrated composite scores with baseline models and calibrated probabilities.
- Evaluate CMEMS/atmospheric forcing and trajectory ensembles against historical cases.
- Add full provenance, uncertainty budgets, experiment tracking, and model/data cards.
- Conduct expert review of survival/triage assumptions; disable those outputs operationally unless validated.
- Run formative user research and accessibility testing with target users.

### P3 — Fellowship/PhD-ready programme (9–18 months)

- Preregister the evaluation, publish benchmark protocol and software release with DOI.
- Complete retrospective study, ablations, robustness analysis, and independent replication.
- Conduct a limited partner pilot under a signed governance and safety protocol.
- Publish methods and HCI/governance results; report negative findings and limitations.
- Establish an advisory board and transparent project/data governance.

## Funding narrative

A fundable proposal should connect five elements in one causal chain:

1. **Problem:** maritime distress evidence is fragmented, delayed, uncertain, and institutionally contested.
2. **Knowledge gap:** existing systems optimise detection or operations but rarely make uncertainty, provenance, and contestability first-class and jointly evaluated.
3. **Method:** governed multi-source corpus, calibrated fusion, ensemble drift, provenance graph, and participatory interface evaluation.
4. **Outputs:** publications, benchmark/data package, open software, governance toolkit, trained researcher, and partner pilot.
5. **Impact:** faster and more accountable analysis, auditable claims, improved cross-organisational learning, and safer data sharing.

Suitable funding families include doctoral scholarships in information studies/HCI/GIScience/ocean engineering; Marie Skłodowska-Curie-style doctoral or postdoctoral actions; European Research Council or national investigator grants through a university host; Horizon Europe clusters on civil security, digital governance, climate/ocean, and research infrastructures; Copernicus/ocean innovation calls; and foundation programmes in human rights, migration, open technology, or investigative evidence. Each live call must be checked for current eligibility, technology-readiness expectations, and host-country rules.

## Required proposal artefacts

- Two-page concept note and one-page theory of change.
- Academic CV, host/supervisor fit statement, and skills-gap/training plan.
- Prior-art/contribution matrix rather than a generic literature list.
- Data management plan, ethics self-assessment, DPIA, and dual-use risk register.
- Work-package/Gantt plan with milestones, dependencies, risks, and go/no-go gates.
- Partner letters describing access, role, and in-kind contribution without overstating commitment.
- Preliminary-results package: reproducible baseline, one historical case study, and limitations.
- Sustainability plan covering maintenance, governance, hosting, and post-grant ownership.

## Twelve-week execution plan

### Weeks 1–2: identity and safeguards

Freeze the scientific scope; separate public/operational/experimental claims; add legal, ethical, security, and prototype notices; define domain and access boundaries.

### Weeks 3–4: research protocol

Write research questions, hypotheses, inclusion criteria, metrics, baselines, and data-management/ethics drafts. Start the prior-art matrix and stakeholder advisory group.

### Weeks 5–7: reproducible baseline

Create deterministic datasets/fixtures, CI, pinned environments, experiment manifests, provenance records, and baseline evaluations. Correct architecture documentation.

### Weeks 8–9: domain launch

Launch the institutional public site with research, methods, team, governance, publications, data catalogue, and transparent status pages. Keep the console protected and clearly labelled.

### Weeks 10–12: application package

Produce a concept note, supervisor/host shortlist, preliminary-results figure, work packages, budget assumptions, partner brief, risk register, and tailored application calendar.

## Success gates

Seacommons should call itself research-grade only when:

- every analytical output exposes source, timestamp, version, uncertainty, and limitations;
- benchmark data and evaluation protocol are independently reviewable;
- key probability outputs are calibrated and externally reviewed;
- a clean environment can reproduce a published result from one documented command;
- sensitive operations are isolated and protected by tested access controls;
- software/data licences, governance, ethics, and incident procedures are public;
- at least one external partner and one independent researcher have evaluated or replicated the method.

## Immediate decision

The next high-leverage decision is disciplinary positioning. Recommended home: **HCI/information studies or GIScience with co-supervision in ocean/SAR modelling and human-rights/data governance**. This matches the actual originality—accountable translation of contested data into decisions—better than presenting the project solely as ocean engineering or as a software startup.
