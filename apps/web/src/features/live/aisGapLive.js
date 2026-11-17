import { reconstructAisGaps, aisGapMapFeatures } from '../play/aisGapGeometry.js';

// Reuse the canonical Live events. Never convert a single fix or a modelled
// drift estimate into an invented AIS reappearance.
export function liveAisGapFeatures(events = []) {
  const features = [];
  for (const event of events) {
    const p = event?.properties || {};
    if (!(p.episode_family === 'gap_episode' || ['gap', 'long_gap', 'ais_gap'].includes(p.anomaly_type))) continue;
    const points = (Array.isArray(p.observed_track) ? p.observed_track : [])
      .map((fix) => ({ ...fix, at: fix.at || fix.ts || fix.timestamp_utc }));
    const vessel = { mmsi: p.linked_mmsi || p.mmsi || '', track_points: points };
    const { gaps } = reconstructAisGaps([vessel], { minMinutes: 30 });
    features.push(...aisGapMapFeatures(gaps).features);
    if (gaps.length || p.gap_still_open !== true || event.geometry?.type !== 'Point') continue;
    const [lon, lat] = event.geometry.coordinates || [];
    if (!Number.isFinite(lon) || !Number.isFinite(lat) || Math.abs(lat) > 90 || Math.abs(lon) > 180) continue;
    features.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] },
      properties: { kind: 'ais_last_observed', mmsi: vessel.mmsi,
        at: p.last_observed_at || p.timestamp_utc || '',
        status: 'open_gap_no_reappearance', duration_min: Number(p.current_silent_seconds || 0) / 60,
        interpretation: 'Last reported AIS position; no observed reappearance. Not a drift prediction.' } });
  }
  return { type: 'FeatureCollection', features };
}
