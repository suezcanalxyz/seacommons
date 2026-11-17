import test from 'node:test';
import assert from 'node:assert/strict';
import { isAttackIncident, createAttackMarkerImage } from './attackMarker.js';
test('attack symbol uses explicit classification, not severity or narrative', () => {
  assert.equal(isAttackIncident({ incident_type: 'drone_attack' }), true);
  assert.equal(isAttackIncident({ maritime_domain: 'attack' }), true);
  assert.equal(isAttackIncident({ type: 'missile_strike' }), true);
  assert.equal(isAttackIncident({ severity: 'critical', title: 'Drone attack' }), false);
  assert.equal(isAttackIncident({ incident_type: 'ais_gap', domain: 'humanitarian' }), false);
});
test('attack marker is a compact image with transparent pixels', () => {
  const icon = createAttackMarkerImage();
  assert.equal(icon.data.length, 32 * 32 * 4);
  assert.equal(icon.data[3], 0);
  assert.ok(icon.data.some((value) => value === 255));
});
