import test from 'node:test';
import assert from 'node:assert/strict';
import { projectConnectedChannels } from './channels.js';

test('11-channel projection counts only distinct genuinely active and tuned SDR sessions', () => {
  const result = projectConnectedChannels({
    active: 3,
    receivers: [
      { receiver_id: 'catania', active: true, frequency_hz: 2187500 },
      { receiver_id: 'catania', active: true, frequency_hz: 2187500 },
      { receiver_id: 'zante', active: true, frequency_hz: 2187500 },
      { receiver_id: 'cagliari', active: false, frequency_hz: 8414500 },
      { receiver_id: 'barcelona', active: false, frequency_hz: null },
    ],
  });
  assert.equal(result.channels.length, 11);
  assert.equal(result.channels.find((row) => row.frequency_hz === 2187500).active_receivers, 2);
  assert.equal(result.channels.find((row) => row.frequency_hz === 8414500).active_receivers, 0);
  assert.equal(result.channels.find((row) => row.frequency_hz === 156525000).decoder_ready, false);
  assert.equal(result.source, 'seacommons_rf_mesh');
});

test('upstream unavailability must not become 11 fabricated zeroes', () => {
  assert.throws(() => projectConnectedChannels(null), /invalid RF receiver mesh/);
  assert.throws(() => projectConnectedChannels({ receivers: [] }), /invalid RF receiver mesh/);
});

test('Vercel route is first-match before catchall proxy in both config roots', async () => {
  const { readFileSync } = await import('node:fs');
  const { fileURLToPath } = await import('node:url');
  const { resolve, dirname } = await import('node:path');
  const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  for (const path of ['vercel.json', 'apps/web/vercel.json']) {
    const rewrites = JSON.parse(readFileSync(resolve(repositoryRoot, path), 'utf8')).rewrites;
    const entry = rewrites.findIndex((row) => row.source === '/api/v1/live/radio/channels');
    const fallback = rewrites.findIndex((row) => row.source === '/api/:path*');
    assert.ok(entry >= 0 && entry < fallback, path);
    assert.equal(rewrites[entry].destination, '/api/channels');
  }
});
