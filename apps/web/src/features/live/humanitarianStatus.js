// Canonical incident state is the operational authority. Source-post metadata
// (humanitarian_status) is historical evidence and may lag later follow-ups.
const CANONICAL = new Set(['active', 'needs_review', 'resolved', 'outcome_unknown']);
const LIFECYCLE = new Set(['active', 'needs_review', 'resolved', 'archived']);

export function humanitarianOperationalStatus(props = {}, fallbackLifecycle = '') {
  const canonical = String(props.incident_status || '').trim().toLowerCase();
  if (CANONICAL.has(canonical)) return canonical.replace(/_/g, ' ');

  const lifecycle = String(props.incident_lifecycle || fallbackLifecycle || '').trim().toLowerCase();
  if (LIFECYCLE.has(lifecycle)) {
    return lifecycle === 'archived' ? 'outcome unknown' : lifecycle.replace(/_/g, ' ');
  }
  return 'Not established';
}

export function humanitarianSourceReportedStatus(props = {}) {
  const sourceStatus = String(props.humanitarian_status || '').trim();
  return sourceStatus ? sourceStatus.replace(/_/g, ' ') : null;
}
