import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const edgeSource = fs.readFileSync(new URL('./index.js', import.meta.url), 'utf8');
const wranglerConfig = fs.readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8');

test('radio listen is not routed through the Cloudflare worker', () => {
  assert.doesNotMatch(edgeSource, /RADIO_LISTEN|radioListen|\/v1\/radio\/listen/);
});

test('Cloudflare config has no radio listen upstream', () => {
  assert.doesNotMatch(wranglerConfig, /RADIO_LISTEN_UPSTREAM/);
});
