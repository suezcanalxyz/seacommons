import test from 'node:test';
import assert from 'node:assert/strict';
import { playIncidentColor } from './incidentPalette.js';
import { incidentCollection } from './timeline.js';
test('PLAY palette matches LIVE canonical event semantics', () => {
  assert.equal(playIncidentColor({ domain: 'humanitarian', source: 'alarm_phone' }), '#ff3b3b');
  assert.equal(playIncidentColor({ domain: 'maritime', incident_type: 'impossible_speed' }), '#c084fc');
  assert.equal(playIncidentColor({ domain: 'maritime', incident_type: 'ais_gap' }), '#fb923c');
  assert.equal(playIncidentColor({ domain: 'maritime', incident_type: 'unable_to_manoeuvre' }), '#38bdf8');
  assert.equal(playIncidentColor({ domain: 'maritime', visual_category: 'sanctions' }), '#f472b6');
  assert.equal(playIncidentColor({ domain: 'maritime' }), '#76b7fa');
});
test('PLAY incident GeoJSON carries the exact canonical visual color', () => {
  const fc = incidentCollection([{ incident_id: 'integrity:1', domain: 'maritime', incident_type: 'position_jump', geometry: { type: 'Point', coordinates: [14, 35] } }]);
  assert.equal(fc.features[0].properties.visual_color, '#c084fc');
});
