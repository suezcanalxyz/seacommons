/**
 * Civil SAR fleet panel model (docs/fixes.md F-13 / Phase 4.2 / 4.3).
 *
 * The full registry response is grouped into Civil NGO vs State SAR, and each
 * asset gets a position-freshness state independent of whether it is on the
 * map. An AIS-offline vessel stays in the list; it just has no marker.
 */

const LIVE_MAX_S = 10 * 60;
const STALE_MAX_S = 60 * 60;

function positionAgeSeconds(properties, now) {
  const raw = properties.position_timestamp_utc
    || properties.last_seen_utc
    || properties.last_seen
    || properties.timestamp
    || properties.updated_at;
  if (!raw) return null;
  const then = Date.parse(raw);
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.round((now - then) / 1000));
}

/** 'live' | 'stale' | 'offline' | 'unverified-identity' */
export function fleetStatus(feature, now = Date.now()) {
  const p = feature.properties || {};
  if (p.identity_status && p.identity_status !== 'verified' && p.identity_status !== 'probable') {
    return 'unverified-identity';
  }
  const positioned = Array.isArray(feature.geometry?.coordinates);
  if (!positioned || p.ais_status === 'offline') return 'offline';
  const age = positionAgeSeconds(p, now);
  if (age === null) return 'live';
  if (age <= LIVE_MAX_S) return 'live';
  if (age <= STALE_MAX_S) return 'stale';
  return 'offline';
}

function asset(feature, now) {
  const p = feature.properties || {};
  return {
    mmsi: String(p.mmsi || ''),
    name: p.ship_name || p.vessel_name || p.name || `MMSI ${p.mmsi || '—'}`,
    org: p.org || p.organisation || '',
    operatorType: p.operator_type || 'civil_ngo',
    status: fleetStatus(feature, now),
    positioned: Array.isArray(feature.geometry?.coordinates),
  };
}

/** { civil: Asset[], state: Asset[] } sorted live-first then by name. */
export function fleetGroups(features = [], now = Date.now()) {
  const order = { live: 0, stale: 1, 'unverified-identity': 2, offline: 3 };
  const sortAssets = (list) => list.sort(
    (a, b) => (order[a.status] - order[b.status]) || a.name.localeCompare(b.name),
  );
  const civil = [];
  const state = [];
  for (const feature of features) {
    const item = asset(feature, now);
    (item.operatorType === 'civil_ngo' ? civil : state).push(item);
  }
  return { civil: sortAssets(civil), state: sortAssets(state) };
}
