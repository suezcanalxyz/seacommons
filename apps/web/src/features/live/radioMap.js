export function radioCoordinates(row) {
  const values = [row.longitude, row.latitude];
  if (!values.every((value) => typeof value === 'number'
    || (typeof value === 'string' && value.trim()))) return null;
  const [lon, lat] = values.map(Number);
  return Number.isFinite(lon) && Number.isFinite(lat) && Math.abs(lon) <= 180 && Math.abs(lat) <= 90
    && (lon !== 0 || lat !== 0) ? [lon, lat] : null;
}

export function radioFeature(row, type) {
  const coordinates = radioCoordinates(row);
  return {
    type: 'Feature',
    geometry: coordinates ? { type: 'Point', coordinates } : null,
    properties: type === 'radio_receiver' ? {
      ...row, radio_type: type, visual_color: '#a78bfa',
      capabilities_json: JSON.stringify(row.capabilities || []),
    } : {
      ...row, radio_type: type, visual_color: row.category === 'distress' ? '#ff3b3b'
        : row.category === 'urgency' ? '#f59e0b' : row.category === 'safety' ? '#38bdf8' : '#a78bfa',
      ais_association_json: JSON.stringify(row.ais_association || null),
    },
  };
}

// Verified regional network presentation, not a claim about RF propagation.
// Inland international HF relays are still listed in receiver diagnostics but
// excluded from the Mediterranean coastal station layer.
const MEDITERRANEAN_CURATED_STATIONS = new Set([
  'catania_openwebrx', 'cagliari_hf_monitor', 'salerno_hf_monitor',
  'zakynthos_hf_monitor', 'thessaloniki_hf_monitor', 'edessa_hf_monitor',
  'mallorca_hf_monitor', 'rome_hf_monitor',
]);
export function isMediterraneanReceiver(row) {
  const lat = Number(row?.latitude);
  const lon = Number(row?.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
  if (lat < 29 || lat > 46 || lon < -7 || lon > 37) return false;
  return MEDITERRANEAN_CURATED_STATIONS.has(String(row?.receiver_id));
}

/** Fail closed: stale receiver-mesh data must not remain on an operational map. */
export function liveActiveReceiverMarkers(mesh) {
  if (mesh?.fresh !== true || !Array.isArray(mesh.receivers)) return [];
  return mesh.receivers
    .filter((row) => row?.active === true && Boolean(row.receiver_id) && isMediterraneanReceiver(row))
    .map((row) => radioFeature(row, 'radio_receiver'))
    .filter((feature) => feature.geometry?.type === 'Point');
}
