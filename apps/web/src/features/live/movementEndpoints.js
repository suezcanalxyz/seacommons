function validEndpoint(point, at) {
  if (point?.lat == null || point?.lon == null || point.lat === '' || point.lon === '') return null;
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
  const from = validEndpoint(movement?.from, movement?.from_at);
  const to = validEndpoint(movement?.to, movement?.to_at);
  if (from) return { from, to, isGap, fromLabel: 'Last observed fix' };
  if (isGap && feature.geometry?.type === 'Point') {
    const [lon, lat] = feature.geometry.coordinates;
    return { from: validEndpoint({ lon, lat }), to: null, isGap, fromLabel: 'Published gap position' };
  }
  return { from: null, to: null, isGap, fromLabel: '' };
}

export function liveMovementMapFeatures(feature) {
  const { from, to, isGap, fromLabel } = liveMovementEndpoints(feature);
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
