const SCENARIO_SCHEMA = 'scenario/v2';
const ENVIRONMENT_SCHEMA = 'environment-snapshot/v1';

function finite(value, label) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`Invalid ${label}`);
  return parsed;
}

function isoUtc(value) {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) throw new Error('Invalid UTC timestamp');
  return parsed.toISOString();
}

function normalizedDirection(value) {
  return ((finite(value, 'direction') % 360) + 360) % 360;
}

function fnv1a(value) {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function frameFromWeather(weather, timeUtc) {
  return {
    time_utc: isoUtc(timeUtc),
    wind: {
      speed_m_s: Math.max(0, finite(weather.wind?.speed_ms, 'wind speed')),
      direction_deg: normalizedDirection(weather.wind?.direction_deg),
      direction_convention: 'from',
    },
    current: {
      speed_m_s: Math.max(0, finite(weather.ocean?.current_speed_ms, 'current speed')),
      direction_deg: normalizedDirection(weather.ocean?.current_dir_deg),
      direction_convention: 'to',
    },
    waves: {
      significant_height_m: Math.max(0, finite(weather.waves?.significant_height_m, 'wave height')),
      period_s: Math.max(0.1, finite(weather.waves?.period_s, 'wave period')),
      direction_deg: normalizedDirection(
        Number.isFinite(Number(weather.waves?.direction_deg))
          ? weather.waves.direction_deg
          : weather.wind?.direction_deg,
      ),
      direction_convention: 'from',
    },
  };
}

export function buildEnvironmentSnapshot(weather, lat, lon) {
  if (!weather) throw new Error('Live environmental feed unavailable');
  const origin = {
    lat: finite(lat, 'latitude'),
    lon: finite(lon, 'longitude'),
  };
  const forecastFrames = Array.isArray(weather.forecast_frames)
    ? weather.forecast_frames
    : [];
  const rawFrames = forecastFrames.length
    ? forecastFrames
    : [frameFromWeather(weather, weather.timestamp_utc || new Date())];
  const frames = rawFrames.map((frame) => ({
    time_utc: isoUtc(frame.time_utc),
    wind: {
      speed_m_s: Math.max(0, finite(frame.wind?.speed_m_s, 'wind speed')),
      direction_deg: normalizedDirection(frame.wind?.direction_deg),
      direction_convention: 'from',
    },
    current: {
      speed_m_s: Math.max(0, finite(frame.current?.speed_m_s, 'current speed')),
      direction_deg: normalizedDirection(frame.current?.direction_deg),
      direction_convention: 'to',
    },
    waves: {
      significant_height_m: Math.max(0, finite(frame.waves?.significant_height_m, 'wave height')),
      period_s: Math.max(0.1, finite(frame.waves?.period_s, 'wave period')),
      direction_deg: normalizedDirection(frame.waves?.direction_deg),
      direction_convention: 'from',
    },
  })).sort((left, right) => Date.parse(left.time_utc) - Date.parse(right.time_utc));

  if (!frames.length) throw new Error('Environmental feed returned no usable frames');
  const identity = JSON.stringify({ origin, source: weather.source, frames });
  return {
    schema_version: ENVIRONMENT_SCHEMA,
    snapshot_id: `env_${fnv1a(identity)}`,
    generated_at: new Date().toISOString(),
    observed_at: isoUtc(weather.timestamp_utc || frames[0].time_utc),
    origin,
    crs: 'EPSG:4326',
    sources: [{
      provider: 'Open-Meteo',
      product: 'weather + marine best match',
      retrieved_at: new Date().toISOString(),
      attribution: weather.source || 'Open-Meteo weather and marine APIs',
    }],
    frames,
  };
}

export function createScenario({
  scenarioId,
  lat,
  lon,
  observedAt,
  scenarioType,
  vesselType,
  persons,
  riskLevel,
  environmentSnapshot,
  simulationResult,
}) {
  const createdAt = new Date().toISOString();
  if (!scenarioId) throw new Error('scenario_id is required');
  if (environmentSnapshot?.schema_version !== ENVIRONMENT_SCHEMA) {
    throw new Error('environment-snapshot/v1 is required');
  }
  return {
    schema_version: SCENARIO_SCHEMA,
    scenario_id: String(scenarioId),
    created_at: createdAt,
    updated_at: createdAt,
    observed_at: isoUtc(observedAt),
    origin: {
      type: 'Point',
      coordinates: [finite(lon, 'longitude'), finite(lat, 'latitude')],
      crs: 'EPSG:4326',
    },
    subject: {
      kind: vesselType || 'unknown',
      persons: Math.max(1, Math.round(finite(persons, 'persons'))),
      anonymous: true,
    },
    classification: {
      scenario_type: scenarioType || 'distress',
      risk_level: riskLevel || 'medium',
    },
    environment_snapshot: environmentSnapshot,
    simulation: {
      engine: simulationResult.diagnostics.engine,
      engine_version: simulationResult.diagnostics.engine_version,
      status: 'completed',
      computed_at: simulationResult.diagnostics.computed_at,
      input_hash: `${environmentSnapshot.snapshot_id}:${simulationResult.diagnostics.seed}`,
      seed: simulationResult.diagnostics.seed,
      live_feed: true,
      operational_use: false,
      products: {
        drift_geojson: simulationResult.geojson,
      },
    },
    features: [],
    evidence: [],
    rendering: {
      preferred_renderer: 'cesium-web',
      compatible_renderers: ['cesium-web', 'unreal-pixel-streaming'],
    },
  };
}

export const CONTRACT_VERSIONS = Object.freeze({
  scenario: SCENARIO_SCHEMA,
  environment: ENVIRONMENT_SCHEMA,
});
