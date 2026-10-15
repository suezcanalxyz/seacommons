/**
 * The public Overall API reports exact retained IntelEvent rows, not incidents
 * or historical ingestion that retention has already erased.
 * Fail closed: absent or malformed counters must never coerce into zero.
 */
export function nonnegativeCount(value) {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

export function retainedEvidence(payload) {
  if (payload?.scope !== 'retained_intel_events' || !payload.intel_record) return null;
  const total = nonnegativeCount(payload.intel_record.total_events);
  const positioned = nonnegativeCount(payload.intel_record.positioned_events);
  const generatedAt = payload.generated_at;
  if (total === null || positioned === null || positioned > total ||
      typeof generatedAt !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(generatedAt) || !Number.isFinite(Date.parse(generatedAt))) return null;
  return { total, positioned, generatedAt, source: 'retained_intel_events' };
}

export function retainedMetricFallback(payload) {
  const evidence = retainedEvidence(payload);
  return evidence ? { parsed_events: evidence.total } : null;
}
