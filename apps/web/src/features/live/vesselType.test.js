import test from 'node:test';
import assert from 'node:assert/strict';

import { shipTypeLabel, isExcludedVesselType } from './vesselType.js';

test('a missing/empty/literal-unknown value returns Unknown', () => {
  assert.equal(shipTypeLabel(null), 'Unknown');
  assert.equal(shipTypeLabel(''), 'Unknown');
  assert.equal(shipTypeLabel('unknown'), 'Unknown');
});

test('an unrecognised numeric code returns Unknown, not a fabricated category', () => {
  // docs/fixes.md M0.4: used to return "Other vessel" here, implying a
  // determined class that was never actually established.
  assert.equal(shipTypeLabel(0), 'Unknown (0)');
  assert.equal(shipTypeLabel(95), 'Unknown (95)');
  assert.doesNotMatch(shipTypeLabel(95), /Other vessel/);
});

test('a recognised code still labels its specific class', () => {
  assert.equal(shipTypeLabel(37), 'Pleasure craft (37)');
  assert.equal(shipTypeLabel(30), 'Fishing (30)');
  assert.equal(shipTypeLabel(80), 'Tanker (80)');
});


test('passenger and pleasure ship types are excluded regardless of subtype', () => {
  for (const value of [37, '37', 60, 61, 66, 69, 'passenger ship', 'pleasure craft']) {
    assert.equal(isExcludedVesselType(value), true, String(value));
  }
  for (const value of [null, '', 0, 30, 36, 51, 70, 80, 'cargo', 'unknown']) {
    assert.equal(isExcludedVesselType(value), false, String(value));
  }
});
