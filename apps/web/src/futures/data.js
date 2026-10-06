export const proprietaryProjects = [
  {
    id: 'seacommons',
    name: 'SeaCommons',
    type: 'proprietary',
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
  },
  {
    id: 'republic',
    name: 'Republic',
    type: 'proprietary',
    status: 'active',
    summary: 'Cultural and technological operating framework for Suez Canal Republic projects and future shared services.',
    phase: 'Platform architecture',
    tags: ['culture', 'governance', 'infrastructure'],
    capabilities: ['Project registry', 'Shared identity', 'Publishing', 'Partner access'],
    workstreams: [
      { id: 'identity', name: 'Shared identity layer', state: 'active', note: 'One Suez identity with domain-preserving return flows and project-level grants.' },
      { id: 'registry', name: 'Project registry', state: 'next', note: 'Canonical registry for proprietary systems, client work and project resources.' },
      { id: 'access', name: 'Partner access model', state: 'active', note: 'Grant access at system, project, subproject and resource level.' },
    ],
    documents: [
      { id: 'republic-framework', title: 'Republic framework', group: 'project', kind: 'brief', visibility: 'partner', source: 'suezcanal.xyz', updated: '30 Sep 2026' },
    ],
  },
  {
    id: 'map',
    name: 'Map',
    type: 'proprietary',
    status: 'prototype',
    summary: 'Shared spatial interface for proprietary research, project layers and partner-facing geographic tools.',
    phase: 'Prototype',
    tags: ['mapping', 'geospatial', 'interface'],
    capabilities: ['Shared basemap', 'Project layers', 'Partner views'],
    workstreams: [
      { id: 'basemap', name: 'Shared basemap', state: 'active', note: 'Reusable geographic surface for project-specific evidence and context layers.' },
      { id: 'layers', name: 'Project layer model', state: 'next', note: 'Permission-aware layers that can be reused across proprietary systems.' },
    ],
    documents: [
      { id: 'map-note', title: 'Map product note', group: 'project', kind: 'brief', visibility: 'partner', source: 'internal', updated: '02 Oct 2026' },
    ],
  },
  {
    id: 'suez',
    name: 'Suez',
    type: 'proprietary',
    status: 'in development',
    summary: 'Shared operational layer for identity, Futures, partner access, client workflow and future proprietary tools.',
    phase: 'Futures foundation',
    tags: ['operations', 'identity', 'tools'],
    capabilities: ['Futures', 'Identity', 'Rooms', 'Access grants'],
    workstreams: [
      { id: 'futures', name: 'Futures', state: 'active', note: 'Partner and client workspaces with intentionally different information architectures.' },
      { id: 'auth', name: 'Suez identity', state: 'blocked', note: 'Application surfaces are ready; final dedicated Supabase tenant will be connected separately.' },
      { id: 'rooms', name: 'Client rooms', state: 'next', note: 'Simplified commercial workflow for client projects, requests, documents and billing.' },
    ],
    documents: [
      { id: 'futures-architecture', title: 'Futures architecture', group: 'technology', kind: 'architecture', visibility: 'partner', source: 'internal', updated: '06 Oct 2026' },
    ],
  },
];

export const clientProjects = [
  {
    id: 'swimming-cetacea',
    name: 'Swimming Cetacea',
    type: 'client',
    status: 'active',
    summary: 'Commercial workflow covering website infrastructure, SEO expansion, market intelligence and charter development.',
    phase: 'Growth + infrastructure',
    tags: ['web', 'SEO', 'market intelligence'],
    capabilities: ['Website', 'SEO', 'Market intelligence', 'Charter expansion'],
    workstreams: [
      { id: 'website', name: 'Core website', state: 'active', note: 'Production website, booking UX, mobile optimisation and CMS integration.' },
      { id: 'seo', name: 'SEO & Search', state: 'active', note: 'Four-port content architecture and search visibility.' },
      { id: 'market', name: 'Market intelligence', state: 'active', note: 'Competitive and geographic market research.' },
      { id: 'charter', name: 'Charter expansion', state: 'next', note: 'Positioning and service architecture for the yacht/charter branch.' },
    ],
    documents: [
      { id: 'swim-market', title: 'Market intelligence', group: 'research', kind: 'deck', visibility: 'client', source: 'internal', updated: '06 Oct 2026' },
      { id: 'swim-growth', title: 'Growth strategy', group: 'strategy', kind: 'deck', visibility: 'client', source: 'internal', updated: '28 Sep 2026' },
    ],
  },
  {
    id: 'case-rosa',
    name: 'Case Rosa',
    type: 'client',
    status: 'active',
    summary: 'Commercial project workspace for digital positioning and hospitality growth.',
    phase: 'Market positioning',
    tags: ['hospitality', 'market', 'web'],
    capabilities: ['Website', 'Market review', 'Positioning'],
    workstreams: [
      { id: 'benchmark', name: 'Market benchmark', state: 'active', note: 'Comparable offer and positioning review.' },
      { id: 'conversion', name: 'Conversion structure', state: 'next', note: 'Commercial website and inquiry journey.' },
    ],
    documents: [
      { id: 'rosa-market', title: 'Market review', group: 'research', kind: 'deck', visibility: 'client', source: 'internal', updated: '06 Oct 2026' },
    ],
  },
  {
    id: 'insulaphilia',
    name: 'Insulaphilia',
    type: 'client',
    status: 'active',
    summary: 'Commercial operations workspace for projects, team workflows, documentation and digital infrastructure.',
    phase: 'Operations system',
    tags: ['operations', 'culture', 'project management'],
    capabilities: ['Projects', 'Team', 'Documents', 'Operations'],
    workstreams: [
      { id: 'database', name: 'Project database', state: 'active', note: 'Make the project record the canonical place for concept, team, deadlines and linked assets.' },
      { id: 'workflow', name: 'Team workflows', state: 'active', note: 'Assignments, deadlines, invitations and project roles.' },
      { id: 'documents', name: 'Document layer', state: 'next', note: 'Versioned project documents and links to presentations and budgets.' },
    ],
    documents: [
      { id: 'insula-ops', title: 'Operations overview', group: 'operations', kind: 'brief', visibility: 'client', source: 'internal', updated: '01 Oct 2026' },
    ],
  },
];

export const allProjects = [...proprietaryProjects, ...clientProjects];

export const roadmap = {
  now: [
    { project: 'SeaCommons', title: 'Cross-modal evidence closure', state: 'active', detail: 'Canonical episodes should absorb independent evidence without lineage inflation.' },
    { project: 'SeaCommons', title: 'Satellite investigation queue', state: 'active', detail: 'Coverage and scene candidates become structured investigation context.' },
    { project: 'Suez', title: 'Futures partner workspace', state: 'active', detail: 'Operational partner surface, project structure, documents and access model.' },
    { project: 'SeaCommons', title: 'Production hygiene + SLO', state: 'ongoing', detail: 'Reproducible releases, service health and fail-closed behaviour.' },
  ],
  next: [
    { project: 'SeaCommons', title: 'Humanitarian ↔ AIS correlation', state: 'planned', detail: 'Canonical cross-source incident threading with uncertainty and response geometry.' },
    { project: 'SeaCommons', title: 'AIS historical baseline + counter-evidence', state: 'planned', detail: 'Historical context before stronger anomaly hypotheses.' },
    { project: 'Suez', title: 'Granular partner grants', state: 'blocked', detail: 'System/project/resource grants switch from bootstrap admin to Supabase-backed access.' },
    { project: 'Suez', title: 'Client Rooms', state: 'planned', detail: 'Simplified commercial workflow, requests, documents and billing.' },
  ],
  later: [
    { project: 'Map', title: 'Permission-aware project layers', state: 'later', detail: 'One map surface serving different authorised project contexts.' },
    { project: 'Suez', title: 'Partner tool suite', state: 'later', detail: 'Launch proprietary tools from the same identity and entitlement layer.' },
    { project: 'SeaCommons', title: 'Expanded radio coverage', state: 'later', detail: 'Only after repeatable structured decode is demonstrated.' },
  ],
};

export const timeline = [
  { date: '06 Oct 2026', project: 'Futures', kind: 'platform', title: 'Partner workspace merged into SeaCommons', detail: 'Dedicated Futures domain, proprietary/client separation and Suez identity bridge.' },
  { date: '06 Oct 2026', project: 'SeaCommons', kind: 'evidence', title: 'Humanitarian corroboration guard tightened', detail: 'AIS-derived rows no longer seed humanitarian source independence.' },
  { date: '05 Oct 2026', project: 'SeaCommons', kind: 'development', title: 'Cross-modal closure prioritised', detail: 'Satellite, radio and humanitarian evidence moved into the active development loop.' },
  { date: '23 Sep 2026', project: 'SeaCommons', kind: 'production', title: 'Extended test baseline established', detail: 'Large backend/web/edge suite retained as the release qualification baseline.' },
  { date: '21 Sep 2026', project: 'SeaCommons', kind: 'product', title: 'Live / Play taxonomy closure', detail: 'Public incident categories constrained to a closed Humanitarian/Maritime vocabulary.' },
];

export const partnerDocuments = proprietaryProjects
  .flatMap((project) => project.documents.map((doc) => ({ ...doc, project: project.name, projectId: project.id })));

export const guidebook = [
  {
    group: 'Start here',
    id: 'futures-access',
    title: 'Futures and access',
    summary: 'How the partner workspace is organised and how access will be scoped.',
    body: [
      'Futures is a private partner surface. It is not the public SeaCommons documentation and it is not the Suez client portal.',
      'A partner can receive access to a whole proprietary system, a specific project or subproject, or an individual resource. Domain separation remains intact: SeaCommons stays SeaCommons even when identity is provided by Suez.',
      'The current bootstrap configuration grants the administrator full visibility. The final Supabase identity tenant will replace that bootstrap state with stored memberships and access grants.',
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
    summary: 'The deployed surfaces and their ownership boundaries.',
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
    summary: 'How current engineering priorities are sequenced.',
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
      'Futures surfaces use public-safe aggregate contracts unless a future entitlement explicitly authorises an operator-only source.',
    ],
  },
  {
    group: 'Operations',
    id: 'partner-access',
    title: 'Partner access model',
    summary: 'How organisations receive access without collapsing product boundaries.',
    body: [
      'Identity is shared through Suez; visual and product context stays on the domain where the user started.',
      'The access model supports grants at system, project and resource level. This means one organisation may see the SeaCommons roadmap and selected documents while another can also open a proprietary tool.',
      'Client work remains structurally separate. Client-facing workflow is intentionally simpler and commercial; the SeaCommons partner workspace is for project knowledge, development state and proprietary-system access.',
    ],
  },
];

export const tools = [
  { id: 'live', name: 'SeaCommons Live', state: 'available', kind: 'public surface', description: 'Operational public map of privacy-filtered current cases and maritime intelligence.', href: 'https://live.seacommons.org' },
  { id: 'play', name: 'SeaCommons Play', state: 'available', kind: 'public surface', description: 'Historical public catalogue and case timelines.', href: 'https://play.seacommons.org' },
  { id: 'docs', name: 'SeaCommons Docs', state: 'available', kind: 'documentation', description: 'Canonical public technical documentation.', href: 'https://seacommons.org/docs' },
  { id: 'api', name: 'API reference', state: 'available', kind: 'developer', description: 'Generated OpenAPI / Swagger reference.', href: 'https://api.seacommons.org/docs' },
  { id: 'map', name: 'Shared Map', state: 'prototype', kind: 'proprietary', description: 'Future permission-aware spatial surface for project-specific layers.', href: null },
  { id: 'research-query', name: 'Research Query', state: 'planned', kind: 'proprietary', description: 'Future structured query surface across authorised project evidence and documents.', href: null },
];

export const supportAreas = [
  { area: 'Evidence infrastructure', status: 'active development', need: 'Engineering time for cross-modal closure, correlation and investigation tooling.' },
  { area: 'Data coverage', status: 'selective expansion', need: 'Source access, historical datasets and validated coverage partnerships.' },
  { area: 'Operations', status: 'ongoing', need: 'Reliable compute, observability, storage and release qualification.' },
  { area: 'Research', status: 'ongoing', need: 'Method review, case validation and domain-specific partnerships.' },
];

export const accessMatrix = [
  { system: 'SeaCommons', level: 'manage', scope: 'all projects + resources', state: 'bootstrap' },
  { system: 'Republic', level: 'manage', scope: 'all projects + resources', state: 'bootstrap' },
  { system: 'Map', level: 'manage', scope: 'prototype + roadmap', state: 'bootstrap' },
  { system: 'Suez', level: 'manage', scope: 'Futures architecture', state: 'bootstrap' },
  { system: 'Client projects', level: 'manage', scope: 'commercial overview only', state: 'bootstrap' },
];
