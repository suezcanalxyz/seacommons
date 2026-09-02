import test from 'node:test';
import assert from 'node:assert/strict';

import { assessmentView, locationLabel, relativeTime } from './eventPresentation.js';

const NOW = Date.parse('2026-09-01T12:00:00Z');

test('relativeTime never goes negative on clock skew', () => {
  assert.equal(relativeTime('2026-09-01T12:05:00Z', NOW), 'just now');
});

test('relativeTime buckets minutes, hours, days', () => {
  assert.equal(relativeTime('2026-09-01T11:18:00Z', NOW), '42 min ago');
  assert.equal(relativeTime('2026-09-01T09:00:00Z', NOW), '3 h ago');
  assert.equal(relativeTime('2026-08-30T12:00:00Z', NOW), '2 d ago');
  assert.equal(relativeTime(undefined, NOW), '');
});

test('a real point shows coordinates and uncertainty', () => {
  const label = locationLabel({ location_uncertainty_m: 1200 }, [11.9423, 34.2715]);
  assert.equal(label.tone, 'ok');
  assert.match(label.text, /34\.2715, 11\.9423/);
  assert.match(label.text, /±1\.2 km/);
});

test('disputed OCR is flagged for review, with or without a point', () => {
  assert.equal(
    locationLabel({ coordinate_review_status: 'machine_ocr_disputed_needs_review' }, null).text,
    'OCR DISPUTED · REVIEW REQUIRED',
  );
  assert.equal(
    locationLabel({ coordinate_review_status: 'machine_ocr_disputed_needs_review' }, [1, 2]).tone,
    'review',
  );
});

test('a land humanitarian case never shows a maritime point', () => {
  assert.equal(
    locationLabel({ humanitarian_case_type: 'land_humanitarian' }, null).text,
    'LOCATION WITHHELD',
  );
});

test('missing coordinate reads as a reason, not "position unavailable"', () => {
  assert.equal(locationLabel({ media_transport: 'x_media_ocr' }, null).text, 'OCR PROCESSING');
  assert.equal(locationLabel({ coordinate_source: 'region_area' }, null).text, 'REGION ONLY');
  assert.equal(locationLabel({}, null).text, 'POSITION NOT EXTRACTED');
});

test('assessmentView returns null when no assessment is attached', () => {
  assert.equal(assessmentView({}), null);
  assert.equal(assessmentView({ event_assessment: 'nope' }), null);
});

test('assessmentView normalizes the backend EventAssessment', () => {
  const view = assessmentView({
    event_assessment: {
      observation: 'AIS navigation status 2 persisted across 4 reports over 13 minutes, speed 0.3 kn.',
      interpretation: 'The vessel is reporting itself as not under command...',
      evidence_level: 'sustained_observation',
      confidence: 0.62,
      supporting_evidence: ['sustained: 4 reports over 13 minutes'],
      contradicting_evidence: [],
      caveats: ['AIS navigation status is reported by the vessel; the operational cause is not independently confirmed.'],
      recommended_action: 'Monitor as vessel safety context.',
      rule_ids: ['ais_nav_status:2'],
      classification_version: 'assessment/v1',
    },
  });
  assert.equal(view.evidenceLevel, 'sustained observation');
  assert.equal(view.confidencePct, 62);
  assert.equal(view.supporting.length, 1);
  assert.match(view.caveats[0], /not independently confirmed/);
  assert.equal(view.recommendedAction, 'Monitor as vessel safety context.');
});

test('two different assessments produce different interpretations', () => {
  const brief = assessmentView({ event_assessment: { interpretation: 'A', observation: 'x', evidence_level: 'single_observation', confidence: 0.2 } });
  const sustained = assessmentView({ event_assessment: { interpretation: 'B', observation: 'y', evidence_level: 'sustained_observation', confidence: 0.7 } });
  assert.notEqual(brief.interpretation, sustained.interpretation);
  assert.ok(sustained.confidencePct > brief.confidencePct);
});
