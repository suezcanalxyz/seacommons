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
