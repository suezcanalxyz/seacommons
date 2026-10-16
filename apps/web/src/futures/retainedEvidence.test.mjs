import test from 'node:test';
import assert from 'node:assert/strict';
import { retainedEvidence, retainedMetricFallback, nonnegativeCount } from './retainedEvidence.js';

const sample = { scope:'retained_intel_events', generated_at:'2026-10-15T12:00:00Z',
  intel_record:{ total_events: 386456, positioned_events:385692 } };
test('accepts a verified retained inventory and maps exactly one metric', () => {
 assert.deepEqual(retainedMetricFallback(sample),{parsed_events:386456});
 assert.equal(retainedEvidence(sample).total,386456);
});
test('missing, malformed and contradictory counts never turn into zero', () => {
 for (const wrong of [null,undefined,'',NaN,-1,1.25,'0',Infinity]) assert.equal(nonnegativeCount(wrong),null);
 for(const [total,positioned] of [[null,0],[0,null],[3,4],[-1,0],['386456',5], [4,NaN]]) {
   assert.equal(retainedMetricFallback({...sample,intel_record:{total_events:total,positioned_events:positioned}}),null);
 }
 assert.equal(retainedMetricFallback({...sample,generated_at:'broken'}),null);
});
test('valid zero remains meaningful when accompanied by a complete contract', () => {
 assert.deepEqual(retainedMetricFallback({...sample,intel_record:{total_events:0,positioned_events:0}}),{parsed_events:0});
});
