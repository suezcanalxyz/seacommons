/**
 * Convert historical PLAY drift items into explicit simulated map features.
 * Never promote a forecast into an AIS observation or infer a missing cone.
 */
const validPosition = (p) => Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]) && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90;
// Unwrap antimeridian crossings before checking for zero-area rings.
// Raw longitude differences (179 -> -179) can otherwise invent an area.
const nonZeroArea = (ring) => {
  const points = ring.slice(0, -1);
  let previous = points[0][0];
  const unwrapped = points.map(([lon, lat], index) => {
    if (index === 0) return [previous, lat];
    let delta = lon - previous;
    delta = ((delta + 180) % 360 + 360) % 360 - 180;
    previous += delta;
    return [previous, lat];
  });
  const area2 = unwrapped.reduce((sum, [x, y], i) => {
    const [nx, ny] = unwrapped[(i + 1) % unwrapped.length];
    return sum + x * ny - nx * y;
  }, 0);
  return Math.abs(area2) > 1e-10;
};
const validRing = (ring) => Array.isArray(ring) && ring.length >= 4 && ring.every(validPosition) && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1] && new Set(ring.slice(0, -1).map(([lon, lat]) => `${lon},${lat}`)).size >= 3 && nonZeroArea(ring);
const validPolygon = (rings) => Array.isArray(rings) && rings.length > 0 && rings.every(validRing);
const validCone = (cone) => cone?.type === 'Polygon' ? validPolygon(cone.coordinates) : cone?.type === 'MultiPolygon' && Array.isArray(cone.coordinates) && cone.coordinates.length > 0 && cone.coordinates.every(validPolygon);

// The persisted OpenDrift API stores GeoJSON Feature wrappers, while older
// records may store bare geometries. Both are valid inputs; never synthesize
// geometry from a missing or malformed model output.
const unwrapGeometry = (value) => value?.type === 'Feature' ? value.geometry : value;

export function historicalDriftFeatures(items = []) {
  const features = [];
  for (const item of Array.isArray(items) ? items : []) {
    if (item?.type !== 'drift' || item?.properties?.forecast !== true) continue;
    const props = { drift_id: item.id, forecast: true, observed: false, at: item.at };
    const track = unwrapGeometry(item.geometry);
    if (track?.type === 'LineString' && Array.isArray(track.coordinates) && track.coordinates.length >= 2 && track.coordinates.every(validPosition) && new Set(track.coordinates.map(([lon, lat]) => `${lon},${lat}`)).size >= 2) {
      features.push({ type: 'Feature', geometry: track, properties: { ...props, geometry_semantics: 'simulated_trajectory' } });
    }
    const cone = unwrapGeometry(item.properties?.cone_24h);
    if (validCone(cone)) {
      features.push({ type: 'Feature', geometry: cone, properties: { ...props, geometry_semantics: 'model_uncertainty_area', probability_calibrated: false } });
    }
  }
  return { type: 'FeatureCollection', features };
}
