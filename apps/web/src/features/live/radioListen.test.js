import test from 'node:test';
import assert from 'node:assert/strict';

import { liveListenWebSocketUrl, pcm16leToFloat32 } from './radioListen.js';

test('listen websocket URL follows API origin and switches to ws protocol', () => {
  assert.equal(
    liveListenWebSocketUrl('https://api.seacommons.org', 'rx 1', { origin: 'https://live.seacommons.org' }),
    'wss://api.seacommons.org/api/v1/live/radio/listen/rx%201',
  );
  assert.equal(
    liveListenWebSocketUrl('', 'rx-2', { origin: 'http://localhost:5173' }),
    'ws://localhost:5173/api/v1/live/radio/listen/rx-2',
  );
});

test('PCM16 little-endian packets become normalized WebAudio samples', () => {
  const packet = Uint8Array.from([0x00, 0x80, 0x00, 0x00, 0xff, 0x7f]).buffer;
  const samples = pcm16leToFloat32(packet);
  assert.equal(samples.length, 3);
  assert.equal(samples[0], -1);
  assert.equal(samples[1], 0);
  assert.ok(samples[2] > 0.999 && samples[2] < 1);
});


test('listen websocket can target the Cloudflare edge relay in production', () => {
  assert.equal(
    liveListenWebSocketUrl(
      'https://seacommons-edge.seacommons.workers.dev',
      'rx-edge',
      { origin: 'https://live.seacommons.org' },
      '/v1/radio/listen',
    ),
    'wss://seacommons-edge.seacommons.workers.dev/v1/radio/listen/rx-edge',
  );
});
