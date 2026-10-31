// Staging-only public taxonomy regression. No production requests or deployment.
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  classifyEventVisual,
  signalCategoryOf,
  EVENT_VISUAL_CATEGORIES,
} from './categories.js';

test('canonical maritime attack is coral and distinct from SAR and piracy', () => {
  const attack = classifyEventVisual({ incident_type: 'maritime_attack' });
  const sar = classifyEventVisual({ source: 'Alarm Phone', type: 'distress' });
  const piracy = classifyEventVisual({ maritime_domain: 'piracy' });
  assert.equal(attack.key, 'maritime_attack');
  assert.equal(attack.color, '#ff6b35');
  assert.notEqual(attack.color, sar.color);
  assert.notEqual(attack.color, piracy.color);
  assert.equal(signalCategoryOf({ incident_type: 'maritime_attack' }), 'maritime_attack');
  assert.ok(EVENT_VISUAL_CATEGORIES.some((entry) => entry.key === 'maritime_attack'));
});

test('AIS gap and sudden stop do not become attack markers', () => {
  for (const props of [
    { type: 'ais_anomaly', anomaly_type: 'ais_gap' },
    { type: 'ais_anomaly', anomaly_type: 'stationary_anomaly' },
    { type: 'news', title: 'Unconfirmed attack on ship' },
  ]) {
    assert.notEqual(classifyEventVisual(props).key, 'maritime_attack');
    assert.notEqual(signalCategoryOf(props), 'maritime_attack');
  }
});

test('armed approach without firing is not an attack marker', () => {
  const props = {
    type: 'news',
    source: 'MSCIO',
    title: '160/26 suspicious approach with armed skiff, no shots fired',
  };
  assert.notEqual(classifyEventVisual(props).key, 'maritime_attack');
  assert.notEqual(signalCategoryOf(props), 'maritime_attack');
});

test('Alarm Phone source remains humanitarian red even with conflicting attack metadata', () => {
  const result = classifyEventVisual({
    source: 'Alarm Phone',
    visual_category: 'maritime_attack',
    incident_type: 'maritime_attack',
  });
  assert.equal(result.key, 'humanitarian_alarm_phone');
  assert.equal(result.color, '#ff3b3b');
});

test('untrusted episode_family in raw event cannot turn into an attack', () => {
  const result = classifyEventVisual({ episode_family: 'attack_episode', type: 'news' });
  assert.notEqual(result.key, 'maritime_attack');
});
