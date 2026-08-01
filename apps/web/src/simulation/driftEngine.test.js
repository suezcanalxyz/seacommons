import assert from 'node:assert/strict';
import test from 'node:test';

import { buildEnvironmentSnapshot, createScenario } from './contracts.js';
import { computeDrift } from './driftEngine.js';
import { pixelStreamingEnvelope, scenarioToDriftScene } from './sceneAdapter.js';

function weather() {
  return {
    timestamp_utc: '2026-08-01T10:00:00Z',
    source: 'test live fields',
    wind: { speed_ms: 6, direction_deg: 270 },
    ocean: { current_speed_ms: 0.25, current_dir_deg: 90 },
    waves: { significant_height_m: 1, period_s: 6, direction_deg: 270 },
    forecast_frames: Array.from({ length: 25 }, (_, hour) => ({
      time_utc: new Date(Date.parse('2026-08-01T10:00:00Z') + hour * 3_600_000).toISOString(),
      wind: { speed_m_s: 6 + hour * 0.02, direction_deg: 270 },
      current: { speed_m_s: 0.25, direction_deg: 90 },
      waves: { significant_height_m: 1, period_s: 6, direction_deg: 270 },
    })),
  };
}

function input() {
  const snapshot = buildEnvironmentSnapshot(weather(), 37.5, 15.1);
  return {
    scenario: {
      scenario_id: 'scenario-test-001',
      observed_at: '2026-08-01T10:00:00Z',
      origin: { lat: 37.5, lon: 15.1 },
      subject: { kind: 'life_raft', persons: 4 },
    },
    environmentSnapshot: snapshot,
    options: { duration_hours: 24, particles: 64, seed: 42 },
  };
}

test('browser drift is deterministic and uses time-varying live frames', () => {
  const first = computeDrift(input());
  const second = computeDrift(input());
  assert.deepEqual(first.geojson, second.geojson);
  const trajectory = first.geojson.features[0];
  assert.equal(trajectory.geometry.type, 'LineString');
  assert.equal(trajectory.geometry.coordinates.length, 25);
  assert.equal(trajectory.properties.timestamps_utc.length, 25);
  assert.equal(trajectory.properties.speed_ms.length, 25);
  assert.equal(trajectory.properties.engine, 'seacommons-browser');
  assert.equal(trajectory.properties.live_feed, true);
  assert.ok(trajectory.geometry.coordinates.at(-1)[0] > 15.1);
  assert.deepEqual(
    first.geojson.features.filter((feature) => feature.geometry.type === 'Polygon')
      .map((feature) => feature.properties.horizon_h),
    [6, 12, 24],
  );
});

test('scenario/v2 keeps the forcing snapshot and renderer compatibility', () => {
  const driftInput = input();
  const result = computeDrift(driftInput);
  const scenario = createScenario({
    scenarioId: driftInput.scenario.scenario_id,
    lat: 37.5,
    lon: 15.1,
    observedAt: driftInput.scenario.observed_at,
    scenarioType: 'distress',
    vesselType: 'life_raft',
    persons: 4,
    riskLevel: 'high',
    environmentSnapshot: driftInput.environmentSnapshot,
    simulationResult: result,
  });
  assert.equal(scenario.schema_version, 'scenario/v2');
  assert.equal(scenario.environment_snapshot.schema_version, 'environment-snapshot/v1');
  assert.equal(scenario.simulation.engine, 'seacommons-browser');
  assert.deepEqual(scenario.rendering.compatible_renderers, ['cesium-web', 'unreal-pixel-streaming']);
  assert.deepEqual(scenario.features, []);
  assert.deepEqual(scenario.evidence, []);
});

test('missing environmental forcing fails instead of drawing a fake path', () => {
  assert.throws(
    () => computeDrift({ scenario: input().scenario, environmentSnapshot: null }),
    /environment-snapshot\/v1/,
  );
});

test('renderer adapter gives Unreal and Cesium the same sampled path', () => {
  const driftInput = input();
  const result = computeDrift(driftInput);
  const scenario = createScenario({
    scenarioId: driftInput.scenario.scenario_id,
    lat: 37.5,
    lon: 15.1,
    observedAt: driftInput.scenario.observed_at,
    scenarioType: 'distress',
    vesselType: 'life_raft',
    persons: 4,
    riskLevel: 'high',
    environmentSnapshot: driftInput.environmentSnapshot,
    simulationResult: result,
  });
  const scene = scenarioToDriftScene(scenario);
  assert.equal(scene.schema_version, 'drift-scene/v1');
  assert.equal(scene.simulation.engine, 'browser-live-fields');
  assert.deepEqual(
    scene.trajectory.positions.map((position) => position.coordinates.slice(0, 2)),
    result.geojson.features[0].geometry.coordinates,
  );
  assert.equal(pixelStreamingEnvelope(scenario).type, 'seacommons.scene');
});
