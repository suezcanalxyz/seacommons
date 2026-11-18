import test from 'node:test';
import assert from 'node:assert/strict';
import { reconstructAisGaps, aisGapMapFeatures } from './aisGapGeometry.js';
const fixes = [
  { at: '2026-10-28T09:59:22Z', lat: 35, lon: 15, source: 'AIS' },
  { at: '2026-10-28T10:34:46Z', lat: 35.1, lon: 15.2, source: 'AIS' },
  { at: '2026-10-28T10:46:24Z', lat: 35.12, lon: 15.22, source: 'AIS' },
];
test('AIS gap is a bounded absence with two observed endpoints, not an observed track', () => {
  const result = reconstructAisGaps([{ mmsi: '636019532', track_points: fixes }], { minMinutes: 30 });
  assert.equal(result.gaps.length, 1);
  assert.equal(result.gaps[0].durationMin, 35 + 24 / 60);
  assert.ok(result.gaps[0].distanceKm > 0);
  assert.deepEqual(result.observed.features[0].geometry.coordinates, [[15.2,35.1],[15.22,35.12]]);
  const features = aisGapMapFeatures(result.gaps).features;
  assert.deepEqual(features.map((f) => f.properties.kind), ['ais_gap_unobserved_connection','ais_last_observed','ais_first_reappearance']);
  assert.equal(features[0].properties.interpretation.includes('actual vessel route unknown'), true);
});
test('open gap with no reappearance is not invented', () => {
  const result = reconstructAisGaps([{ mmsi: '1', track_points: fixes.slice(0, 1) }]);
  assert.equal(result.gaps.length, 0);
  assert.equal(result.observed.features.length, 0);
});
test('invalid positions and out-of-order timestamps do not create phantom gaps', () => {
  const result = reconstructAisGaps([{ mmsi: '1', track_points: [fixes[2], { ...fixes[1], lat: 900 }, fixes[0]] }], { minMinutes: 30 });
  assert.equal(result.gaps.length, 1);
  assert.equal(result.gaps[0].from.at, fixes[0].at);
  assert.equal(result.gaps[0].to.at, fixes[2].at);
});

test('rejects null coordinates without moving a gap endpoint to zero', () => {
  const result = reconstructAisGaps([{ track_points: [{ ...fixes[0], lat: null, lon: null }, fixes[1]] }]);
  assert.deepEqual(result.gaps, []);
  assert.deepEqual(result.observed.features, []);
});

test('LIVE and PLAY both break the observed track across a recorded gap', async () => {
  const { splitObservedTrackSegments } = await import('../live/observedTrack.js');
  const result = reconstructAisGaps([{ track_points: fixes }]);
  assert.deepEqual(splitObservedTrackSegments(fixes), result.segments);
  const [line, start, end] = aisGapMapFeatures(result.gaps).features;
  assert.deepEqual(line.geometry.coordinates, [start.geometry.coordinates, end.geometry.coordinates]);
});
