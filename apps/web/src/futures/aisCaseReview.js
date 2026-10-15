import { validIMO, validMMSI } from './aisCrossCheck.js';

export function caseIdentity(feature) {
  const p = feature?.properties || {};
  const imo = String(p.imo || '').trim();
  const mmsi = String(p.linked_mmsi || p.mmsi || '').trim();
  return {
    imo: validIMO(imo) ? imo : '',
    mmsi: validMMSI(mmsi) ? mmsi : '',
  };
}

export function reviewableCases(features) {
  if (!Array.isArray(features)) return [];
  return features.filter((feature) => {
    const coords = feature?.geometry?.coordinates;
    const { imo, mmsi } = caseIdentity(feature);
    return feature?.geometry?.type === 'Point'
      && Array.isArray(coords) && coords.length === 2
      && coords.every((x) => Number.isFinite(Number(x)))
      && (imo || mmsi);
  });
}

export function caseKey(feature) {
  return String(feature?.id || feature?.properties?.id || '');
}

export function parseAISClock(value) {
  if (!value) return null;
  const raw = String(value);
  // SeaCommons legacy timestamps are UTC even without a timezone suffix.
  const iso = /(?:Z|[+-]\d{2}:\d{2})$/.test(raw) ? raw : raw + 'Z';
  const stamp = Date.parse(iso);
  return Number.isFinite(stamp) ? new Date(stamp) : null;
}

export function aisFreshness(value, nowMs = Date.now()) {
  const dt = parseAISClock(value);
  if (!dt || dt.getTime() > nowMs + 5 * 60000) return 'unknown';
  const age = nowMs - dt.getTime();
  return age <= 15 * 60000 ? 'recent' : age <= 2 * 3600000 ? 'delayed' : 'stale';
}

export function coordsText(value, positive, negative) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return 'Unavailable';
  const coordinate = Number(value);
  return Math.abs(coordinate).toFixed(5) + '° ' + (coordinate < 0 ? negative : positive);
}

export function renderTime(value) {
  const date = parseAISClock(value);
  return date ? date.toISOString().replace('T', ' ').replace('.000Z', ' UTC').replace('Z', ' UTC') : 'Unavailable';
}
