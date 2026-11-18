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

const geographicClues = {
  '57dce9fa': [
    { name: 'El Kala, Algeria', role: 'departure', coordinates: [8.4431, 36.8961],
      reference: 'https://mapcarta.com/El_Kala' },
    { name: 'Sardinia, Italy', role: 'destination', coordinates: [9, 40],
      reference: 'https://www.geonames.org/2523228/sardegna.html' },
  ],
};

const noClues = [];

export function archiveGeographicClues(record) {
  return geographicClues[record?.incident_id] || noClues;
}

export function geographicClueFeatures(clues) {
  return clues.map(({ name, role, coordinates }) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates },
    properties: {
      kind: `clue_${role}`,
      label: role === 'departure' ? 'Reported departure' : 'Reported destination',
      place: name,
    },
  }));
}
