// Colors + tags for the MDA anomaly layer (spoofing, sanctions, dark-fleet,
// infrastructure). Keyed by anomaly_type when the backend sets one
// (core/mda/watch.py's scan_* methods), falling back to the event's
// top-level `type` for the few kinds that don't have a sub-type
// (ais_rendezvous, dark_candidate, conflict_event, navwarning,
// correlated_alert). Single source of truth for the map layer paint, the
// hover-popup tag, and the legend, so all three always agree.
//
// Terminology and evidence_level follow docs/prompt.md section 6/7: never
// state spoofing/dark-fleet activity as fact when it's an algorithmic
// inference ("Possible ..."), and separate what was literally observed
// (an AIS message stopped arriving) from what that's interpreted to mean
// (derived), from an official record match (official_match).
export const MDA_ANOMALY_CATEGORIES = {
  circle_spoof: { color: '#f472b6', tag: 'Possible spoofing — circular track', evidence_level: 'derived', description: 'AIS track draws an unnaturally regular circle — a typical signature of a spoofed signal, not a confirmed one.' },
  position_jump: { color: '#fb923c', tag: 'Possible spoofing — position jump', evidence_level: 'derived', description: 'The vessel "jumps" between positions too far apart in too little time — physically impossible for a real transit, not confirmed to be deliberate.' },
  static_spoof: { color: '#facc15', tag: 'Possible spoofing — frozen track', evidence_level: 'derived', description: 'Position frozen for too long while surrounding traffic keeps moving.' },
  cable_proximity: { color: '#22d3ee', tag: 'Near subsea cable', evidence_level: 'observed', description: 'Vessel stopped or slow directly over a known subsea cable.' },
  loiter: { color: '#38bdf8', tag: 'Prolonged presence near infrastructure', evidence_level: 'observed', description: 'Extended dwell near a platform/pipeline with no declared reason.' },
  gap: { color: '#a78bfa', tag: 'AIS reporting gap', evidence_level: 'observed', description: 'AIS signal interruption in an area with known GNSS jamming — a stopped signal, not proof it was switched off deliberately.' },
  long_gap: { color: '#7c3aed', tag: 'Long AIS reporting gap', evidence_level: 'observed', description: 'AIS interruption of more than 6 hours — more significant than a short gap, still not proof of intent.' },
  sdn_match: { color: '#ef4444', tag: 'Sanctioned', evidence_level: 'official_match', description: 'Vessel or owner on an official sanctions list (OFAC/OpenSanctions).' },
  identity_anomaly: { color: '#d97706', tag: 'Identity anomaly', evidence_level: 'derived', description: 'Invalid IMO or MMSI from a reserved block — identity worth checking, not necessarily sanctions.' },
  mmsi_duplicate: { color: '#dc2626', tag: 'Duplicate MMSI', evidence_level: 'derived', description: 'Same MMSI transmitted from two positions far apart at the same time — cloned or borrowed identity.' },
  ais_rendezvous: { color: '#c026d3', tag: 'Ship-to-ship transfer (possible)', evidence_level: 'derived', description: 'Two vessels alongside long enough for a possible ship-to-ship transfer — not visually confirmed cargo movement.' },
  dark_candidate: { color: '#4ade80', tag: 'Possible dark vessel', evidence_level: 'correlated', description: 'Vessel detected by satellite (SAR) with no matching AIS signal in the area.' },
  conflict_event: { color: '#ea580c', tag: 'Conflict zone', evidence_level: 'official_match', description: 'Event inside a known conflict area.' },
  navwarning: { color: '#fde047', tag: 'Nav warning', evidence_level: 'official_match', description: 'Official notice to mariners.' },
  correlated_alert: { color: '#ffb347', tag: 'Corroborated', evidence_level: 'correlated', description: 'Multiple independent sources confirm the same event.' },
};

export const MDA_ANOMALY_DEFAULT = { color: '#60a5fa', tag: 'Anomaly', evidence_level: 'observed', description: 'Signal detected, category not yet classified.' };

export function mdaCategoryKey(type, anomalyType) {
  if (anomalyType && MDA_ANOMALY_CATEGORIES[anomalyType]) return anomalyType;
  if (type && MDA_ANOMALY_CATEGORIES[type]) return type;
  return null;
}

export function mdaCategoryInfo(type, anomalyType) {
  const key = mdaCategoryKey(type, anomalyType);
  return key ? MDA_ANOMALY_CATEGORIES[key] : MDA_ANOMALY_DEFAULT;
}

// MapLibre `match` expression stops, built once from the same table above.
export function mdaAnomalyColorExpression() {
  const stops = [];
  for (const [key, info] of Object.entries(MDA_ANOMALY_CATEGORIES)) {
    stops.push(key, info.color);
  }
  return ['match', ['get', 'category'], ...stops, MDA_ANOMALY_DEFAULT.color];
}
