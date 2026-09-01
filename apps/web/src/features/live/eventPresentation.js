/**
 * Humanitarian card presentation helpers (docs/fixes.md F-12 / Phase 4.1).
 *
 * The event's report time must be visible in every row (not hidden in a
 * hover tooltip), and a missing coordinate must read as a *reason*, not a
 * bare "position unavailable".
 */

/** "42 min ago" / "3 h ago" / "2 d ago" -- never a negative interval. */
export function relativeTime(iso, now = Date.now()) {
  if (!iso) return '';
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return '';
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 45) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} d ago`;
}

function formatUncertainty(metres) {
  const value = Number(metres);
  if (!Number.isFinite(value) || value <= 0) return '';
  return value >= 1000 ? `±${(value / 1000).toFixed(1)} km` : `±${Math.round(value)} m`;
}

/**
 * The location cell for a humanitarian row.
 * Returns { text, tone } where tone is 'ok' | 'pending' | 'review' | 'none'.
 */
export function locationLabel(properties = {}, coords = null) {
  const review = String(properties.coordinate_review_status || '').toLowerCase();
  const status = String(properties.location_status || '').toLowerCase();
  const source = String(properties.coordinate_source || '').toLowerCase();
  const uncertainty = formatUncertainty(
    properties.location_uncertainty_m ?? properties.radius_m,
  );

  if (Array.isArray(coords) && coords.length >= 2
      && Number.isFinite(coords[0]) && Number.isFinite(coords[1])) {
    const point = `${Number(coords[1]).toFixed(4)}, ${Number(coords[0]).toFixed(4)}`;
    if (review.includes('disputed')) {
      return { text: `${point} · OCR DISPUTED · review required`, tone: 'review' };
    }
    return { text: uncertainty ? `${point} · ${uncertainty}` : point, tone: 'ok' };
  }

  if (status === 'withheld_from_maritime_map'
      || properties.humanitarian_case_type === 'land_humanitarian') {
    return { text: 'LOCATION WITHHELD', tone: 'none' };
  }
  if (review.includes('disputed')) {
    return { text: 'OCR DISPUTED · REVIEW REQUIRED', tone: 'review' };
  }
  if (status === 'processing'
      || properties.ocr_queue_state === 'deferred_queue_full'
      || (properties.media_transport === 'x_media_ocr' && !review)) {
    return { text: 'OCR PROCESSING', tone: 'pending' };
  }
  if (status === 'region_only' || source === 'region_area' || properties.area_geojson) {
    return { text: 'REGION ONLY', tone: 'pending' };
  }
  return { text: 'POSITION NOT EXTRACTED', tone: 'none' };
}
