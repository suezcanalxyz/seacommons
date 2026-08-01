const EARTH_METERS_PER_DEGREE = 111_320;
const ENGINE_VERSION = '0.1.0';

const LEEWAY = Object.freeze({
  person_in_water: 0.015,
  rubber_boat: 0.040,
  life_raft: 0.035,
  fishing_vessel: 0.025,
  wooden_boat: 0.030,
  sailboat: 0.030,
  motorboat: 0.025,
  container_ship: 0.012,
  unknown: 0.030,
});

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

function vectorTo(speed, directionDeg) {
  const angle = Number(directionDeg) * Math.PI / 180;
  return { east: Number(speed) * Math.sin(angle), north: Number(speed) * Math.cos(angle) };
}

function vectorFrom(speed, directionDeg) {
  return vectorTo(speed, Number(directionDeg) + 180);
}

function addVector(...vectors) {
  return vectors.reduce((sum, vector) => ({
    east: sum.east + vector.east,
    north: sum.north + vector.north,
  }), { east: 0, north: 0 });
}

function scaleVector(vector, factor) {
  return { east: vector.east * factor, north: vector.north * factor };
}

function frameVectors(frame) {
  const wind = vectorFrom(frame.wind.speed_m_s, frame.wind.direction_deg);
  const current = vectorTo(frame.current.speed_m_s, frame.current.direction_deg);
  const waves = vectorFrom(1, frame.waves.direction_deg);
  // Deep-water surface Stokes estimate. This remains deliberately bounded
  // because significant wave height is not a full directional wave spectrum.
  const stokesSpeed = clamp(
    Math.PI ** 3 * frame.waves.significant_height_m ** 2
      / (9.80665 * frame.waves.period_s ** 3),
    0,
    0.35,
  );
  return { wind, current, stokes: scaleVector(waves, stokesSpeed) };
}

function lerp(left, right, ratio) {
  return left + (right - left) * ratio;
}

function interpolateEnvironment(frames, timeMs) {
  if (frames.length === 1 || timeMs <= Date.parse(frames[0].time_utc)) return frameVectors(frames[0]);
  const last = frames.at(-1);
  if (timeMs >= Date.parse(last.time_utc)) return frameVectors(last);
  let upperIndex = 1;
  while (upperIndex < frames.length && Date.parse(frames[upperIndex].time_utc) < timeMs) upperIndex += 1;
  const lower = frames[upperIndex - 1];
  const upper = frames[upperIndex];
  const lowerTime = Date.parse(lower.time_utc);
  const ratio = (timeMs - lowerTime) / Math.max(1, Date.parse(upper.time_utc) - lowerTime);
  const left = frameVectors(lower);
  const right = frameVectors(upper);
  return {
    wind: { east: lerp(left.wind.east, right.wind.east, ratio), north: lerp(left.wind.north, right.wind.north, ratio) },
    current: { east: lerp(left.current.east, right.current.east, ratio), north: lerp(left.current.north, right.current.north, ratio) },
    stokes: { east: lerp(left.stokes.east, right.stokes.east, ratio), north: lerp(left.stokes.north, right.stokes.north, ratio) },
  };
}

function velocity(environment, leewayFactor, currentFactor = 1, crosswindFactor = 0) {
  const downwind = scaleVector(environment.wind, leewayFactor);
  const crosswind = {
    east: environment.wind.north * leewayFactor * crosswindFactor,
    north: -environment.wind.east * leewayFactor * crosswindFactor,
  };
  return addVector(scaleVector(environment.current, currentFactor), downwind, crosswind, environment.stokes);
}

function displace(position, movement, seconds) {
  const cosLat = Math.max(0.12, Math.cos(position.lat * Math.PI / 180));
  return {
    lat: clamp(position.lat + movement.north * seconds / EARTH_METERS_PER_DEGREE, -89.999, 89.999),
    lon: position.lon + movement.east * seconds / (EARTH_METERS_PER_DEGREE * cosLat),
  };
}

function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state += 0x6D2B79F5;
    let value = state;
    value = Math.imul(value ^ value >>> 15, value | 1);
    value ^= value + Math.imul(value ^ value >>> 7, value | 61);
    return ((value ^ value >>> 14) >>> 0) / 4_294_967_296;
  };
}

function gaussian(random) {
  const left = Math.max(Number.EPSILON, random());
  const right = Math.max(Number.EPSILON, random());
  return Math.sqrt(-2 * Math.log(left)) * Math.cos(2 * Math.PI * right);
}

function convexHull(points) {
  const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (sorted.length <= 2) return sorted;
  const cross = (origin, left, right) => (
    (left[0] - origin[0]) * (right[1] - origin[1])
      - (left[1] - origin[1]) * (right[0] - origin[0])
  );
  const lower = [];
  for (const point of sorted) {
    while (lower.length >= 2 && cross(lower.at(-2), lower.at(-1), point) <= 0) lower.pop();
    lower.push(point);
  }
  const upper = [];
  for (const point of [...sorted].reverse()) {
    while (upper.length >= 2 && cross(upper.at(-2), upper.at(-1), point) <= 0) upper.pop();
    upper.push(point);
  }
  return [...lower.slice(0, -1), ...upper.slice(0, -1)];
}

function distanceMeters(left, right) {
  const meanLat = (left.lat + right.lat) * Math.PI / 360;
  const east = (right.lon - left.lon) * EARTH_METERS_PER_DEGREE * Math.cos(meanLat);
  const north = (right.lat - left.lat) * EARTH_METERS_PER_DEGREE;
  return Math.hypot(east, north);
}

function coneFeature(particles, center, horizonHours, snapshotId) {
  const points = particles.map((particle) => [particle.lon, particle.lat]);
  const hull = convexHull(points);
  const ring = hull.length >= 3 ? [...hull, hull[0]] : points;
  const radius = Math.max(...particles.map((particle) => distanceMeters(center, particle)), 0);
  return {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [ring] },
    properties: {
      type: `cone_${horizonHours}h`,
      horizon_h: horizonHours,
      radius_m: Math.round(radius),
      particles: particles.length,
      engine: 'seacommons-browser',
      engine_version: ENGINE_VERSION,
      environment_snapshot_id: snapshotId,
      live_feed: true,
      operational_use: false,
    },
  };
}

function scenarioSeed(scenario) {
  const source = `${scenario.scenario_id}:${scenario.origin.lat}:${scenario.origin.lon}`;
  let seed = 2166136261;
  for (let index = 0; index < source.length; index += 1) {
    seed ^= source.charCodeAt(index);
    seed = Math.imul(seed, 16777619);
  }
  return seed >>> 0;
}

export function computeDrift({ scenario, environmentSnapshot, options = {} }, onProgress = () => {}) {
  if (environmentSnapshot?.schema_version !== 'environment-snapshot/v1') {
    throw new Error('A valid environment-snapshot/v1 is required');
  }
  const frames = environmentSnapshot.frames || [];
  if (!frames.length) throw new Error('Environmental snapshot contains no forcing frames');
  const origin = { lat: Number(scenario.origin.lat), lon: Number(scenario.origin.lon) };
  if (!Number.isFinite(origin.lat) || !Number.isFinite(origin.lon)) throw new Error('Invalid scenario origin');
  const durationHours = clamp(Number(options.duration_hours) || 24, 1, 72);
  const particleCount = Math.round(clamp(Number(options.particles) || 128, 32, 512));
  const stepSeconds = 900;
  const totalSteps = Math.ceil(durationHours * 3600 / stepSeconds);
  const outputEvery = Math.max(1, Math.round(3600 / stepSeconds));
  const startMs = Date.parse(scenario.observed_at || environmentSnapshot.observed_at);
  if (!Number.isFinite(startMs)) throw new Error('Invalid scenario observation time');
  const vesselType = scenario.subject?.kind || 'unknown';
  const baseLeeway = LEEWAY[vesselType] ?? LEEWAY.unknown;
  const seed = Number.isInteger(options.seed) ? options.seed >>> 0 : scenarioSeed(scenario);
  const random = seededRandom(seed);
  let center = { ...origin };
  const particles = Array.from({ length: particleCount }, () => ({
    ...origin,
    leewayFactor: baseLeeway * clamp(1 + gaussian(random) * 0.18, 0.45, 1.65),
    currentFactor: clamp(1 + gaussian(random) * 0.12, 0.55, 1.45),
    crosswindFactor: clamp(gaussian(random) * 0.22, -0.65, 0.65),
  }));
  const coordinates = [[origin.lon, origin.lat]];
  const timestamps = [new Date(startMs).toISOString()];
  const speeds = [0];
  const particlesAtHorizon = new Map();
  const centerAtHorizon = new Map();

  for (let step = 1; step <= totalSteps; step += 1) {
    const midpointMs = startMs + (step - 0.5) * stepSeconds * 1000;
    const environment = interpolateEnvironment(frames, midpointMs);
    const centerVelocity = velocity(environment, baseLeeway);
    center = displace(center, centerVelocity, stepSeconds);
    for (const particle of particles) {
      const particleVelocity = velocity(
        environment,
        particle.leewayFactor,
        particle.currentFactor,
        particle.crosswindFactor,
      );
      // Horizontal diffusion represents unresolved sub-grid flow, not a fake
      // route. Its deterministic seed makes the same snapshot reproducible.
      particleVelocity.east += gaussian(random) * 0.018;
      particleVelocity.north += gaussian(random) * 0.018;
      const next = displace(particle, particleVelocity, stepSeconds);
      particle.lat = next.lat;
      particle.lon = next.lon;
    }
    if (step % outputEvery === 0 || step === totalSteps) {
      coordinates.push([center.lon, center.lat]);
      timestamps.push(new Date(startMs + step * stepSeconds * 1000).toISOString());
      speeds.push(Math.hypot(centerVelocity.east, centerVelocity.north));
    }
    const elapsedHours = step * stepSeconds / 3600;
    for (const horizon of [6, 12, 24]) {
      if (!particlesAtHorizon.has(horizon) && elapsedHours >= Math.min(horizon, durationHours)) {
        particlesAtHorizon.set(horizon, particles.map((particle) => ({ lat: particle.lat, lon: particle.lon })));
        centerAtHorizon.set(horizon, { ...center });
      }
    }
    if (step % 8 === 0 || step === totalSteps) onProgress(step / totalSteps);
  }

  const trajectory = {
    type: 'Feature',
    geometry: { type: 'LineString', coordinates },
    properties: {
      type: 'trajectory',
      timestamps_utc: timestamps,
      speed_ms: speeds,
      engine: 'seacommons-browser',
      engine_version: ENGINE_VERSION,
      model: 'time-varying current + leeway + bounded Stokes drift',
      environment_snapshot_id: environmentSnapshot.snapshot_id,
      live_feed: true,
      degraded: false,
      operational_use: false,
    },
  };
  const cones = [6, 12, 24]
    .filter((horizon) => particlesAtHorizon.has(horizon))
    .map((horizon) => coneFeature(
      particlesAtHorizon.get(horizon),
      centerAtHorizon.get(horizon),
      horizon,
      environmentSnapshot.snapshot_id,
    ));
  const impactPoint = {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: coordinates.at(-1) },
    properties: {
      type: 'impact_point',
      engine: 'seacommons-browser',
      environment_snapshot_id: environmentSnapshot.snapshot_id,
      live_feed: true,
      operational_use: false,
    },
  };
  return {
    geojson: { type: 'FeatureCollection', features: [trajectory, ...cones, impactPoint] },
    diagnostics: {
      engine: 'seacommons-browser',
      engine_version: ENGINE_VERSION,
      computed_at: new Date().toISOString(),
      seed,
      particles: particleCount,
      steps: totalSteps,
      forcing_frames: frames.length,
      duration_hours: durationHours,
    },
  };
}
