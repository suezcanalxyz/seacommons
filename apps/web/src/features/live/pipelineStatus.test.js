import test from 'node:test';
import assert from 'node:assert/strict';

import { normalizePipelineSources, receiverChannelLabel } from './pipelineStatus.js';

test('normalizes unified acquisition families and keeps radio as provenance only', () => {
  const sources = normalizePipelineSources({ sources: [
    { family: 'ais', label: 'AIS', state: 'live', mode: 'legacy' },
    { family: 'radio', label: 'Radio', state: 'live', receivers: [{
      receiver_id: 'med_dsc', station_label: 'Mediterranean DSC', provider: 'kiwisdr',
      state: 'connected', channel_kind: 'dsc', frequency_hz: 2187500, mode: 'usb',
      last_observation_at: '2026-09-07T00:00:00Z', observations_received: 3,
      frontend_url: 'https://secret.example.org',
    }] },
  ] });
  assert.deepEqual(sources.map((source) => source.family), ['ais', 'radio']);
  assert.equal(sources[1].receivers[0].station_label, 'Mediterranean DSC');
  assert.equal('frontend_url' in sources[1].receivers[0], false);
});

test('receiver channel label is operational and readable', () => {
  assert.equal(receiverChannelLabel({ channel_kind: 'dsc', frequency_hz: 2187500, mode: 'usb' }), 'DSC · 2187.5 kHz · USB');
  assert.equal(receiverChannelLabel({ channel_kind: 'monitor' }), 'Monitor');
});
