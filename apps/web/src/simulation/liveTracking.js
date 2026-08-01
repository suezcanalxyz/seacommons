const EMPTY_COLLECTION = Object.freeze({ type: 'FeatureCollection', features: [] });

function eventId(feature) {
  return String(feature?.properties?.id || feature?.id || '').replace(/^intel:/, '');
}

function parsedTime(value) {
  const milliseconds = Date.parse(value);
  return Number.isFinite(milliseconds) ? milliseconds : null;
}

export function liveTrackingCandidates(events, now = new Date(), maxAgeHours = 48) {
  const currentMs = now instanceof Date ? now.getTime() : Number(now);
  return (Array.isArray(events) ? events : []).filter((feature) => {
    const properties = feature?.properties || {};
    const coordinates = feature?.geometry?.coordinates;
    const observedMs = parsedTime(properties.timestamp_utc);
    const usableCoordinate = [
      'post_text', 'media_ocr_consensus', 'media_ocr_text', 'relative_place_offset',
    ]
      .includes(properties.coordinate_source);
    return properties.source === 'Alarm Phone'
      && (properties.kind === 'distress' || properties.tier === 'operational')
      && properties.incident_status !== 'resolved'
      && usableCoordinate
      && Array.isArray(coordinates)
      && coordinates.length >= 2
      && coordinates.slice(0, 2).every((value) => Number.isFinite(Number(value)))
      && observedMs !== null
      && currentMs >= observedMs
      && currentMs - observedMs <= maxAgeHours * 3_600_000;
  });
}

export function decorateLiveTracking(result, signal) {
  const properties = signal?.properties || {};
  const id = eventId(signal);
  return {
    type: 'FeatureCollection',
    features: (result?.geojson?.features || []).map((feature) => ({
      ...feature,
      properties: {
        ...(feature.properties || {}),
        intel_event_id: id,
        intel_title: String(properties.title || 'Alarm Phone signal').slice(0, 80),
        intel_source: String(properties.source || 'Alarm Phone').slice(0, 64),
        intel_severity: properties.severity || 'high',
        auto_drift: true,
        publication_status: 'published',
        trajectory_kind: 'model_forecast',
        observed_track: false,
        verification_status: 'modelled_live_fields',
        operational_use: false,
      },
    })),
  };
}

export function currentEstimateFeature(trajectory, eventTimestamp, now = new Date()) {
  const coordinates = trajectory?.geometry?.coordinates || [];
  const timestamps = trajectory?.properties?.timestamps_utc || [];
  if (coordinates.length < 2 || timestamps.length !== coordinates.length) return null;
  const times = timestamps.map(parsedTime);
  if (times.some((value) => value === null)) return null;
  const nowMs = now instanceof Date ? now.getTime() : Number(now);
  const eventMs = parsedTime(eventTimestamp);
  if (!Number.isFinite(nowMs) || eventMs === null) return null;

  let coordinate;
  let state;
  if (nowMs <= times[0]) {
    coordinate = coordinates[0];
    state = 'before_model_start';
  } else if (nowMs >= times.at(-1)) {
    coordinate = coordinates.at(-1);
    state = 'model_horizon_reached';
  } else {
    const upper = times.findIndex((value) => value >= nowMs);
    const lower = upper - 1;
    const ratio = (nowMs - times[lower]) / Math.max(1, times[upper] - times[lower]);
    coordinate = [
      Number(coordinates[lower][0])
        + (Number(coordinates[upper][0]) - Number(coordinates[lower][0])) * ratio,
      Number(coordinates[lower][1])
        + (Number(coordinates[upper][1]) - Number(coordinates[lower][1])) * ratio,
    ];
    state = 'interpolated';
  }
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: coordinate.slice(0, 2) },
    properties: {
      ...(trajectory.properties || {}),
      type: 'current_estimate',
      elapsed_hours: Math.round(Math.max(0, nowMs - eventMs) / 36_000) / 100,
      estimate_time_utc: new Date(nowMs).toISOString(),
      trajectory_state: state,
    },
  };
}

export function mergeLiveDrifts(serverCollection, browserCollection, events, now = new Date()) {
  const serverFeatures = serverCollection?.features || [];
  const browserFeatures = browserCollection?.features || [];
  const serverTrajectoryIds = new Set(
    serverFeatures
      .filter((feature) => feature?.geometry?.type === 'LineString')
      .map((feature) => String(feature.properties?.intel_event_id || '').replace(/^intel:/, '')),
  );
  const selectedBrowser = browserFeatures.filter(
    (feature) => !serverTrajectoryIds.has(
      String(feature.properties?.intel_event_id || '').replace(/^intel:/, ''),
    ),
  );
  const withoutEstimates = [...serverFeatures, ...selectedBrowser].filter(
    (feature) => feature?.properties?.type !== 'current_estimate',
  );
  const timestampById = new Map(
    (Array.isArray(events) ? events : []).map((feature) => [
      eventId(feature),
      feature?.properties?.timestamp_utc,
    ]),
  );
  const estimates = withoutEstimates
    .filter((feature) => feature?.geometry?.type === 'LineString')
    .map((trajectory) => currentEstimateFeature(
      trajectory,
      timestampById.get(String(trajectory.properties?.intel_event_id || '').replace(/^intel:/, '')),
      now,
    ))
    .filter(Boolean);
  return {
    ...EMPTY_COLLECTION,
    features: [...withoutEstimates, ...estimates],
  };
}
