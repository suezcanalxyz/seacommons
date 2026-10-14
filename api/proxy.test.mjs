import test from 'node:test';
import assert from 'node:assert/strict';
import { selectUpstream, publicProxyCacheSeconds } from './proxy.js';

test('Futures partner API requests use the canonical operational backend', () => {
  assert.equal(selectUpstream({ host: 'futures.seacommons.org' }), 'api.seacommons.org');
  assert.equal(selectUpstream({ host: 'futures.seacommons.org:443' }), 'api.seacommons.org');
});

test('Live and Console continue using the canonical backend', () => {
  for (const host of ['live.seacommons.org', 'console.seacommons.org', 'api.seacommons.org']) {
    assert.equal(selectUpstream({ host }), 'api.seacommons.org');
  }
});

test('Other hosts retain the demo/backend isolation rule', () => {
  for (const host of ['seacommons.org', 'play.seacommons.org', 'unknown.example']) {
    assert.equal(selectUpstream({ host }), 'demo-api.seacommons.org');
  }
});

test('Futures never inherits a site-wide demo upstream override', () => {
  const original = process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST;
  try {
    process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST = 'demo-api.seacommons.org';
    assert.equal(selectUpstream({host:'futures.seacommons.org'}),'api.seacommons.org');
    assert.equal(selectUpstream({host:'seacommons.org'}),'demo-api.seacommons.org');
  } finally {
    if (original === undefined) delete process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST;
    else process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST = original;
  }
});

test('Public read caching is restricted by host and route', () => {
  const get = (host, path) => publicProxyCacheSeconds({ host }, 'GET', path);
  assert.equal(get('play.seacommons.org', '/api/v1/play/counts'), 45);
  assert.equal(get('play.seacommons.org', '/api/v1/play/incidents?limit=100&offset=0'), 30);
  assert.equal(get('live.seacommons.org', '/api/v1/live/pipeline'), 20);
  assert.equal(get('live.seacommons.org', '/api/v1/live/ngo-vessels'), 15);
  assert.equal(get('futures.seacommons.org', '/api/v1/play/counts'), 0);
  assert.equal(get('api.seacommons.org', '/api/v1/play/counts'), 0);
  assert.equal(get('play.seacommons.org', '/api/v1/operator/ingestion/overall'), 0);
  assert.equal(get('live.seacommons.org', '/api/v1/status'), 0);
  assert.equal(get('live.seacommons.org', '/api/v1/intel'), 0);
});

test('Authenticated, mutated and non-200 responses cannot use the public CDN cache', () => {
  const path = '/api/v1/play/counts';
  const host = 'play.seacommons.org';
  assert.equal(publicProxyCacheSeconds({ host, authorization: 'Bearer secret' }, 'GET', path), 0);
  assert.equal(publicProxyCacheSeconds({ host, cookie: 'session=secret' }, 'GET', path), 0);
  assert.equal(publicProxyCacheSeconds({ host, 'x-api-key': 'secret' }, 'GET', path), 0);
  assert.equal(publicProxyCacheSeconds({ host }, 'POST', path), 0);
  assert.equal(publicProxyCacheSeconds({ host }, 'GET', path, 401), 0);
  assert.equal(publicProxyCacheSeconds({ host }, 'GET', path, 502), 0);
  assert.equal(publicProxyCacheSeconds({ host }, 'GET', path, 200, { 'set-cookie': 'session=secret' }), 0);
  assert.equal(publicProxyCacheSeconds({ host }, 'GET', path, 200, { vary: 'Authorization, Accept-Encoding' }), 0);
  assert.equal(publicProxyCacheSeconds({ host }, 'GET', path, 200, { vary: '*' }), 0);
});
