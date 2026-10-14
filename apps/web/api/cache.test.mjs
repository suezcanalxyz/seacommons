import test from 'node:test';
import assert from 'node:assert/strict';

import { publicProxyCacheSeconds, selectUpstream } from './proxy.js';
import { publicLiveCacheSeconds } from './live.js';

test('deployed Vercel handlers cache public anonymous reads only', () => {
  assert.equal(publicLiveCacheSeconds('signals'), 15);
  assert.equal(publicLiveCacheSeconds('drifts'), 25);
  assert.equal(publicLiveCacheSeconds('signals', { cookie: 'session=secret' }), 0);
  assert.equal(publicProxyCacheSeconds({ host: 'play.seacommons.org' }, 'GET', '/api/v1/play/counts'), 45);
  assert.equal(publicProxyCacheSeconds({ host: 'live.seacommons.org' }, 'GET', '/api/v1/live/pipeline'), 20);
  assert.equal(publicProxyCacheSeconds({ host: 'futures.seacommons.org' }, 'GET', '/api/v1/play/counts'), 0);
  assert.equal(publicProxyCacheSeconds({ host: 'play.seacommons.org' }, 'GET', '/api/v1/operator/ingestion/overall'), 0);
  assert.equal(publicProxyCacheSeconds({ host: 'play.seacommons.org', authorization: 'Bearer x' }, 'GET', '/api/v1/play/counts'), 0);
  assert.equal(publicProxyCacheSeconds({ host: 'play.seacommons.org' }, 'POST', '/api/v1/play/counts'), 0);
  assert.equal(publicProxyCacheSeconds({ host: 'play.seacommons.org' }, 'GET', '/api/v1/play/counts', 503), 0);
});

test('Futures cannot inherit a demo origin from Vercel environment', () => {
  const original = process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST;
  try {
    process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST = 'demo-api.seacommons.org';
    assert.equal(selectUpstream({ host: 'futures.seacommons.org' }), 'api.seacommons.org');
  } finally {
    if (original === undefined) delete process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST;
    else process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST = original;
  }
});
