import test from 'node:test';
import assert from 'node:assert/strict';
import { liveMovementEndpoints, liveMovementMapFeatures } from './movementEndpoints.js';

test('a position jump maps both recorded fixes and the anomalous connection', () => {
  const feature = { properties: { movement_evidence: {
    from: { lat: 37, lon: 12 }, to: { lat: 36, lon: 14 },
    from_at: '2026-11-17T17:56:02Z', to_at: '2026-11-17T17:56:47Z',
  } } };
  const { from, to, isGap } = liveMovementEndpoints(feature);
  assert.equal(isGap, false);
  assert.equal(from.at, '2026-11-17T17:56:02Z');
  assert.equal(to.at, '2026-11-17T17:56:47Z');
  const mapped = liveMovementMapFeatures(feature);
  assert.deepEqual(mapped.map(({ geometry }) => geometry.coordinates), [[12, 37], [[12, 37], [14, 36]], [14, 36]]);
});

test('a legacy gap maps its published position without inferring reappearance from the track', () => {
  const feature = { geometry: { type: 'Point', coordinates: [14, 36] },
    properties: { episode_family: 'gap_episode', observed_track: [{ lat: 38, lon: 13 }] } };
  const { from, to, fromLabel } = liveMovementEndpoints(feature);
  assert.deepEqual(from, { lon: 14, lat: 36, at: null });
  assert.equal(fromLabel, 'Published gap position');
  assert.equal(to, null);
  assert.equal(liveMovementMapFeatures(feature).length, 1);
});

test('missing fix coordinates cannot render as zero', () => {
  const feature = { properties: { movement_evidence: { from: { lat: null, lon: 12 } } } };
  assert.deepEqual(liveMovementMapFeatures(feature), []);
});
