// Shared signal taxonomy for the map, the legend and the OSINT panels.
// One place so the map colours, the legend rows and the dashboard icons never
// drift apart. `distress` (SAR), `correlated_alert` and the `ais_*` types each
// render on their own dedicated map layer and are listed here only for the
// legend / icon lookups.

export const SIGNAL_CATEGORIES = [
  { key: 'distress',   label: 'Active distress',   color: '#ff3b3b', types: ['distress'] },
  { key: 'fused',      label: 'Correlated alert',  color: '#ffb347', types: ['correlated_alert'] },
  { key: 'ais',        label: 'AIS anomaly / spike', color: '#60a5fa', types: ['ais_spike', 'ais_anomaly'] },
  { key: 'incident',   label: 'Vessel incident',   color: '#fb923c', types: ['vessel_incident'] },
  { key: 'hazard',     label: 'Natural hazard (GDACS)', color: '#f59e0b', types: ['gdacs'] },
  { key: 'iom',        label: 'IOM missing migrants', color: '#b91c1c', types: ['iom_incident'] },
  { key: 'social',     label: 'Social post',       color: '#818cf8', types: ['twitter', 'mastodon', 'bluesky'] },
  { key: 'news',       label: 'News / RSS',        color: '#94a3b8', types: ['news'] },
  { key: 'ngo',        label: 'NGO activity',      color: '#4ade80', types: ['ngo_activity'] },
  { key: 'other',      label: 'Other signal',      color: '#8bf0c5', types: [] },
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
