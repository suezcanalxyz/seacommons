import assert from 'node:assert/strict';
import test from 'node:test';

import {
    currentEstimateFeature,
    decorateLiveTracking,
    edgeSnapshotIsFresh,
    edgeSnapshotIsUsable,
    liveTrackingCandidates,
    mergeLiveDrifts,
} from './liveTracking.js';

const signal = {
  type: 'Feature',
  id: 'intel:x123',
  geometry: { type: 'Point', coordinates: [24.81, 34.79] },
  properties: {
    id: 'intel:x123',
    kind: 'distress',
    tier: 'operational',
    source: 'Alarm Phone',
    severity: 'high',
    title: '47 people south of Crete',
    timestamp_utc: '2026-08-01T09:00:00Z',
    incident_status: 'active',
    coordinate_source: 'relative_place_offset',
  },
};

const trajectory = {
  type: 'Feature',
  geometry: { type: 'LineString', coordinates: [[24.81, 34.79], [25.01, 34.89]] },
  properties: {
    type: 'trajectory',
    timestamps_utc: ['2026-08-01T09:00:00Z', '2026-08-01T11:00:00Z'],
  },
};

test('selects only recent active geolocated Alarm Phone distress signals', () => {
  const now = new Date('2026-08-01T10:00:00Z');
  assert.deepEqual(liveTrackingCandidates([signal], now), [signal]);
  assert.equal(liveTrackingCandidates([{ ...signal, geometry: null }], now).length, 0);
  assert.equal(liveTrackingCandidates([{
    ...signal,
    properties: { ...signal.properties, incident_lifecycle: 'resolved' },
  }], now).length, 0);
  assert.equal(liveTrackingCandidates([{
    ...signal,
    properties: { ...signal.properties, incident_lifecycle: 'archived' },
  }], now).length, 0);
  assert.equal(liveTrackingCandidates([{
    ...signal,
    properties: { ...signal.properties, incident_lifecycle: 'needs_review' },
  }], now).length, 0);
  assert.equal(liveTrackingCandidates([{
    ...signal,
    properties: { ...signal.properties, coordinate_source: 'place_centroid' },
  }], now).length, 0);
});

test('accepts only fresh edge snapshots', () => {
  const now = new Date('2026-08-06T14:00:00Z');
  assert.equal(edgeSnapshotIsFresh({ updated_at: '2026-08-06T13:59:00Z' }, now), true);
  assert.equal(edgeSnapshotIsFresh({ updated_at: '2026-08-06T13:50:00Z' }, now), false);
  assert.equal(edgeSnapshotIsFresh({ updated_at: null }, now), false);
});

test('keeps a quiet edge snapshot usable for its retention window', () => {
  const now = new Date('2026-08-06T14:00:00Z');
  const quiet = {
    schema: 'seacommons-live-snapshot-v1',
    updated_at: '2026-08-06T10:00:00Z',
    ttl_seconds: 8 * 24 * 60 * 60,
    events: [{ id: 'incident-1' }],
  };
  assert.equal(edgeSnapshotIsFresh(quiet, now), false);
  assert.equal(edgeSnapshotIsUsable(quiet, now), true);
  assert.equal(edgeSnapshotIsUsable({ ...quiet, updated_at: '2026-07-01T10:00:00Z' }, now), false);
  assert.equal(edgeSnapshotIsUsable({ ...quiet, schema: 'unknown' }, now), false);
});

test('interpolates a wall-clock estimate along the calculated trajectory', () => {
  const estimate = currentEstimateFeature(
    trajectory,
    signal.properties.timestamp_utc,
    new Date('2026-08-01T10:00:00Z'),
  );
  assert.deepEqual(estimate.geometry.coordinates, [24.91, 34.84]);
  assert.equal(estimate.properties.elapsed_hours, 1);
  assert.equal(estimate.properties.trajectory_state, 'interpolated');
});

test('decorates browser output and prefers a verified server trajectory when present', () => {
  const browser = decorateLiveTracking({ geojson: { features: [trajectory] } }, signal);
  assert.equal(browser.features[0].properties.intel_event_id, 'x123');
  assert.equal(browser.features[0].properties.verification_status, 'modelled_live_fields');
  const serverTrajectory = {
    ...trajectory,
    properties: { ...trajectory.properties, intel_event_id: 'x123', model: 'OpenDrift Leeway' },
  };
  const merged = mergeLiveDrifts(
    { type: 'FeatureCollection', features: [serverTrajectory] },
    browser,
    [signal],
    new Date('2026-08-01T10:00:00Z'),
  );
  assert.equal(merged.features.filter((feature) => feature.geometry.type === 'LineString').length, 1);
  assert.equal(merged.features[0].properties.model, 'OpenDrift Leeway');
  assert.equal(merged.features.at(-1).properties.type, 'current_estimate');
});

test('removes server and browser drifts as soon as an incident is resolved', () => {
  const browser = decorateLiveTracking({ geojson: { features: [trajectory] } }, signal);
  const resolvedSignal = {
    ...signal,
    properties: { ...signal.properties, incident_lifecycle: 'resolved' },
  };
  const merged = mergeLiveDrifts(
    { type: 'FeatureCollection', features: [{
      ...trajectory,
      properties: { ...trajectory.properties, intel_event_id: 'x123' },
    }] },
    browser,
    [resolvedSignal],
    new Date('2026-08-01T10:00:00Z'),
  );
  assert.deepEqual(merged.features, []);
});
