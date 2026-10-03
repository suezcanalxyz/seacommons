// Shared public proposal. These are prospective milestones, never live telemetry.
export const PILOT_PHASES = [
  { period: 'Months 1–2', title: 'Establish the baseline', work: 'Audit deployment health and source coverage. Agree a bounded geography and review protocol with pilot participants.', output: 'Coverage report, baseline dataset and agreed evaluation protocol.' },
  { period: 'Months 3–4', title: 'Validate case reconstruction', work: 'Review a documented sample of humanitarian and maritime cases. Record unsupported associations, corrections and analyst effort.', output: 'Reviewed case sample with source lineage, uncertainty and correction log.' },
  { period: 'Months 5–6', title: 'Evaluate and hand over', work: 'Compare results with the baseline. Document operating costs, maintenance responsibilities and requirements for continued use.', output: 'Evaluation report, operating runbook and costed continuation proposal.' },
];

export const FUNDING_WORK = [
  { title: 'Reliable infrastructure', body: 'Deployment recovery, monitoring, backups and source availability.', evidence: 'Health checks, recovery exercise and coverage report.' },
  { title: 'Evidence validation', body: 'Source integration, independent lineage checks and reviewed case reconstruction.', evidence: 'Review protocol, case sample and correction log.' },
  { title: 'Partner use and maintenance', body: 'Research participation, onboarding, documentation and ongoing engineering.', evidence: 'Participant feedback, operating runbook and cost report.' },
];

export const PILOT_METRICS = [
  { title: 'Source availability', definition: 'Received updates against the expected schedule, by source and geography. Report gaps and denominators.' },
  { title: 'Evidence traceability', definition: 'Share of reviewed cases with inspectable source lineage, location precision and transformation history.' },
  { title: 'Review quality', definition: 'Unsupported associations and corrections in a documented sample, distinguishing independent corroboration from repeated reports.' },
  { title: 'Research usefulness', definition: 'Time to assemble a case record and participant assessment against an agreed baseline workflow.' },
];
