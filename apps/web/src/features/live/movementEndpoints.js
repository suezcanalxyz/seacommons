import { reconstructAisGaps } from '../play/aisGapGeometry.js';

export function aisUtcTimestamp(value) {
  if (typeof value !== 'string') return null;
  const iso = value.trim();
  const normalized = /^\d{4}-\d{2}-\d{2}T[\d:.]+$/.test(iso) ? `${iso}Z` : iso;
  return Number.isFinite(Date.parse(normalized)) ? normalized : null;
}

function validEndpoint(point, at) {
  if (point?.lat == null || point?.lon == null || ![point.lat, point.lon].every((value) => typeof value === 'number'
    || (typeof value === 'string' && value.trim()))) return null;
  const lat = Number(point.lat);
  const lon = Number(point.lon);
  return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180
    ? { lat, lon, at: at || null } : null;
}

export function liveMovementEndpoints(feature) {
  const props = feature?.properties || {};
  const movement = props.movement_evidence;
  const isGap = ['gap', 'long_gap', 'ais_gap'].includes(String(props.anomaly_type || props.event || '').toLowerCase())
    || props.episode_family === 'gap_episode'
    || /ais.*gap|long gap/i.test(String(props.category || props.title || ''));
  const fromAt = aisUtcTimestamp(movement?.from_at);
  const toAt = aisUtcTimestamp(movement?.to_at);
  const from = fromAt ? validEndpoint(movement?.from, fromAt) : null;
  const to = fromAt && toAt && Date.parse(toAt) > Date.parse(fromAt)
    ? validEndpoint(movement?.to, toAt) : null;
  if (from) return { from, to, isGap, fromLabel: 'Last observed fix' };
  if (isGap && feature.geometry?.type === 'Point') {
    const [lon, lat] = feature.geometry.coordinates;
    return { from: validEndpoint({ lon, lat }), to: null, isGap, fromLabel: 'Published gap position' };
  }
  return { from: null, to: null, isGap, fromLabel: '' };
}

export function selectedLiveMovementEndpoints(feature) {
  const endpoints = liveMovementEndpoints(feature);
  const properties = feature?.properties || {};
  if (endpoints.fromLabel !== 'Published gap position' || !endpoints.from) return endpoints;
  if (endpoints.isGap && properties.gap_still_open !== true && !properties.movement_evidence) {
    const points = (Array.isArray(properties.observed_track) ? properties.observed_track : [])
      .filter((fix) => validEndpoint(fix))
      .map((fix) => ({ ...fix, at: aisUtcTimestamp(fix.at || fix.ts || fix.timestamp_utc) }));
    const { gaps } = reconstructAisGaps([{ track_points: points }]);
    const last = gaps.at(-1);
    if (last) return {
      ...endpoints, from: validEndpoint(last.from, last.from.at), to: validEndpoint(last.to, last.to.at),
      fromLabel: 'Last observed AIS fix',
    };
  }
  const at = aisUtcTimestamp(properties.last_observed_at || (properties.gap_still_open === true ? properties.timestamp_utc : null));
  if (!at) return endpoints;
  return {
    ...endpoints, from: { ...endpoints.from, at }, fromLabel: 'Last observed AIS fix',
  };
}

export function latestLiveAisFix(feature, dossier) {
  const { from, to, fromLabel } = selectedLiveMovementEndpoints(feature);
  const candidates = [
    dossier?.latest_ais_fix, ...((dossier?.track_points) || []),
    ...(feature?.properties?.observed_track || []), to,
    fromLabel !== 'Published gap position' ? from : null,
  ];
  let latest = null;
  for (const fix of candidates) {
    const at = aisUtcTimestamp(fix?.ts || fix?.at || fix?.timestamp_utc);
    const time = Date.parse(at);
    if (!Number.isFinite(time) || (latest && time <= Date.parse(latest.ts))) continue;
    const position = validEndpoint(fix, at);
    if (position) latest = { ...fix, ...position, ts: at };
  }
  return latest;
}

export function liveMovementMapFeatures(feature, endpoints = liveMovementEndpoints(feature)) {
  const { from, to, isGap, fromLabel } = endpoints;
  if (!from) return [];
  const first = [from.lon, from.lat];
  const features = [{ type: 'Feature', geometry: { type: 'Point', coordinates: first },
    properties: { kind: 'ais_last_observed', at: from.at, label: fromLabel } }];
  if (to) {
    const second = [to.lon, to.lat];
    features.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [first, second] },
      properties: { kind: 'ais_gap_unobserved_connection' } });
    features.push({ type: 'Feature', geometry: { type: 'Point', coordinates: second },
      properties: { kind: 'ais_first_reappearance', at: to.at, label: isGap ? 'Next recorded AIS fix' : 'Next recorded fix' } });
  }
  return features;
}
