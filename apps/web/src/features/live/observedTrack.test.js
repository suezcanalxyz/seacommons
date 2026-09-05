import assert from 'node:assert/strict';
import test from 'node:test';
import { splitObservedTrackSegments } from './observedTrack.js';

test('splits impossible AIS jumps instead of drawing trans-Mediterranean spokes', () => {
  const segments = splitObservedTrackSegments([
    { lon: 8.74, lat: 41.92 },
    { lon: 8.75, lat: 41.91 },
    { lon: 2.46, lat: 39.42 },
    { lon: 2.47, lat: 39.43 },
  ]);
  assert.equal(segments.length, 2);
  assert.deepEqual(segments.map((s) => s.length), [2, 2]);
});

test('keeps plausible observed AIS fixes in one segment', () => {
  const segments = splitObservedTrackSegments([
    { lon: 14.0, lat: 35.0 },
    { lon: 14.1, lat: 35.05 },
    { lon: 14.2, lat: 35.1 },
  ]);
  assert.equal(segments.length, 1);
  assert.equal(segments[0].length, 3);
});
