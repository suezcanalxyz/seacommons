export const seaCommonsProject = {
  id: 'seacommons',
  name: 'SeaCommons',
  type: 'workspace',
  status: 'production + active development',
  summary: 'Maritime OSINT infrastructure that turns source observations into reviewable incidents, episodes, hypotheses and privacy-aware public outputs.',
  phase: 'Evidence fusion + operational hardening',
  tags: ['maritime OSINT', 'evidence', 'investigation'],
  capabilities: ['Humanitarian OSINT', 'Maritime intelligence', 'Live', 'Play', 'Drift', 'Satellite', 'Radio'],
  workstreams: [
    { id: 'cross-modal', name: 'Cross-modal evidence closure', state: 'active', note: 'Make independent satellite, radio, humanitarian and AIS evidence update canonical episodes without inflating independence.' },
    { id: 'satellite-queue', name: 'Satellite investigation queue', state: 'active', note: 'Attach coverage and candidate scenes to dossiers as investigation context before any claim is promoted to evidence.' },
    { id: 'humanitarian-correlation', name: 'Humanitarian cross-source correlation', state: 'next', note: 'Unify follow-up reports, uncertainty areas, temporal windows and response geometry around canonical incidents.' },
    { id: 'ais-baseline', name: 'AIS historical baseline + counter-evidence', state: 'next', note: 'Use historical behaviour and explicit counter-evidence to reduce false positives before creating stronger hypotheses.' },
    { id: 'radio-decode', name: 'Structured radio decode', state: 'stabilise', note: 'Prioritise repeatable decoded DSC/NAVTEX output before expanding receiver coverage.' },
    { id: 'production', name: 'Production hygiene + SLO', state: 'ongoing', note: 'Keep releases reproducible, observable and fail-closed across API, workers, edge and public surfaces.' },
  ],
  documents: [
    { id: 'project-overview', title: 'Project overview', group: 'project', kind: 'brief', visibility: 'partner', source: 'apps/web/src/docs/content/SEACOMMONS.md', updated: '06 Oct 2026' },
    { id: 'architecture', title: 'System architecture', group: 'technology', kind: 'architecture', visibility: 'partner', source: 'docs/ARCHITECTURE.md', updated: '22 Sep 2026' },
    { id: 'current-work', title: 'Current work', group: 'development', kind: 'status', visibility: 'partner', source: 'docs/current_work.md', updated: '06 Oct 2026' },
    { id: 'roadmap', title: 'Engineering roadmap', group: 'development', kind: 'roadmap', visibility: 'partner', source: 'docs/roadmap.md', updated: '06 Oct 2026' },
    { id: 'security', title: 'Security model', group: 'technology', kind: 'policy', visibility: 'restricted', source: 'docs/SECURITY_MODEL.md', updated: '22 Sep 2026' },
    { id: 'public-docs', title: 'Public documentation contract', group: 'project', kind: 'policy', visibility: 'partner', source: 'docs/PUBLIC_DOCUMENTATION.md', updated: '22 Sep 2026' },
  ],
};

export const roadmap = {
  now: [
    { project: 'SeaCommons', title: 'Cross-modal evidence closure', state: 'active', detail: 'Canonical episodes should absorb independent evidence without lineage inflation.' },
    { project: 'SeaCommons', title: 'Satellite investigation queue', state: 'active', detail: 'Coverage and scene candidates become structured investigation context.' },
    { project: 'SeaCommons', title: 'Production hygiene + SLO', state: 'ongoing', detail: 'Reproducible releases, service health and fail-closed behaviour.' },
  ],
  next: [
    { project: 'SeaCommons', title: 'Humanitarian ↔ AIS correlation', state: 'planned', detail: 'Canonical cross-source incident threading with uncertainty and response geometry.' },
    { project: 'SeaCommons', title: 'AIS historical baseline + counter-evidence', state: 'planned', detail: 'Historical context before stronger anomaly hypotheses.' },
    { project: 'SeaCommons', title: 'Structured radio decode', state: 'planned', detail: 'Repeatable decoded DSC/NAVTEX output before any receiver expansion.' },
  ],
  later: [
    { project: 'SeaCommons', title: 'Expanded radio coverage', state: 'later', detail: 'Only after repeatable structured decode is demonstrated.' },
    { project: 'SeaCommons', title: 'Additional investigation surfaces', state: 'later', detail: 'Add project-specific tools only when their evidence and access model is explicit.' },
  ],
};

export const timeline = [
  { date: '07 Oct 2026', project: 'SeaCommons', kind: 'workspace', title: 'Futures scope corrected to SeaCommons only', detail: 'The SeaCommons Futures domain is now a project-specific workspace rather than a catalogue of Suez products or client projects.' },
  { date: '06 Oct 2026', project: 'SeaCommons', kind: 'workspace', title: 'Partner workspace merged', detail: 'Dedicated Futures domain with live operational status, roadmap, project documents, guidebook and access surface.' },
  { date: '06 Oct 2026', project: 'SeaCommons', kind: 'evidence', title: 'Humanitarian corroboration guard tightened', detail: 'AIS-derived rows no longer seed humanitarian source independence.' },
  { date: '05 Oct 2026', project: 'SeaCommons', kind: 'development', title: 'Cross-modal closure prioritised', detail: 'Satellite, radio and humanitarian evidence moved into the active development loop.' },
  { date: '23 Sep 2026', project: 'SeaCommons', kind: 'production', title: 'Extended test baseline established', detail: 'Large backend/web/edge suite retained as the release qualification baseline.' },
  { date: '21 Sep 2026', project: 'SeaCommons', kind: 'product', title: 'Live / Play taxonomy closure', detail: 'Public incident categories constrained to a closed Humanitarian/Maritime vocabulary.' },
];

export const partnerDocuments = seaCommonsProject.documents.map((doc) => ({
  ...doc,
  project: 'SeaCommons',
  projectId: 'seacommons',
}));

export const guidebook = [
  {
    group: 'Start here',
    id: 'futures-access',
    title: 'Futures and access',
    summary: 'How the SeaCommons partner workspace is organised and how access will be scoped.',
    body: [
      'Futures is the private workspace for SeaCommons. It is not a catalogue of Suez products, and it is not the Suez client portal.',
      'A partner can receive access to the SeaCommons workspace, a specific SeaCommons project or subproject, or an individual SeaCommons resource.',
      'Identity may be provided by the shared Suez account layer, but the product context and permissions remain SeaCommons-specific on this domain.',
    ],
  },
  {
    group: 'SeaCommons',
    id: 'project-overview',
    title: 'Project overview',
    summary: 'What SeaCommons is, what is in production and what is still under development.',
    body: [
      'SeaCommons is a maritime OSINT platform with two operational verticals: Humanitarian OSINT and Maritime Intelligence. Both use one evidence model rather than separate truth stores.',
      'The canonical flow is source observation → normalized evidence → correlation → incident or episode → assessment or hypothesis → publication policy → Live, Play, API or analyst surfaces.',
      'Production work prioritises provenance, source independence, explicit contradictions, privacy-aware geometry and replayable automated decisions.',
    ],
  },
  {
    group: 'SeaCommons',
    id: 'evidence-model',
    title: 'Evidence model',
    summary: 'The invariants partners should understand when reading outputs.',
    body: [
      'An observation is not an incident. A derived cue is not a factual finding. Multiple transformations of one source lineage do not create independent corroboration.',
      'Contradictory claims remain part of the record. Missing coordinates remain missing, and approximate geometry carries explicit precision metadata.',
      'Humanitarian privacy is applied before public map convenience. AIS alone cannot confirm rescue or humanitarian resolution.',
    ],
  },
  {
    group: 'SeaCommons',
    id: 'architecture',
    title: 'System architecture',
    summary: 'The deployed SeaCommons surfaces and their ownership boundaries.',
    body: [
      'SeaCommons is a modular monorepo rather than a microservice estate. The operational backend is a FastAPI application with optional workers sharing its database and domain code.',
      'The institutional site and public docs run on the web build; the operational console uses the same frontend package; API/workers own ingestion and persistence; the Cloudflare edge owns the privacy-filtered public Live snapshot.',
      'PostgreSQL is the production system of record. Browser storage and the edge snapshot are never authoritative truth stores.',
    ],
  },
  {
    group: 'SeaCommons',
    id: 'development-roadmap',
    title: 'Development roadmap',
    summary: 'How current SeaCommons engineering priorities are sequenced.',
    body: [
      'Current work is centred on cross-modal evidence closure, satellite investigation context, stronger historical AIS baselines and humanitarian cross-source correlation.',
      'New receiver coverage is intentionally secondary to repeatable radio decoding. New data sources should not be introduced before their provenance, independence and publication implications are explicit.',
      'Each development packet is expected to preserve production behaviour, add replayable tests and maintain the public/private evidence boundary.',
    ],
  },
  {
    group: 'Operations',
    id: 'production',
    title: 'Production and reliability',
    summary: 'What operational quality means for SeaCommons.',
    body: [
      'Production changes are qualified through backend tests, web tests, browser E2E, edge tests, migration checks, static analysis and security scanning.',
      'Critical invariants include idempotent delivery, no stale resurrection of resolved incidents, explicit source freshness and fail-closed public projection.',
      'Futures uses public-safe aggregate contracts unless a future SeaCommons entitlement explicitly authorises an operator-only source.',
    ],
  },
  {
    group: 'Operations',
    id: 'partner-access',
    title: 'Partner access model',
    summary: 'How organisations receive access to SeaCommons without collapsing product boundaries.',
    body: [
      'Identity can be shared through Suez while visual and product context remains SeaCommons.',
      'The access model supports grants at SeaCommons workspace, project, subproject and resource level.',
      'Access to other Suez products is a separate entitlement on its own product surface and is not implied by SeaCommons access.',
    ],
  },
];

export const tools = [
  { id: 'live', name: 'SeaCommons Live', state: 'available', kind: 'public surface', description: 'Operational public map of privacy-filtered current cases and maritime intelligence.', href: 'https://live.seacommons.org' },
  { id: 'play', name: 'SeaCommons Play', state: 'available', kind: 'public surface', description: 'Historical public catalogue and case timelines.', href: 'https://play.seacommons.org' },
  { id: 'docs', name: 'SeaCommons Docs', state: 'available', kind: 'documentation', description: 'Canonical public technical documentation.', href: 'https://seacommons.org/docs' },
  { id: 'api', name: 'API reference', state: 'available', kind: 'developer', description: 'Generated OpenAPI / Swagger reference.', href: 'https://api.seacommons.org/docs' },
];

export const supportAreas = [
  { area: 'Evidence infrastructure', status: 'active development', need: 'Engineering time for cross-modal closure, correlation and investigation tooling.' },
  { area: 'Data coverage', status: 'selective expansion', need: 'Source access, historical datasets and validated coverage partnerships.' },
  { area: 'Operations', status: 'ongoing', need: 'Reliable compute, observability, storage and release qualification.' },
  { area: 'Research', status: 'ongoing', need: 'Method review, case validation and domain-specific partnerships.' },
];

export const accessMatrix = [
  { system: 'SeaCommons', level: 'manage', scope: 'workspace + authorised projects / resources', state: 'bootstrap' },
];
