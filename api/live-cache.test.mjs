import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeLiveMode, publicLiveCacheSeconds } from './live.js';

test('Only published Live projections have short positive TTLs', () => {
  assert.equal(publicLiveCacheSeconds('signals'), 15);
  assert.equal(publicLiveCacheSeconds('drifts'), 25);
  assert.equal(publicLiveCacheSeconds('sources'), 30);
  assert.equal(publicLiveCacheSeconds('archives'), 60);
  assert.equal(publicLiveCacheSeconds('archive'), 60);
  assert.equal(publicLiveCacheSeconds(undefined), 15);
  assert.equal(normalizeLiveMode('security'), 'maritime');
});

test('Authenticated Live requests are excluded from CDN caching', () => {
  assert.equal(publicLiveCacheSeconds('signals', { authorization: 'Bearer token' }), 0);
  assert.equal(publicLiveCacheSeconds('drifts', { cookie: 'session=x' }), 0);
  assert.equal(publicLiveCacheSeconds('sources', { 'x-api-key': 'token' }), 0);
});
