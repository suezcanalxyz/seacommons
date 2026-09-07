import test from 'node:test';
import assert from 'node:assert/strict';
import { vesselReportFeature, vesselMotionState } from './vesselVisual.js';

test('vesselMotionState distinguishes moving and stationary contacts', () => {
  assert.equal(vesselMotionState({ speed: 4.1 }), 'moving');
  assert.equal(vesselMotionState({ speed: 0.2 }), 'stationary');
  assert.equal(vesselMotionState({ speed: null }), 'unknown');
});

test('vesselReportFeature preserves the complete vessel name and report fields', () => {
  const feature = { type: 'Feature', geometry: { type: 'Point', coordinates: [15.3, 36.8] }, properties: { mmsi: '258479000', ship_name: 'OCEAN VIKING', speed: 0.6, course: 66.2, heading: 72 } };
  const report = vesselReportFeature(feature);
  assert.equal(report.properties.vessel_name, 'OCEAN VIKING');
  assert.equal(report.properties.title, 'OCEAN VIKING');
  assert.equal(report.properties.entity_kind, 'vessel');
  assert.equal(report.properties.latest_sog, 0.6);
  assert.equal(report.properties.latest_course, 66.2);
  assert.equal(report.properties.latest_heading, 72);
});
