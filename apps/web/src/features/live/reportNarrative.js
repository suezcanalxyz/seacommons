/** Human-readable, evidence-first interpretation. Never stringify raw detector parameters. */
const CODE_LABELS = {
  DENSE_REPORTING_HISTORY: 'The vessel normally reports AIS regularly.',
  NEIGHBOUR_TRAFFIC_CONTINUED: 'Nearby vessels continued transmitting AIS.',
  TRACK_CORRIDOR_COVERAGE_PRESENT: 'AIS reception along the corridor was observed.',
  NO_MATERIAL_JAMMING_CONTEXT: 'No material GNSS jamming context was reported.',
  MANY_EXPECTED_REPORTS_MISSING: 'Many expected AIS messages were not received.',
  PROLONGED_OFFSHORE_GAP: 'A prolonged AIS gap was detected offshore.',
};

export function humanizeDetectorText(value) {
  if (value == null) return '';
  const raw = typeof value === 'string' ? value : (typeof value === 'object' ? '' : String(value));
  if (!raw) return '';
  return raw.replace(/\s*The observed silence is currently[^.]*\./i, ' ')
    .replace(/\s*Reception expectation at the trigger was\s*\{[\s\S]*$/i, '')
    .replace(/\s*\{["']method version["'][\s\S]*$/i, '')
    .replace(/\s+/g, ' ').trim();
}

export function detectorEvidence(props = {}) {
  const observedText = String(props.assessment?.observation || props.detection_reason || props.detail || '');
  const gapFromText = observedText.match(/(?:gap|silence|interruption)[^.!?]{0,75}?(?:lasting|of|for)\s+(\d{2,5})\s*(?:min(?:utes)?|mins?)/i);
  const gap = Number(props.gap_minutes ?? props.ais_gap_minutes ?? props.duration_minutes ?? gapFromText?.[1] ?? NaN);
  const codes = Array.isArray(props.reason_codes) ? props.reason_codes : [];
  const details = codes.map((code) => CODE_LABELS[code]).filter(Boolean);
  return {
    gap: Number.isFinite(gap) && gap > 0 ? gap : null,
    details,
    interpretation: codes.some((code) => /COVERAGE|NEIGHBOUR|REPORTING/.test(code))
      ? 'The interruption is notable in the available reception context. AIS silence alone cannot establish whether the transmitter was switched off, equipment failed or reception was lost.'
      : 'The detector identified an observation requiring review. Its cause has not been established.',
    limitations: 'AIS reception is incomplete. Without independent corroboration, vessel intent and activity during a gap remain unknown.',
  };
}

export function timelineReport(events = []) {
  const positions = events.flatMap((event) => {
    const geometry = event?.geometry;
    if (geometry?.type === 'Point' && geometry.coordinates?.length >= 2) return [{ at: event.at, coordinates: geometry.coordinates, source: event.source }];
    if (geometry?.type === 'LineString') return (geometry.coordinates || []).filter((c) => c.length >= 2).map((coordinates) => ({ at: event.at, coordinates, source: event.source }));
    return [];
  });
  return { positions, first: events[0] || null, last: events.at(-1) || null };
}
