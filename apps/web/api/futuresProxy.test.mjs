import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { isFuturesAllowedRequest, requestHeaders, selectUpstream } from './proxy.js';

const futures = { host: 'futures.seacommons.org' };

describe('Futures production proxy security boundary', () => {
  it('pins partner origin to the canonical operational API', () => {
    const original = process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST;
    process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST = 'demo-api.seacommons.org';
    try {
      assert.equal(selectUpstream(futures), 'api.seacommons.org');
    } finally {
      if (original === undefined) delete process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST;
      else process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST = original;
    }
  });

  it('permits only known public, read-only evidence contracts anonymously', () => {
    for (const path of [
      '/health', '/ready', '/api/v1/status?hours=24',
      '/api/v1/status?hours=168', '/api/v1/futures/overall', '/api/v1/futures/intelligence-overall',
      '/api/v1/play/counts', '/api/v1/live/pipeline',
    ]) {
      assert.equal(isFuturesAllowedRequest(futures, 'GET', path), true, path);
      assert.equal(isFuturesAllowedRequest(futures, 'HEAD', path), true, path);
    }
    for (const path of [
      '/api/v1/ops/summary', '/api/v1/ops/stats',
      '/api/v1/operator/ingestion/overall', '/api/v1/admin/users',
      '/api/v1/forensic', '/docs', '/openapi.json',
    ]) assert.equal(isFuturesAllowedRequest(futures, 'GET', path), false, path);
    assert.equal(isFuturesAllowedRequest(futures, 'POST', '/api/v1/status'), false);
    assert.equal(isFuturesAllowedRequest(futures, 'POST', '/api/v1/futures/intelligence-overall'), false);
  });

  it('allows OIDC-bearing Intelligence reads without bypassing backend identity verification', () => {
    const signed = { ...futures, authorization: 'Bearer signed.id.token' };
    assert.equal(isFuturesAllowedRequest(signed, 'GET', '/api/v1/operator/ingestion/overview?hours=168'), true);
    assert.equal(isFuturesAllowedRequest(signed, 'GET', '/api/v1/operator/ingestion/scheduled-tasks'), true);
    assert.equal(isFuturesAllowedRequest(signed, 'GET', '/api/v1/ops/summary'), false);
    assert.equal(isFuturesAllowedRequest(signed, 'POST', '/api/v1/operator/ingestion/overview'), false);
    assert.equal(isFuturesAllowedRequest({ ...futures, authorization: 'Basic abc' }, 'GET', '/api/v1/operator/ingestion/overall'), false);
    assert.equal(isFuturesAllowedRequest({ ...futures, authorization: 'Bearer ' }, 'GET', '/api/v1/operator/ingestion/overall'), false);
  });

  it('allows only signed AIS review reads, single-vessel lookup and human review writes', () => {
    const signed = {...futures, authorization: 'Bearer signed.id.token'};
    const paths = ['/api/v1/operator/ais-reviews',
      '/api/v1/operator/ais-reviews/lookup?imo=9316359'];
    for (const path of paths) {
      assert.equal(isFuturesAllowedRequest(signed, 'GET', path), true, path);
      assert.equal(isFuturesAllowedRequest(futures, 'GET', path), false, path);
    }
    assert.equal(isFuturesAllowedRequest(signed, 'POST', '/api/v1/operator/ais-reviews'), true);
    assert.equal(isFuturesAllowedRequest(futures, 'POST', '/api/v1/operator/ais-reviews'), false);
    assert.equal(isFuturesAllowedRequest(signed, 'POST', '/api/v1/operator/ais-reviews/lookup'), false);
    assert.equal(isFuturesAllowedRequest(signed, 'POST', '/api/v1/operator/ingestion/overall'), false);
    assert.equal(isFuturesAllowedRequest(signed, 'GET', '/api/v1/vessels/search?q=9316359'), false);
    assert.equal(isFuturesAllowedRequest(signed, 'GET', '/api/v1/operator/ais-reviews/..%2fadmin'), false);
  });

  it('rejects encoded and ambiguous paths rather than relying on upstream normalization', () => {
    const signed = { ...futures, authorization: 'Bearer signed.id.token' };
    for (const path of [
      '/api/v1/status/../ops/summary',
      '/api/v1/operator/ingestion/../../ops/stats',
      '/api/v1/operator/ingestion/%2e%2e/ops/summary',
      '/api/v1/operator/ingestion/%2fops',
      '/api/v1/operator/ingestion//overview',
      '/api/v1/operator/ingestion/..\\ops',
    ]) assert.equal(isFuturesAllowedRequest(signed, 'GET', path), false, path);
  });

  it('strips caller-supplied gateways and never injects an internal secret for Futures', () => {
    const previous = process.env.SEACOMMONS_INTERNAL_PROXY_SECRET;
    process.env.SEACOMMONS_INTERNAL_PROXY_SECRET = 'server-internal-secret';
    try {
      const incoming = {
        ...futures,
        authorization: 'Bearer identity-token',
        cookie: 'private=must-not-forward',
        'x-seacommons-internal': 'spoofed',
        'x-seacommons-operator-gateway': 'spoofed',
      };
      const partner = requestHeaders(incoming, 'api.seacommons.org', true);
      assert.equal(partner.authorization, 'Bearer identity-token');
      assert.equal(partner.cookie, undefined);
      assert.equal(partner['x-seacommons-internal'], undefined);
      assert.equal(partner['x-seacommons-operator-gateway'], undefined);
      const operational = requestHeaders({host: 'live.seacommons.org'}, 'api.seacommons.org', false);
      assert.equal(operational['x-seacommons-internal'], 'server-internal-secret');
    } finally {
      if (previous === undefined) delete process.env.SEACOMMONS_INTERNAL_PROXY_SECRET;
      else process.env.SEACOMMONS_INTERNAL_PROXY_SECRET = previous;
    }
  });
});
