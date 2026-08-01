function subjectKind(kind) {
  if (['rubber_boat', 'life_raft', 'raft'].includes(kind)) return 'raft';
  if (['person', 'person_in_water', 'piw'].includes(kind)) return 'person_in_water';
  if (!kind || kind === 'unknown') return 'unknown';
  return 'vessel';
}

export function scenarioToDriftScene(scenario) {
  if (scenario?.schema_version !== 'scenario/v2') throw new Error('scenario/v2 is required');
  const geojson = scenario.simulation?.products?.drift_geojson;
  const trajectory = geojson?.features?.find((feature) => feature.geometry?.type === 'LineString');
  if (!trajectory) throw new Error('Scenario has no drift trajectory');
  const times = trajectory.properties?.timestamps_utc || [];
  const positions = trajectory.geometry.coordinates.map((coordinates, index) => ({
    time: times[index] || new Date(Date.parse(scenario.observed_at) + index * 3_600_000).toISOString(),
    coordinates: [Number(coordinates[0]), Number(coordinates[1]), Number(coordinates[2]) || 0],
  }));
  const frame = scenario.environment_snapshot.frames[0];
  return {
    schema_version: 'drift-scene/v1',
    scenario_id: scenario.scenario_id,
    generated_at: scenario.updated_at,
    simulation: {
      engine: 'browser-live-fields',
      status: 'model-estimate',
      authoritative_for: ['none'],
      model_version: scenario.simulation.engine_version,
    },
    subject: {
      kind: subjectKind(scenario.subject.kind),
      persons: scenario.subject.persons,
      anonymous: true,
    },
    environment: {
      observed_at: scenario.environment_snapshot.observed_at,
      wind: { ...frame.wind, source: scenario.environment_snapshot.sources[0]?.attribution || 'live feed' },
      current: { ...frame.current, source: scenario.environment_snapshot.sources[0]?.attribution || 'live feed' },
      waves: {
        ...frame.waves,
        direction_source: 'directional-wave-product',
      },
    },
    trajectory: { crs: 'EPSG:4326', positions },
    uncertainty: {
      format: 'geojson-feature-list',
      features: geojson.features.filter((feature) => feature.geometry?.type === 'Polygon'),
    },
    rendering: {
      people_per_cube: Math.max(1, Math.ceil(scenario.subject.persons / 24)),
      vertical_motion_physical: false,
      interpolation: 'sampled-position',
    },
  };
}

export function pixelStreamingEnvelope(scenario) {
  return { type: 'seacommons.scene', payload: scenarioToDriftScene(scenario) };
}
