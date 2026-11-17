// A missing AIS interval is not an observed vessel route. Endpoints are stored
// fixes, and the connecting segment is strictly a visual uncertainty cue.
const empty = () => ({ type: 'FeatureCollection', features: [] });
const validFix = (p) => Number.isFinite(Number(p?.lat)) && Number.isFinite(Number(p?.lon))
  && Math.abs(Number(p.lat)) <= 90 && Math.abs(Number(p.lon)) <= 180
  && Number.isFinite(Date.parse(p?.at));
const radians = (degrees) => degrees * Math.PI / 180;
export function endpointDistanceKm(a, b) {
  const dLat = radians(Number(b.lat) - Number(a.lat));
  const dLon = radians(Number(b.lon) - Number(a.lon));
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(radians(Number(a.lat)))
    * Math.cos(radians(Number(b.lat))) * Math.sin(dLon / 2) ** 2;
  return 6371.0088 * 2 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))));
}
export function reconstructAisGaps(vessels = [], { minMinutes = 30 } = {}) {
  const gaps = [];
  const observed = [];
  for (const vessel of vessels) {
    const fixes = (vessel.track_points || []).filter(validFix)
      .sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
    let segment = [];
    const flush = () => {
      if (segment.length >= 2) observed.push({ type: 'Feature',
        geometry: { type: 'LineString', coordinates: segment.map((p) => [Number(p.lon), Number(p.lat)]) },
        properties: { kind: 'observed_ais_track', mmsi: vessel.mmsi } });
      segment = [];
    };
    for (const fix of fixes) {
      const previous = segment.at(-1);
      if (previous) {
        const minutes = (Date.parse(fix.at) - Date.parse(previous.at)) / 60000;
        if (minutes >= minMinutes) {
          flush();
          gaps.push({ mmsi: vessel.mmsi, from: previous, to: fix,
            durationMin: minutes, distanceKm: endpointDistanceKm(previous, fix),
            status: 'bounded_missing_observations' });
        }
      }
      segment.push(fix);
    }
    flush();
  }
  return { gaps, observed: { ...empty(), features: observed } };
}
export function aisGapMapFeatures(gaps = []) {
  const features = [];
  for (const gap of gaps) {
    const base = { mmsi: String(gap.mmsi || ''), from_utc: gap.from.at, to_utc: gap.to.at,
      duration_min: Math.round(gap.durationMin * 10) / 10,
      distance_km: Math.round(gap.distanceKm * 10) / 10,
      interpretation: 'No stored AIS fixes; actual vessel route unknown' };
    features.push({ type: 'Feature', geometry: { type: 'LineString',
      coordinates: [[Number(gap.from.lon), Number(gap.from.lat)], [Number(gap.to.lon), Number(gap.to.lat)]] },
    properties: { ...base, kind: 'ais_gap_unobserved_connection' } });
    for (const [fix, kind] of [[gap.from, 'ais_last_observed'], [gap.to, 'ais_first_reappearance']]) {
      features.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [Number(fix.lon), Number(fix.lat)] },
        properties: { ...base, kind, at: fix.at, source: fix.source || 'AIS stored fix' } });
    }
  }
  return { ...empty(), features };
}
