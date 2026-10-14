import test from 'node:test';
import assert from 'node:assert/strict';
import { detectorEvidence, humanizeDetectorText, timelineReport } from './reportNarrative.js';

test('recognizes a 652 minute gap from actual observation and explains reception limitations', () => {
  const evidence = detectorEvidence({ assessment: { observation: 'AIS reporting gap for 265915769 lasting 652 min.' }, reason_codes: ['DENSE_REPORTING_HISTORY', 'NEIGHBOUR_TRAFFIC_CONTINUED'] });
  assert.equal(evidence.gap, 652);
  assert.equal(evidence.details.length, 2);
  assert.match(evidence.interpretation, /cannot establish/);
});
test('removes serialized technical payload from public prose', () => {
  const cleaned = humanizeDetectorText('AIS gap detected. Reception expectation at the trigger was {"method version":"1","positions":18}.');
  assert.equal(cleaned, 'AIS gap detected.');
});
test('does not create a trajectory when none is documented', () => {
  assert.deepEqual(timelineReport([{type:'observation',at:'2026-10-14T08:00:00Z'}]).positions, []);
});
