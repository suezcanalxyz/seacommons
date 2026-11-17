import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
test('public LIVE clock displays UTC and real source freshness independently', async () => {
  const source = await readFile(new URL('../../main.jsx', import.meta.url), 'utf8');
  assert.ok(source.includes('10_000 - (Date.now() % 10_000)'));
  assert.ok(source.includes('setLastDriftSyncAt(Date.now())'));
  assert.ok(source.includes('new Date(liveEstimateClock).toISOString().slice(11, 19)'));
  assert.ok(source.includes('Drift data awaiting first sync'));
  assert.ok(source.includes('Display estimate · 10s · source refresh 30s'));
  assert.ok(source.includes('if (!alive || inFlight) return'));
  assert.ok(source.includes("window.addEventListener('online', loadDrifts)"));
});
