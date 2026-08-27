import test from 'node:test';
import assert from 'node:assert/strict';

import {
  environmentalState,
  sampleWaveField,
  trajectoryDisplayMode,
  trajectoryFromGeoJson,
  weatherDescription,
} from './sceneModel.js';

test('normalizes trajectory timestamps and speed samples', () => {
  const result = trajectoryFromGeoJson({
    features: [{
      geometry: { type: 'LineString', coordinates: [[14, 35], [15, 36]] },
      properties: {
        timestamps_utc: ['2026-08-26T10:00:00Z', '2026-08-26T10:30:00Z'],
        speed_ms: [0.4, 0.8],
      },
    }],
  }, 10, 20);

  assert.deepEqual(result.coordinates, [[14, 35], [15, 36]]);
  assert.deepEqual(result.timeOffsets, [0, 1800]);
  assert.deepEqual(result.speeds, [0.4, 0.8]);
});

test('uses a stationary fallback for malformed trajectory input', () => {
  const result = trajectoryFromGeoJson({ features: [] }, 14.08, 35.52);
  assert.deepEqual(result, {
    coordinates: [[14.08, 35.52]],
    timeOffsets: [0],
    speeds: [0],
  });
});

test('normalizes bounded environmental forcing with explicit direction precedence', () => {
  const state = environmentalState({
    timestamp_utc: '2026-08-26T10:00:00Z',
    source: 'forecast',
    waves: { significant_height_m: 2.1, period_s: 7, direction_deg: 210 },
    wind: { speed_ms: 9, direction_deg: 120 },
    air: { cloud_cover_pct: 130, visibility_km: 0.1, humidity_pct: -4, is_day: false },
  });

  assert.equal(state.directionDeg, 210);
  assert.equal(state.cloudCover, 100);
  assert.equal(state.visibilityKm, 0.2);
  assert.equal(state.humidity, 0);
  assert.equal(state.isDay, false);
});

test('wave sampling is deterministic and finite', () => {
  const environment = environmentalState(null, new Date('2026-08-26T10:00:00Z'));
  const first = sampleWaveField(1200, -800, environment);
  const second = sampleWaveField(1200, -800, environment);
  assert.deepEqual(first, second);
  assert.ok(Object.values(first).every(Number.isFinite));
});

test('describes weather and trajectory provenance without renderer state', () => {
  assert.equal(weatherDescription(95), 'thunderstorm');
  assert.equal(trajectoryDisplayMode([]), 'awaiting trajectory');
  assert.equal(trajectoryDisplayMode([{ properties: { degraded: true } }]), 'degraded estimate');
  assert.equal(
    trajectoryDisplayMode([{ properties: { engine: 'seacommons-browser' } }]),
    'live browser engine',
  );
});
