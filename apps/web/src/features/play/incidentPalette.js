import { classifyEventVisual, EVENT_VISUAL_CATEGORIES } from '../intel/categories.js';

const COLORS = new Map(EVENT_VISUAL_CATEGORIES.map(({ key, color }) => [key, color]));

// Semantic event classification, never transport domain or severity.
// For historical records without anomaly metadata retain the domain fallback.
export function playIncidentColor(incident = {}) {
  const domain = String(incident.main_category || incident.domain || '').toLowerCase();
  const explicit = incident.visual_category;
  if (explicit && COLORS.has(explicit)) return COLORS.get(explicit);
  if (domain === 'humanitarian' || incident.source === 'alarm_phone') return '#ff3b3b';
  const kind = String(incident.incident_type || incident.anomaly_type || '').toLowerCase();
  const visual = classifyEventVisual({
    source: incident.source,
    incident_type: kind,
    anomaly_type: incident.anomaly_type || kind,
    maritime_domain: incident.maritime_domain,
    type: kind,
  });
  if (visual.key !== 'context') return visual.color;
  return domain === 'maritime' ? '#76b7fa' : '#c6a6ff';
}
