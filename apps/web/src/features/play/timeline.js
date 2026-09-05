function parseTime(value) {
  const ms = Date.parse(String(value || ''));
  return Number.isFinite(ms) ? ms : Number.POSITIVE_INFINITY;
}

export function normalizeTimeline(items = []) {
  return [...items]
    .filter((item) => item && item.at)
    .sort((a, b) => parseTime(a.at) - parseTime(b.at))
    .map((item, frameIndex) => ({ ...item, frameIndex }));
}

export function selectFrame(timeline = [], index = 0) {
  if (!timeline.length) return { index: -1, item: null, geometry: null };
  const clamped = Math.max(0, Math.min(timeline.length - 1, Number(index) || 0));
  const item = timeline[clamped];
  let geometry = item.geometry || null;
  if (!geometry) {
    for (let i = clamped - 1; i >= 0; i -= 1) {
      if (timeline[i]?.geometry) {
        geometry = timeline[i].geometry;
        break;
      }
    }
  }
  return { index: clamped, item, geometry };
}

export function selectSatelliteObservation(timeline = [], at) {
  const target = parseTime(at);
  const candidates = timeline.filter((item) => item?.type === 'satellite');
  if (!candidates.length) return null;
  const before = candidates
    .filter((item) => parseTime(item.at) <= target)
    .sort((a, b) => parseTime(b.at) - parseTime(a.at));
  if (before.length) return before[0];
  return [...candidates].sort((a, b) => parseTime(a.at) - parseTime(b.at))[0];
}

export function statusLabel(status) {
  const value = String(status || '').toLowerCase();
  if (value === 'needs_review') return 'NEEDS REVIEW';
  if (value === 'outcome_unknown' || value === 'archived') return 'OUTCOME UNKNOWN';
  if (value === 'resolved') return 'RESOLVED';
  if (value === 'active') return 'ACTIVE';
  return value ? value.replaceAll('_', ' ').toUpperCase() : 'UNKNOWN';
}

export function satelliteRasterDescriptor(observation) {
  const props = observation?.properties || {};
  const asset = String(props.asset_ref || '');
  if (!asset || (!asset.startsWith('https://') && !asset.startsWith('http://'))) return null;
  if (asset.includes('{z}') && asset.includes('{x}') && asset.includes('{y}')) {
    return { type: 'raster', tiles: [asset], tileSize: 256 };
  }
  const bbox = Array.isArray(props.bbox) ? props.bbox.map(Number) : null;
  const looksLikeImage = /\.(?:png|jpe?g|webp)(?:\?|$)/i.test(asset);
  if (!looksLikeImage || bbox?.length !== 4 || bbox.some((value) => !Number.isFinite(value))) return null;
  const [west, south, east, north] = bbox;
  return {
    type: 'image',
    url: asset,
    coordinates: [[west, north], [east, north], [east, south], [west, south]],
  };
}

export function incidentsAtCutoff(incidents = [], cutoff = null) {
  if (!cutoff) return [...incidents];
  const cutoffMs = parseTime(cutoff);
  return incidents.filter((incident) => parseTime(incident?.reported_at) <= cutoffMs);
}

export function timelineAtCutoff(timeline = [], cutoff = null) {
  if (!cutoff) return [...timeline];
  const cutoffMs = parseTime(cutoff);
  return timeline.filter((item) => parseTime(item?.at) <= cutoffMs);
}

export function resolveGlobalTimelinePosition(incidents = [], position = 1000, max = 1000) {
  const times = incidents.map((incident) => parseTime(incident?.reported_at)).filter(Number.isFinite);
  if (!times.length || Number(position) >= Number(max)) return { mode: 'all', cutoff: null };
  const min = Math.min(...times);
  const latest = Math.max(...times);
  const ratio = Math.max(0, Math.min(1, Number(position) / Number(max || 1)));
  return { mode: 'temporal', cutoff: new Date(min + ((latest - min) * ratio)).toISOString() };
}

export function incidentCollection(incidents = [], cutoff = null) {
  return {
    type: 'FeatureCollection',
    features: incidentsAtCutoff(incidents, cutoff)
      .filter((incident) => incident?.geometry?.type === 'Point')
      .map((incident) => ({
        type: 'Feature',
        geometry: incident.geometry,
        properties: {
          incident_id: incident.incident_id,
          incident_status: incidentStatusAtCutoff(incident, cutoff),
          case_type: incident.case_type || 'incident',
          source: incident.source || '',
          domain: incident.domain || 'humanitarian',
          reported_at: incident.reported_at || '',
          title: incident.title || '',
        },
      })),
  };
}


export function incidentStatusAtCutoff(incident, cutoff = null) {
  const current = incident?.incident_status || 'outcome_unknown';
  if (!cutoff) return current;
  const cutoffMs = parseTime(cutoff);
  const history = [...(incident?.status_history || [])]
    .filter((item) => Number.isFinite(parseTime(item?.at)))
    .sort((a, b) => parseTime(a.at) - parseTime(b.at));
  let effective = null;
  for (const transition of history) {
    const at = parseTime(transition.at);
    if (at <= cutoffMs) effective = transition.to_state || effective;
    else if (effective == null) return transition.from_state || current;
    else break;
  }
  return effective || current;
}
