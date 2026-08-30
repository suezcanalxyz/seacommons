import assert from 'node:assert/strict';
import test from 'node:test';

import { classifyEventVisual, eventAnomalyLabel } from '../intel/categories.js';

test('classifies unable-to-manoeuvre reports as red navigation casualties', () => {
  const event = {
    title: 'Vessel unable to manoeuvre — AGATE',
    severity: 'medium',
    anomaly_types: ['not_under_command'],
    latest_nav_status: 2,
  };
  assert.equal(classifyEventVisual(event).key, 'navigation_casualty');
  assert.equal(classifyEventVisual(event).color, '#ff4d5e');
  assert.equal(eventAnomalyLabel(event), 'unable to manoeuvre');
});

test('explicit anomaly type takes precedence over a vessel latest navigation status', () => {
  assert.equal(classifyEventVisual({
    anomaly_types: ['circle_spoof'],
    latest_nav_status: 3,
    severity: 'high',
  }).key, 'spoofing');
  assert.equal(classifyEventVisual({
    anomaly_types: ['gap'],
    latest_nav_status: 2,
    severity: 'medium',
  }).key, 'ais_gap');
});

test('keeps operational categories visually distinct', () => {
  const cases = [
    [{ anomaly_types: ['loitering'] }, 'loitering'],
    [{ anomaly_types: ['rendezvous'] }, 'rendezvous'],
    [{ sanctions_matched: true }, 'sanctions'],
    [{ infrastructure: { kind: 'pipeline' } }, 'infrastructure'],
    [{ anomaly_types: ['mmsi_mismatch'] }, 'identity'],
  ];
  const colors = new Set();
  for (const [event, expected] of cases) {
    const category = classifyEventVisual(event);
    assert.equal(category.key, expected);
    colors.add(category.color);
  }
  assert.equal(colors.size, cases.length);
});
