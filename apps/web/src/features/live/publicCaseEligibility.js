// Editorial exclusions only affect the public case views. The source record is
// retained so the classification can be reviewed against the original text.
export function isPublicCaseEligible(record = {}) {
  const id = String(record.incident_id || record.intel_event_id || record.id || '').replace(/^intel:/, '');
  if (id === '0175f9e2') return false;

  const classification = [record.humanitarian_case_type, record.incident_type, record.case_type];
  if (classification.some((value) => ['advocacy', 'policy_commentary'].includes(value))) return false;

  const title = String(record.title || '').toLowerCase();
  return !(title.includes('@seawatch_intl') && title.includes('stands for ignorance'));
}
