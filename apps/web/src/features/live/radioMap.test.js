import test from 'node:test';
import assert from 'node:assert/strict';
import { radioFeature } from './radioMap.js';

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
