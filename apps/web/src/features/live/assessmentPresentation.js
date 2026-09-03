/**
 * Case-specific EventAssessment presentation (docs/fixes.md M0.2).
 *
 * ConePanel's "Interpretation" row used to always be
 * descriptionOf(props.type) -- near-identical text for every event of the
 * same type. The backend now projects a nested `assessment` object (built
 * from that specific event's own evidence, core/intel/assessment.py) for
 * the kinds it has an assessor for. These helpers pick it when present and
 * fall back to the older flat fields / category help text otherwise --
 * never invent assessment content on the frontend.
 */

/** The Observation row value: case-specific evidence first, generic label last. */
export function observationText(properties = {}, fallbackEventType = '') {
  return (
    properties.assessment?.observation
    || properties.detection_reason
    || properties.detail
    || fallbackEventType
  );
}

/**
 * The Interpretation row value. `categoryHelpText` is descriptionOf(type) --
 * category help only now, never the primary case-specific text (docs/
 * fixes.md M0.2: "descriptionOf() remains category help only").
 */
export function interpretationText(properties = {}, categoryHelpText = '') {
  return properties.assessment?.interpretation || categoryHelpText;
}

export function evidenceLevelText(properties = {}, fallback = '') {
  return properties.assessment?.evidence_level || properties.evidence_level || fallback;
}

export function assessmentConfidence(properties = {}) {
  return properties.assessment?.confidence ?? properties.confidence ?? properties.anomaly_confidence;
}

/** Joined caveats string for display, or '' when there are none to show. */
export function caveatsText(properties = {}) {
  const caveats = properties.assessment?.caveats;
  return Array.isArray(caveats) && caveats.length > 0 ? caveats.join(' ') : '';
}
