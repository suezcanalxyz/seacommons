import test from 'node:test';
import assert from 'node:assert/strict';

import { liveListenHttpUrl, liveListenWebSocketUrl, pcm16leToFloat32 } from './radioListen.js';

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


test('listen HTTP stream stays on the API/VM path instead of Cloudflare', () => {
  assert.equal(
    liveListenHttpUrl('', 'rx-vm', { origin: 'https://live.seacommons.org' }),
    'https://live.seacommons.org/api/v1/live/radio/listen/rx-vm',
  );
  assert.equal(
    liveListenHttpUrl('https://console.seacommons.org', 'rx 2', { origin: 'https://live.seacommons.org' }),
    'https://console.seacommons.org/api/v1/live/radio/listen/rx%202',
  );
});
