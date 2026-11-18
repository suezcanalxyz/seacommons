import test from 'node:test';
import assert from 'node:assert/strict';
import { radioFeature, liveActiveReceiverMarkers, isMediterraneanReceiver } from './radioMap.js';

test('a DSC message with no valid published position remains readable without a map marker', () => {
  for (const coords of [[null, null], ['', ''], [100, 16], [0, 0]]) {
    const feature = radioFeature({ observation_id: 'dsc-test', latitude: coords[0], longitude: coords[1] }, 'radio_message');
    assert.equal(feature.geometry, null);
    assert.equal(feature.properties.observation_id, 'dsc-test');
  }
});

test('valid published DSC and receiver positions preserve GeoJSON coordinate order', () => {
  for (const type of ['radio_receiver', 'radio_message']) {
    const feature = radioFeature({ latitude: 35, longitude: 14, frequency_hz: 2187500, listen_available: true }, type);
    assert.deepEqual(feature.geometry, { type: 'Point', coordinates: [14, 35] });
    assert.equal(feature.properties.radio_type, type);
    assert.equal(feature.properties.frequency_hz, 2187500);
    assert.equal(feature.properties.listen_available, true);
  }
});

test('active receiver symbols require a fresh mesh and actual geolocation', () => {
  const receivers = [
    { receiver_id: 'catania', active: true, latitude: 37.5, longitude: 15.09 },
    { receiver_id: 'mallorca', active: false, latitude: 39.8, longitude: 3.1 },
    { receiver_id: 'missing', active: true, latitude: null, longitude: null },
  ];
  assert.deepEqual(liveActiveReceiverMarkers({ fresh: false, receivers }), []);
  const active = liveActiveReceiverMarkers({ fresh: true, receivers });
  assert.equal(active.length, 1);
  assert.equal(active[0].properties.receiver_id, 'catania');
  assert.deepEqual(active[0].geometry.coordinates, [15.09, 37.5]);
  assert.deepEqual(liveActiveReceiverMarkers({ fresh: true, receivers: [] }), []);
});

test('Mediterranean LIVE map excludes unrelated northern/inland RF relay sites', () => {
  const receivers = [
    { receiver_id: 'zakynthos_hf_monitor', active: true, latitude: 37.783, longitude: 20.896 },
    { receiver_id: 'cagliari_hf_monitor', active: true, latitude: 39.22, longitude: 9.12 },
    { receiver_id: 'cassine_hf_monitor', active: true, latitude: 44.778, longitude: 8.531 },
    { receiver_id: 'heimiswil_hf_monitor', active: true, latitude: 47.057, longitude: 7.648 },
    { receiver_id: 'german_hf_relay', active: true, latitude: 50.11, longitude: 8.68 },
  ];
  assert.equal(isMediterraneanReceiver(receivers[0]), true);
  assert.equal(isMediterraneanReceiver(receivers[2]), false);
  assert.deepEqual(liveActiveReceiverMarkers({ fresh: true, receivers }).map((f) => f.properties.receiver_id),
    ['zakynthos_hf_monitor', 'cagliari_hf_monitor']);
  assert.equal(liveActiveReceiverMarkers({ fresh: false, receivers }).length, 0);
});
