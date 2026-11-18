import test from 'node:test';
import assert from 'node:assert/strict';
import { isPublicCaseEligible } from './publicCaseEligibility.js';

test('commentary cannot enter the public case view under a legacy distress label', () => {
  assert.equal(isPublicCaseEligible({ incident_id: '0175f9e2', incident_type: 'distress' }), false);
  assert.equal(isPublicCaseEligible({ title: '@seawatch_intl: In Malta’s region, rescue stands for ignorance', incident_type: 'distress' }), false);
  assert.equal(isPublicCaseEligible({ humanitarian_case_type: 'advocacy', type: 'distress' }), false);
});

test('distress reports from the same organization and documented maritime cases remain eligible', () => {
  assert.equal(isPublicCaseEligible({ title: '@seawatch_intl: 24 people in distress', incident_type: 'distress' }), true);
  assert.equal(isPublicCaseEligible({ title: 'AIS gap', incident_type: 'ais_gap' }), true);
});
