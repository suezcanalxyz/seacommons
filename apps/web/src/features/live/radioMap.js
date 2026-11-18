import { receiverNominalChannels } from './radioChannels.js';

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

/** The public map distinguishes operator-connected RF from physically geolocated
 * catalogue candidates. Never count a reachable HTTP endpoint as reception.
 */
const BARCELONA_RESEARCH_CANDIDATE = Object.freeze({
  receiver_id: 'ea3hru_barcelona_research',
  station_label: 'EA3HRU · Barcelona / Pallejà',
  latitude: 41.411, longitude: 1.999,
  active: false,
  state: 'review_required',
  source_class: 'passive_operator_status',
  audit_date: '2026-11-18',
  candidate_only: true,
  capabilities: [{ min_hz: 0, max_hz: 30000000, modes: ['usb'] }],
});

export function mediterraneanReceiverMapMarkers(mesh) {
  if (mesh?.fresh !== true || !Array.isArray(mesh.receivers)) return [];
  const relevant = mesh.receivers.filter((row) =>
    Boolean(row?.receiver_id) && isMediterraneanReceiver(row));
  // A distinct, verified receiver physically in Barcelona: candidate only.
  // Duplicate EA3HRU URL, private Valencia and non-MF OpenWebRX excluded.
  if (!relevant.some((row) => row.receiver_id === BARCELONA_RESEARCH_CANDIDATE.receiver_id)) {
    relevant.push(BARCELONA_RESEARCH_CANDIDATE);
  }
  return relevant.map((row) => {
    const isActive = row.active === true;
    const feature = radioFeature({
      ...row,
      active: isActive,
      station_label: row.station_label || row.public_label || row.receiver_id,
      station_status: isActive ? 'receiving'
        : row.candidate_only ? 'candidate'
          : row.state === 'offline' ? 'offline' : 'not_connected',
      nominal_channel_ids: receiverNominalChannels(row),
    }, 'radio_receiver');
    return feature;
  }).filter((feature) => feature.geometry?.type === 'Point');
}
