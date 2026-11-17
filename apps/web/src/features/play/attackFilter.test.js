import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { isAttackIncident } from '../map/attackMarker.js';

test('attack filter only accepts explicitly classified attack events', () => {
  assert.equal(isAttackIncident({ incident_type: 'drone_attack' }), true);
  assert.equal(isAttackIncident({ attack_type: 'missile_strike' }), true);
  assert.equal(isAttackIncident({ incident_type: 'ais_gap', title: 'possible attack' }), false);
  assert.equal(isAttackIncident({ incident_type: 'position_integrity' }), false);
});

test('PLAY ATTACKS filter drives shared map, list and timeline case selection', async () => {
  const source = await readFile(new URL('./PlayTimeline.jsx', import.meta.url), 'utf8');
  assert.match(source, /archiveFilter === 'attacks'\) return isAttackIncident\(incident\)/);
  assert.match(source, /setArchiveFilter\('attacks'\)/);
  assert.match(source, /setIncidentTypeFilter\('all'\)/);
  assert.match(source, /incidentCollection\(filteredIncidents\)/);
  assert.match(source, /filteredIncidents\.slice\(0, visibleCaseLimit\)/);
});
