import test from 'node:test';
import assert from 'node:assert/strict';
import { historicalDriftFeatures } from './driftGeometry.js';

test('preserves simulated track and uncertainty cone as distinct map geometries', () => {
  const result = historicalDriftFeatures([{ id: 'case-1', at: '2026-10-28T00:00:00Z', type: 'drift', geometry: { type: 'LineString', coordinates: [[14, 35], [15, 36]] }, properties: { forecast: true, cone_24h: { type: 'Polygon', coordinates: [[[14,35],[15,35],[15,36],[14,35]]] } } }]);
  assert.deepEqual(result.features.map(f => f.properties.geometry_semantics), ['simulated_trajectory', 'model_uncertainty_area']);
  assert.ok(result.features.every(f => f.properties.forecast && !f.properties.observed));
});
test('does not invent geometry or treat AIS observations as forecast', () => {
  assert.equal(historicalDriftFeatures([{ type: 'ais', properties: { forecast: false }, geometry: { type: 'Point', coordinates: [14,35] } }, { type: 'drift', properties: { forecast: true } }]).features.length, 0);
});

test('rejects invalid coordinates and unclosed uncertainty polygons', () => {
  const base = { type: 'drift', properties: { forecast: true, cone_24h: { type: 'Polygon', coordinates: [[[14,35],[15,35],[15,36]]] } }, geometry: { type: 'LineString', coordinates: [[14,35],[181,36]] } };
  assert.equal(historicalDriftFeatures([base]).features.length, 0);
  assert.equal(historicalDriftFeatures([{ ...base, geometry: { type: 'LineString', coordinates: [[14,35],[15,36]] } }]).features.length, 1);
});

test('rejects degenerate closed rings and tolerates malformed collections', () => {
  const item = { id: 'case-2', type: 'drift', properties: { forecast: true, cone_24h: { type: 'Polygon', coordinates: [[[14,35],[14,35],[15,36],[14,35]]] } } };
  assert.equal(historicalDriftFeatures([item]).features.length, 0);
  assert.deepEqual(historicalDriftFeatures(null).features, []);
  assert.deepEqual(historicalDriftFeatures({ items: [item] }).features, []);
});

test('rejects collinear uncertainty rings without discarding a valid trajectory', () => {
  const item = { id: 'case-3', type: 'drift', at: '2026-10-30T12:00:00Z', geometry: { type: 'LineString', coordinates: [[14,35],[15,36]] }, properties: { forecast: true, cone_24h: { type: 'Polygon', coordinates: [[[14,35],[15,36],[16,37],[14,35]]] } } };
  const features = historicalDriftFeatures([item]).features;
  assert.deepEqual(features.map(f => f.properties.geometry_semantics), ['simulated_trajectory']);
});

test('rejects stationary zero-length simulated tracks while retaining valid uncertainty areas', () => {
  const item = { id: 'stationary', type: 'drift', geometry: { type: 'LineString', coordinates: [[14, 35], [14, 35]] }, properties: { forecast: true, cone_24h: { type: 'Polygon', coordinates: [[[14,35],[15,35],[15,36],[14,35]]] } } };
  assert.deepEqual(historicalDriftFeatures([item]).features.map(f => f.properties.geometry_semantics), ['model_uncertainty_area']);
});

test('rejects collinear polygons crossing the antimeridian', () => {
  const item = { type: 'drift', properties: { forecast: true, cone_24h: { type: 'Polygon', coordinates: [[[179, 0], [-179, 1], [-177, 2], [179, 0]]] } } };
  assert.deepEqual(historicalDriftFeatures([item]).features, []);
});


test('renders persisted OpenDrift GeoJSON Feature wrappers for humanitarian incidents', () => {
  const track = { type: 'LineString', coordinates: [[18.4, 33.1], [18.5, 33.0]] };
  const cone = { type: 'Polygon', coordinates: [[[18.4,33.0],[18.5,33.0],[18.5,33.1],[18.4,33.0]]] };
  const item = { id: 'humanitarian-drift', type: 'drift', properties: { forecast: true, domain: 'humanitarian', cone_24h: { type: 'Feature', geometry: cone, properties: { model: 'OpenDrift' } } }, geometry: { type: 'Feature', geometry: track, properties: {} } };
  const features = historicalDriftFeatures([item]).features;
  assert.deepEqual(features.map((f) => f.geometry), [track, cone]);
  assert.deepEqual(features.map((f) => f.properties.geometry_semantics), ['simulated_trajectory', 'model_uncertainty_area']);
});

test('never renders malformed persisted GeoJSON Feature wrappers', () => {
  const item = { id: 'invalid', type: 'drift', geometry: { type: 'Feature', geometry: null }, properties: { forecast: true, cone_24h: { type: 'Feature', geometry: { type: 'Point', coordinates: [18,33] } } } };
  assert.deepEqual(historicalDriftFeatures([item]).features, []);
});
