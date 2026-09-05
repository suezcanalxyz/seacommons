import assert from 'node:assert/strict';
import test from 'node:test';

import {
  normalizeTimeline,
  selectFrame,
  selectSatelliteObservation,
  statusLabel,
} from './timeline.js';

const items = [
  { id: 'later', at: '2026-09-05T12:00:00Z', type: 'attending_news', geometry: null },
  { id: 'report', at: '2026-09-04T12:00:00Z', type: 'report', geometry: { type: 'Point', coordinates: [14, 35] } },
  { id: 'sat-before', at: '2026-09-04T10:00:00Z', type: 'satellite', properties: { asset_ref: 'before.jpg' } },
  { id: 'drift', at: '2026-09-04T12:10:00Z', type: 'drift', geometry: { type: 'LineString', coordinates: [[14, 35], [14.2, 35.2]] } },
];

test('normalizeTimeline sorts ascending and assigns stable frame indices', () => {
  const result = normalizeTimeline(items);
  assert.deepEqual(result.map((item) => item.id), ['sat-before', 'report', 'drift', 'later']);
  assert.deepEqual(result.map((item) => item.frameIndex), [0, 1, 2, 3]);
});

test('selectFrame clamps index and carries the last known geometry', () => {
  const timeline = normalizeTimeline(items);
  const first = selectFrame(timeline, -10);
  const last = selectFrame(timeline, 999);
  assert.equal(first.item.id, 'sat-before');
  assert.equal(last.item.id, 'later');
  assert.deepEqual(last.geometry, { type: 'LineString', coordinates: [[14, 35], [14.2, 35.2]] });
});

test('selectSatelliteObservation chooses the closest snapshot at or before the frame', () => {
  const timeline = normalizeTimeline([
    ...items,
    { id: 'sat-after', at: '2026-09-04T14:00:00Z', type: 'satellite', properties: { asset_ref: 'after.jpg' } },
  ]);
  const observation = selectSatelliteObservation(timeline, '2026-09-04T12:10:00Z');
  assert.equal(observation.id, 'sat-before');
  assert.equal(observation.properties.asset_ref, 'before.jpg');
});

test('statusLabel never exposes archived as an incident outcome', () => {
  assert.equal(statusLabel('resolved'), 'RESOLVED');
  assert.equal(statusLabel('needs_review'), 'NEEDS REVIEW');
  assert.equal(statusLabel('outcome_unknown'), 'OUTCOME UNKNOWN');
  assert.equal(statusLabel('archived'), 'OUTCOME UNKNOWN');
});

test('satelliteRasterDescriptor supports dated tiles and bounded image previews', async () => {
  const { satelliteRasterDescriptor } = await import('./timeline.js');
  const tile = satelliteRasterDescriptor({
    properties: { asset_ref: 'https://example.test/{z}/{y}/{x}.jpg', bbox: [13.9, 35.3, 14.3, 35.7] },
  });
  assert.equal(tile.type, 'raster');
  assert.deepEqual(tile.tiles, ['https://example.test/{z}/{y}/{x}.jpg']);

  const image = satelliteRasterDescriptor({
    properties: { asset_ref: 'https://example.test/preview.jpg', bbox: [14, 35, 14.2, 35.2] },
  });
  assert.equal(image.type, 'image');
  assert.deepEqual(image.coordinates[0], [14, 35.2]);
});

test('satelliteRasterDescriptor rejects non-image product assets', async () => {
  const { satelliteRasterDescriptor } = await import('./timeline.js');
  assert.equal(satelliteRasterDescriptor({ properties: { asset_ref: 's3://bucket/product.safe' } }), null);
});
