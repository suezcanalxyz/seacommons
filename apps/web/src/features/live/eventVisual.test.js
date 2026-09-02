import assert from 'node:assert/strict';
import test from 'node:test';

import { SIGNAL_CATEGORIES, aisTaxonomyGroup, classifyEventVisual, eventAnomalyLabel } from '../intel/categories.js';

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

test('Alarm Phone is always red — category/source role, never severity or lifecycle', () => {
  for (const lifecycle of ['active', 'needs_review', 'resolved', 'archived']) {
    for (const severity of ['low', 'medium', 'high', 'critical']) {
      const v = classifyEventVisual({
        source: 'Alarm Phone',
        incident_lifecycle: lifecycle,
        severity,
        humanitarian_case_type: 'distress',
      });
      assert.equal(v.key, 'humanitarian_alarm_phone');
      assert.equal(v.color, '#ff3b3b');
    }
  }
  // Land + region-only Alarm Phone stay red too.
  assert.equal(
    classifyEventVisual({ source: 'alarm_phone', humanitarian_case_type: 'land_humanitarian' }).color,
    '#ff3b3b',
  );
  assert.equal(
    classifyEventVisual({ source: 'alarm_phone', location_status: 'region_only' }).color,
    '#ff3b3b',
  );
  // A drift feature carrying the backend origin_category is red as well.
  assert.equal(
    classifyEventVisual({ origin_category: 'humanitarian_alarm_phone' }).key,
    'humanitarian_alarm_phone',
  );
});

test('classifyEventVisual never falls back to severity', () => {
  // A resolved, "critical" Alarm Phone must not go green or amber.
  const resolved = classifyEventVisual({
    source: 'Alarm Phone', incident_lifecycle: 'resolved', severity: 'critical',
  });
  assert.equal(resolved.color, '#ff3b3b');
  // A plain context signal with critical severity stays context, not casualty.
  assert.equal(classifyEventVisual({ type: 'news', severity: 'critical' }).key, 'context');
  // Severity 'medium' no longer means "needs_review".
  assert.notEqual(classifyEventVisual({ severity: 'medium' }).key, 'needs_review');
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

test('the specific AIS subtype is named, never "spike"', () => {
  assert.equal(eventAnomalyLabel({ anomaly_type: 'sudden_stop' }), 'sudden stop');
  assert.equal(eventAnomalyLabel({ anomaly_type: 'possible_rescue_cluster' }), 'possible vessel cluster');
  assert.equal(eventAnomalyLabel({ anomaly_type: 'coverage_gap' }), 'AIS coverage outage');
  assert.equal(eventAnomalyLabel({ anomaly_type: 'impossible_speed' }), 'impossible speed');
  assert.equal(eventAnomalyLabel({ type: 'ais_spike', anomaly_type: 'ngo_search_pattern' }), 'search pattern');
});

test('aisTaxonomyGroup splits vessel-status / behavioural-cue / signal-anomaly', () => {
  assert.equal(aisTaxonomyGroup('vessel_incident'), 'vessel_status');
  assert.equal(aisTaxonomyGroup('ais_spike'), 'behavioural_cue');
  assert.equal(aisTaxonomyGroup('ais_anomaly'), 'signal_anomaly');
  assert.equal(aisTaxonomyGroup('correlated_alert'), 'fused_alert');
  assert.equal(aisTaxonomyGroup('twitter'), null);
});

test('no SIGNAL_CATEGORIES legend row says "spike"', () => {
  for (const cat of SIGNAL_CATEGORIES) {
    assert.ok(!/spike/i.test(cat.label), cat.key);
    assert.ok(!/spike/i.test(cat.description || ''), cat.key);
  }
});
