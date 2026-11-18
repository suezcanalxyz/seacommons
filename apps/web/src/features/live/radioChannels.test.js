import test from 'node:test';
import assert from 'node:assert/strict';
import { MARITIME_RADIO_CHANNELS, monitoredRadioChannels, receiverNominalChannels } from './radioChannels.js';
import { mediterraneanReceiverMapMarkers } from './radioMap.js';

test('all audited maritime channel types are present without pretending to receive', () => {
  assert.equal(MARITIME_RADIO_CHANNELS.length, 11);
  assert.equal(MARITIME_RADIO_CHANNELS.filter((c) => c.family === 'dsc').length, 6);
  assert.equal(MARITIME_RADIO_CHANNELS.find((c) => c.frequency_hz === 156525000).decoder, 'not_supported');
  assert.equal(MARITIME_RADIO_CHANNELS.find((c) => c.frequency_hz === 4209500).decoder, 'not_configured');
  assert.ok(monitoredRadioChannels({ fresh: false, receivers: [
    { active: true, frequency_hz: 2187500 },
  ] }).every((c) => c.active_receivers === 0));
});

test('channel counts derive ONLY from active, fresh, tuned receiver runtime', () => {
  const rows = monitoredRadioChannels({ fresh: true, receivers: [
    { active: true, frequency_hz: 2187500 },
    { active: true, frequency_hz: 2187500 },
    { active: false, frequency_hz: 8414500 },
    { active: true, frequency_hz: null },
  ] });
  assert.equal(rows.find((x) => x.frequency_hz === 2187500).active_receivers, 2);
  assert.equal(rows.find((x) => x.frequency_hz === 8414500).active_receivers, 0);
  assert.equal(rows.find((x) => x.frequency_hz === 518000).state, 'not_monitored');
});

test('nominal equipment bands are not mistaken for connected channel streams', () => {
  const capabilities = [{ min_hz: 0, max_hz: 30000000, modes: ['usb', 'am'] }];
  const nominal = receiverNominalChannels({ capabilities });
  assert.equal(nominal.length, 9);
  assert.ok(nominal.includes('navtex-518'));
  assert.ok(!nominal.includes('vhf-dsc-70'));
});

test('map displays connected Mediterranean SDR plus unconnected catalogue and one research candidate', () => {
  const receivers = [
    { receiver_id: 'zakynthos_hf_monitor', station_label: 'Zante',
      active: true, frequency_hz: 2187500, latitude: 37.783, longitude: 20.896,
      capabilities: [{ min_hz: 0, max_hz: 30000000 }] },
    { receiver_id: 'cagliari_hf_monitor', station_label: 'Cagliari',
      active: false, state: 'eligible', latitude: 39.22, longitude: 9.12 },
    { receiver_id: 'heimiswil_hf_monitor', active: true, latitude: 47.057, longitude: 7.648 },
    { receiver_id: 'invalid', active: true, latitude: 35, longitude: null },
  ];
  const features = mediterraneanReceiverMapMarkers({ fresh: true, receivers });
  assert.deepEqual(features.map((f) => f.properties.receiver_id),
    ['zakynthos_hf_monitor', 'cagliari_hf_monitor', 'ea3hru_barcelona_research']);
  assert.equal(features[0].properties.station_status, 'receiving');
  assert.equal(features[1].properties.station_status, 'not_connected');
  assert.equal(features[2].properties.station_status, 'candidate');
  assert.equal(features[2].properties.active, false);
  assert.equal(mediterraneanReceiverMapMarkers({ fresh: false, receivers }).length, 0);
});
