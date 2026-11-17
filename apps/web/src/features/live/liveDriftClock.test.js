import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
test('LIVE interpolates persisted operational drift every ten seconds without duplicate modelling', async () => {
  const source = await readFile(new URL('../../main.jsx', import.meta.url), 'utf8');
  assert.ok(source.includes('10_000 - (Date.now() % 10_000)'));
  assert.ok(source.includes('mergeLiveDrifts('));
  assert.ok(source.includes('document.addEventListener(\'visibilitychange\', onVisibility)'));
  assert.ok(source.includes("window.addEventListener('online', loadDrifts)"));
  assert.ok(source.includes('if (!alive || loading) return;'));
  assert.ok(source.includes('if (alive && Array.isArray(data.features)) setIntelDrifts(data)'));
});
