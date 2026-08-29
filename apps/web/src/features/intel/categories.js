// Shared signal taxonomy for the map, the legend and the OSINT panels.
// One place so the map colours, the legend rows and the dashboard icons never
// drift apart. `distress` (SAR), `correlated_alert` and the `ais_*` types each
// render on their own dedicated map layer and are listed here only for the
// legend / icon lookups.

export const SIGNAL_CATEGORIES = [
  { key: 'distress',   label: 'Active distress',   color: '#ff3b3b', types: ['distress'],
    description: 'A distress beacon (AIS-SART/MOB/EPIRB) or a corroborated SAR report. Auto-published — treat as real until stood down.' },
  { key: 'fused',      label: 'Correlated alert',  color: '#ffb347', types: ['correlated_alert'],
    description: 'Multiple independent sources agree on the same event (spoofing, dark rendezvous, infrastructure proximity, identity fraud...). Never opened from one source alone.' },
  { key: 'ais',        label: 'AIS anomaly / spike', color: '#60a5fa', types: ['ais_spike', 'ais_anomaly'],
    description: 'A transponder pattern that does not look like normal navigation — circular track, teleport jump, or a signal frozen in place. Flags identity questions, not identity conclusions.' },
  { key: 'incident',   label: 'Vessel incident',   color: '#fb923c', types: ['vessel_incident'],
    description: 'A vessel\'s own AIS navigational-status report: aground, or "not under command" (cannot manoeuvre). Not under command is frequently set for benign reasons — always needs operator review before acting on it.' },
  { key: 'hazard',     label: 'Natural hazard (GDACS)', color: '#f59e0b', types: ['gdacs'],
    description: 'Environmental/weather hazard from the GDACS global disaster feed — context, not a vessel-specific signal.' },
  { key: 'iom',        label: 'IOM missing migrants', color: '#b91c1c', types: ['iom_incident'],
    description: 'A recorded incident from IOM\'s Missing Migrants project — historical/aggregate reporting, not a live position.' },
  { key: 'social',     label: 'Social post',       color: '#818cf8', types: ['twitter', 'mastodon', 'bluesky'],
    description: 'An unverified public social-media report. Lowest-confidence source class until corroborated by another channel.' },
  { key: 'news',       label: 'News / RSS',        color: '#94a3b8', types: ['news'],
    description: 'A published news article matched to a location/event — secondary reporting, not a primary observation.' },
  { key: 'ngo',        label: 'NGO activity',      color: '#4ade80', types: ['ngo_activity'],
    description: 'A public status update from an NGO SAR vessel or operation.' },
  { key: 'other',      label: 'Other signal',      color: '#8bf0c5', types: [],
    description: 'Does not match a known category yet.' },
];

// Categories that get their own toggleable map layer over the shared
// `intel-events` source (distress / fused / ais have dedicated sources).
export const INTEL_MAP_CATEGORIES = SIGNAL_CATEGORIES.filter(
  (c) => !['distress', 'fused', 'ais', 'other'].includes(c.key) && c.types.length,
);

const _BY_TYPE = SIGNAL_CATEGORIES.reduce((acc, cat) => {
  for (const t of cat.types) acc[t] = cat.key;
  return acc;
}, {});

const _COLOR_BY_KEY = SIGNAL_CATEGORIES.reduce((acc, cat) => {
  acc[cat.key] = cat.color;
  return acc;
}, {});

export function categoryOf(type) {
  return _BY_TYPE[type] || 'other';
}

const _CAT_BY_KEY = SIGNAL_CATEGORIES.reduce((acc, cat) => {
  acc[cat.key] = cat;
  return acc;
}, {});

/** Human-readable definition + reliability caveat for a raw event `type`. */
export function descriptionOf(type) {
  return (_CAT_BY_KEY[categoryOf(type)] || _CAT_BY_KEY.other).description;
}

export function categoryColor(key) {
  return _COLOR_BY_KEY[key] || _COLOR_BY_KEY.other;
}

// MapLibre `match` expression: feature `type` -> category colour, for the
// generic intel-events circle layer.
export function categoryColorExpression() {
  const expr = ['match', ['get', 'type']];
  for (const cat of SIGNAL_CATEGORIES) {
    if (!cat.types.length) continue;
    expr.push(cat.types.length === 1 ? cat.types[0] : cat.types, cat.color);
  }
  expr.push(_COLOR_BY_KEY.other);
  return expr;
}
