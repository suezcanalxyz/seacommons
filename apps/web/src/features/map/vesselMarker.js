export const VESSEL_COLOR = '#7dd3fc';
export const NGO_VESSEL_COLOR = '#8bf0c5';

export function createVesselArrowImage(size = 48) {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, size, size);
  ctx.fillStyle = '#ffffff';
  const cx = size / 2;
  ctx.beginPath();
  // Pointed vessel triangle, heading aligned to its bow (top).
  ctx.moveTo(cx, 3);
  ctx.lineTo(size - 5, size - 5);
  ctx.lineTo(5, size - 5);
  ctx.closePath();
  ctx.fill();
  const idata = ctx.getImageData(0, 0, size, size);
  return { width: size, height: size, data: new Uint8Array(idata.data.buffer) };
}

export function isVesselArchiveIncident(incident = {}) {
  const kind = String(incident.case_type || '').toLowerCase();
  const id = String(incident.incident_id || '').toLowerCase();
  return id.startsWith('aisanom:') || [
    'ais_anomaly', 'ais_status', 'ais_behaviour', 'ais_integrity', 'vessel_incident',
  ].includes(kind);
}


/**
 * Do not infer a northbound vessel from missing or invalid AIS headings.
 * AIS heading 511 and COG 3600/360 are not directions; select an alternate
 * field only when it has a valid [0, 360) numeric value.
 * These are MapLibre style expressions, evaluated for each feature.
 */
const bearingValue = (key) => [
  'case', ['==', ['get', key], null], -1,
  ['to-number', ['get', key], -1],
];
const validBearing = (key) => [
  'all', ['>=', bearingValue(key), 0], ['<', bearingValue(key), 360],
];
export function vesselBearingExpression(keys = ['heading_deg', 'heading', 'course', 'cog']) {
  return ['case', ...keys.flatMap((key) => [validBearing(key), bearingValue(key)]), 0];
}
export function vesselDirectionalIconExpression(keys = ['heading_deg', 'heading', 'course', 'cog']) {
  return ['case', ['any', ...keys.map(validBearing)], 'vessel-arrow', 'vessel-diamond'];
}

export function createVesselDiamondImage(size = 48) {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, size, size);
  ctx.fillStyle = '#ffffff';
  const middle = size / 2;
  ctx.beginPath();
  ctx.moveTo(middle, 3);
  ctx.lineTo(size - 3, middle);
  ctx.lineTo(middle, size - 3);
  ctx.lineTo(3, middle);
  ctx.closePath();
  ctx.fill();
  const pixels = ctx.getImageData(0, 0, size, size);
  return { width: size, height: size, data: new Uint8Array(pixels.data.buffer) };
}
