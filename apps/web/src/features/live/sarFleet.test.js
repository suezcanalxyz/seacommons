import test from 'node:test';
import assert from 'node:assert/strict';

import { fleetGroups, fleetStatus } from './sarFleet.js';

const NOW = Date.parse('2026-09-01T12:00:00Z');

const feat = (props, coords = null) => ({
  type: 'Feature',
  geometry: coords ? { type: 'Point', coordinates: coords } : null,
  properties: props,
});

test('a fresh AIS fix is live, an old one stale, a very old / null one offline', () => {
  assert.equal(fleetStatus(feat({ last_seen: '2026-09-01T11:55:00Z' }, [14, 35]), NOW), 'live');
  assert.equal(fleetStatus(feat({ last_seen: '2026-09-01T11:20:00Z' }, [14, 35]), NOW), 'stale');
  assert.equal(fleetStatus(feat({ last_seen: '2026-09-01T09:00:00Z' }, [14, 35]), NOW), 'offline');
  assert.equal(fleetStatus(feat({ ais_status: 'offline' }), NOW), 'offline');
});

test('an unverified radio identity is flagged, never given a live badge', () => {
  assert.equal(
    fleetStatus(feat({ identity_status: 'unverified', last_seen: '2026-09-01T11:59:00Z' }, [14, 35]), NOW),
    'unverified-identity',
  );
});

test('groups split civil NGO from state SAR and keep offline vessels', () => {
  const { civil, state } = fleetGroups([
    feat({ mmsi: '1', ship_name: 'Ocean Viking', org: 'SOS MEDITERRANEE', operator_type: 'civil_ngo', last_seen: '2026-09-01T11:58:00Z' }, [14, 35]),
    feat({ mmsi: '2', ship_name: 'Humanity 1', org: 'SOS Humanity', operator_type: 'civil_ngo', ais_status: 'offline' }),
    feat({ mmsi: '3', ship_name: 'CP 234', org: 'Guardia Costiera', operator_type: 'state_authority', ais_status: 'offline' }),
  ], NOW);

  assert.equal(civil.length, 2);
  assert.equal(state.length, 1);
  // AIS-offline vessels are still listed, just not positioned.
  assert.deepEqual(civil.map((a) => a.name), ['Ocean Viking', 'Humanity 1']);
  assert.equal(civil[1].positioned, false);
  assert.equal(civil[0].status, 'live');
});
