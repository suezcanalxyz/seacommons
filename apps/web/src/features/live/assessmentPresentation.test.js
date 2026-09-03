import test from 'node:test';
import assert from 'node:assert/strict';

import {
  assessmentConfidence,
  caveatsText,
  evidenceLevelText,
  interpretationText,
  observationText,
} from './assessmentPresentation.js';

test('Interpretation prefers assessment.interpretation over category help text', () => {
  const properties = { assessment: { interpretation: 'Case-specific text.' } };
  assert.equal(interpretationText(properties, 'Generic category help.'), 'Case-specific text.');
});

test('Interpretation falls back to category help text when there is no assessment', () => {
  assert.equal(interpretationText({}, 'Generic category help.'), 'Generic category help.');
});

test('two NUC events with different evidence render different interpretation text', () => {
  const plain = { assessment: { interpretation: 'Not under command, plain report.' } };
  const jammed = { assessment: { interpretation: 'Not under command, GNSS interference nearby.' } };
  assert.notEqual(
    interpretationText(plain, 'fallback'),
    interpretationText(jammed, 'fallback'),
  );
});

test('Observation prefers assessment.observation, then detection_reason, then detail, then type', () => {
  assert.equal(
    observationText({ assessment: { observation: 'A' }, detection_reason: 'B', detail: 'C' }, 'D'),
    'A',
  );
  assert.equal(observationText({ detection_reason: 'B', detail: 'C' }, 'D'), 'B');
  assert.equal(observationText({ detail: 'C' }, 'D'), 'C');
  assert.equal(observationText({}, 'D'), 'D');
});

test('evidenceLevelText prefers the assessment value over the flat legacy field', () => {
  assert.equal(
    evidenceLevelText({ assessment: { evidence_level: 'observed' }, evidence_level: 'derived from maritime data' }),
    'observed',
  );
  assert.equal(evidenceLevelText({ evidence_level: 'derived from maritime data' }), 'derived from maritime data');
  assert.equal(evidenceLevelText({}, 'fallback'), 'fallback');
});

test('assessmentConfidence prefers the assessment value over legacy confidence fields', () => {
  assert.equal(assessmentConfidence({ assessment: { confidence: 0.6 }, confidence: 0.9 }), 0.6);
  assert.equal(assessmentConfidence({ confidence: 0.9 }), 0.9);
  assert.equal(assessmentConfidence({ anomaly_confidence: 0.4 }), 0.4);
  assert.equal(assessmentConfidence({}), undefined);
});

test('caveatsText joins caveats, and is empty when there are none', () => {
  assert.equal(
    caveatsText({ assessment: { caveats: ['First.', 'Second.'] } }),
    'First. Second.',
  );
  assert.equal(caveatsText({ assessment: { caveats: [] } }), '');
  assert.equal(caveatsText({}), '');
});
