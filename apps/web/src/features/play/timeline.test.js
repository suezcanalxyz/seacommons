import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

import {
  normalizeTimeline,
  selectFrame,
  selectSatelliteObservation,
  statusLabel,
  resolveGlobalTimelinePosition,
  incidentsAtCutoff,
  incidentCollection,
  timelineAtCutoff,
  incidentStatusAtCutoff,
  satelliteFootprintCollection,
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


test('global archive timeline is ALL at its rightmost position and temporal before it', () => {
  const incidents = [
    { incident_id: 'a', reported_at: '2026-09-01T00:00:00Z' },
    { incident_id: 'b', reported_at: '2026-09-05T00:00:00Z' },
  ];
  assert.deepEqual(resolveGlobalTimelinePosition(incidents, 1000), { mode: 'all', cutoff: null });
  const past = resolveGlobalTimelinePosition(incidents, 500);
  assert.equal(past.mode, 'temporal');
  assert.equal(past.cutoff, '2026-09-03T00:00:00.000Z');
});

test('cutoff filters archive incidents and selected-case evidence without leaking the future', () => {
  const incidents = [
    { incident_id: 'a', reported_at: '2026-09-01T00:00:00Z', geometry: { type: 'Point', coordinates: [10, 35] } },
    { incident_id: 'b', reported_at: '2026-09-04T00:00:00Z', geometry: { type: 'Point', coordinates: [12, 36] } },
  ];
  const cutoff = '2026-09-02T00:00:00.000Z';
  assert.deepEqual(incidentsAtCutoff(incidents, cutoff).map((x) => x.incident_id), ['a']);
  const fc = incidentCollection(incidents, cutoff);
  assert.equal(fc.features.length, 1);
  assert.equal(fc.features[0].properties.incident_id, 'a');
  const timeline = normalizeTimeline([
    { id: 'r', at: '2026-09-01T01:00:00Z', type: 'report' },
    { id: 'future', at: '2026-09-03T01:00:00Z', type: 'satellite' },
  ]);
  assert.deepEqual(timelineAtCutoff(timeline, cutoff).map((x) => x.id), ['r']);
  assert.equal(timelineAtCutoff(timeline, null).length, 2);
});

test('Play surface exposes ALL-first global timeline and mobile drawer/sheet contracts', async () => {
  const { readFile } = await import('node:fs/promises');
  const jsx = await readFile(new URL('./PlayTimeline.jsx', import.meta.url), 'utf8');
  const css = await readFile(new URL('./play.css', import.meta.url), 'utf8');
  assert.match(jsx, /aria-label="Global archive timeline"/);
  assert.match(jsx, /play-mobile-cases-toggle/);
  assert.match(jsx, /play-evidence.*is-open/);
  assert.match(jsx, /next_offset/);
  assert.match(jsx, /!visibleIncidents\.some/);
  assert.match(css, /\.play-mobile-cases-toggle/);
  assert.match(css, /\.play-evidence\.is-open/);
});

test('incident status at cutoff uses only transitions knowable by that time', () => {
  const incident = {
    incident_status: 'resolved',
    status_history: [
      { at: '2026-09-03T00:00:00Z', from_state: 'active', to_state: 'needs_review' },
      { at: '2026-09-04T00:00:00Z', from_state: 'needs_review', to_state: 'resolved' },
    ],
  };
  assert.equal(incidentStatusAtCutoff(incident, '2026-09-02T00:00:00Z'), 'active');
  assert.equal(incidentStatusAtCutoff(incident, '2026-09-03T12:00:00Z'), 'needs_review');
  assert.equal(incidentStatusAtCutoff(incident, null), 'resolved');
});

test('Play map style keeps a visible street-map fallback under satellite imagery', async () => {
  const { playMapStyle } = await import('./timeline.js');
  const style = playMapStyle('2026-09-04');
  assert.equal(style.layers[0].id, 'base-map');
  assert.equal(style.layers[0].paint?.['raster-opacity'] ?? 1, 1);
  assert.equal(style.layers[1].id, 'satellite-context');
  assert.ok((style.layers[1].paint?.['raster-opacity'] ?? 1) < 1);
});

test('Play panels use the same glass treatment as public Live and keep the map dominant', async () => {
  const css = await readFile(new URL('./play.css', import.meta.url), 'utf8');
  assert.match(css, /background:\s*rgba\(3,\s*10,\s*14,\s*\.88\)/);
  assert.match(css, /backdrop-filter:\s*blur\(18px\)\s+saturate\(1\.15\)/);
  assert.match(css, /\.play-shell\.has-selection/);
  assert.match(css, /grid-template-columns:\s*min\(392px,\s*32vw\)\s+minmax\(0,\s*1fr\)\s+0/);
});

test('mergeIncidentPages progressively deduplicates pages and keeps the newest version', async () => {
  const { mergeIncidentPages } = await import('./timeline.js');
  const first = [
    { incident_id: 'a', reported_at: '2026-09-05T10:00:00Z', title: 'A' },
    { incident_id: 'b', reported_at: '2026-09-05T09:00:00Z', title: 'B old' },
  ];
  const second = [
    { incident_id: 'b', reported_at: '2026-09-05T09:00:00Z', title: 'B new' },
    { incident_id: 'c', reported_at: '2026-09-04T08:00:00Z', title: 'C' },
  ];
  const merged = mergeIncidentPages(first, second);
  assert.deepEqual(merged.map((item) => item.incident_id), ['a', 'b', 'c']);
  assert.equal(merged.find((item) => item.incident_id === 'b').title, 'B new');
});


test('Copernicus OData thumbnails are renderable image sources even without a filename extension', async () => {
  const { satelliteRasterDescriptor } = await import('./timeline.js');
  const observation = {
    source: 'copernicus_dataspace',
    properties: {
      asset_ref: 'https://datahub.creodias.eu/odata/v1/Assets(abc)/$value',
      bbox: [14, 35, 15, 36],
      mission: 'Sentinel-1',
    },
  };
  const source = satelliteRasterDescriptor(observation);
  assert.equal(source.type, 'image');
  assert.equal(source.url, observation.properties.asset_ref);
});

test('Sentinel footprints remain visible when no raster preview is available', () => {
  const timeline = [{
    id: 's1', type: 'satellite', source: 'copernicus_dataspace',
    geometry: { type: 'Polygon', coordinates: [[[14,35],[15,35],[15,36],[14,35]]] },
    properties: { mission: 'Sentinel-1', sensor_type: 'sar' },
  }];
  const collection = satelliteFootprintCollection(timeline);
  assert.equal(collection.features.length, 1);
  assert.equal(collection.features[0].properties.mission, 'Sentinel-1');
});
