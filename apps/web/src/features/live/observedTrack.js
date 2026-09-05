export function splitObservedTrackSegments(points = [], maxJumpKm = 80) {
  const valid = points
    .map((point) => ({ ...point, lon: Number(point?.lon), lat: Number(point?.lat) }))
    .filter((point) => Number.isFinite(point.lon) && Number.isFinite(point.lat));
  if (valid.length < 2) return [];
  const segments = [];
  let current = [valid[0]];
  const kmBetween = (a, b) => {
    const meanLat = ((a.lat + b.lat) / 2) * Math.PI / 180;
    const dx = (b.lon - a.lon) * 111 * Math.cos(meanLat);
    const dy = (b.lat - a.lat) * 111;
    return Math.hypot(dx, dy);
  };
  for (let i = 1; i < valid.length; i += 1) {
    if (kmBetween(valid[i - 1], valid[i]) > maxJumpKm) {
      if (current.length >= 2) segments.push(current);
      current = [valid[i]];
    } else {
      current.push(valid[i]);
    }
  }
  if (current.length >= 2) segments.push(current);
  return segments;
}
