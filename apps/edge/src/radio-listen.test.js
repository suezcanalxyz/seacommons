import test from 'node:test';
import assert from 'node:assert/strict';

import { radioListenOriginAllowed, radioListenUpstreamUrl } from './index.js';

test('radio listen relay maps the public edge route to the bounded API websocket', () => {
  const publicUrl = new URL('https://edge.example/v1/radio/listen/rx%2Falpha');
  assert.equal(
    radioListenUpstreamUrl(publicUrl, 'http://152.70.182.58'),
    'http://152.70.182.58/api/v1/live/radio/listen/rx%2Falpha',
  );
});

test('radio listen relay accepts only configured browser origins', () => {
  const env = { ALLOWED_ORIGINS: 'https://live.seacommons.org,https://play.seacommons.org' };
  assert.equal(radioListenOriginAllowed('https://live.seacommons.org', env), true);
  assert.equal(radioListenOriginAllowed('https://attacker.example', env), false);
  assert.equal(radioListenOriginAllowed('', env), true);
});
