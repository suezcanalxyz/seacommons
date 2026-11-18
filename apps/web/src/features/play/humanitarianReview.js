// Review decisions apply to the archive display. The source reports are retained.
const nonIncidentReports = new Set([
  'aa84c4c6', // Criminal sentencing unrelated to an active emergency.
  'df895782', // Court verdict, not a distinct distress incident.
  'a8154c20', // Policy advocacy.
]);

const destinationOnly = new Set(['57dce9fa']);

export function reviewedArchiveCase(record) {
  if ((record.main_category || record.domain) !== 'humanitarian') return record;
  if (nonIncidentReports.has(record.incident_id)) return null;
  if (!record.source && record.title === 'Humanitarian incident') return null;
  if (!destinationOnly.has(record.incident_id)) return record;
  return {
    ...record,
    geometry: null,
    search_area: null,
    has_satellite: false,
    evidence_counts: { ...record.evidence_counts, satellite: 0, drift: 0 },
    location_summary: 'Sardinia was the reported destination. The location of the missing boat is unknown.',
    suppress_inferred_map_evidence: true,
  };
}
