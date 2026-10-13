import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { selectUpstream, isFuturesPublicRequest } from '../../../api/proxy.js';

describe('Futures canonical production gateway', () => {
  it('never selects demo for Futures, even under a global demo override', () => {
    const old = process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST;
    try {
      process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST = 'demo-api.seacommons.org';
      assert.equal(selectUpstream({ host: 'futures.seacommons.org' }), 'api.seacommons.org');
    } finally {
      if (old === undefined) delete process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST;
      else process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST = old;
    }
  });

  it('only grants the partner host access to approved public-safe contracts', () => {
    for (const path of [
      '/api/v1/status?hours=24',
      '/api/v1/status?hours=168',
      '/api/v1/futures/overall',
      '/api/v1/play/counts',
      '/api/v1/live/pipeline',
      '/health',
    ]) {
      assert.equal(isFuturesPublicRequest({host:'futures.seacommons.org'},'GET',path),true,path);
    }
    for (const path of [
      '/api/v1/ops/data-status',
      '/api/v1/ops/summary',
      '/api/v1/ops/overall',
      '/api/v1/operator/ingestion/overall',
      '/api/v1/admin/users',
      '/api/v1/forensic',
    ]) {
      assert.equal(isFuturesPublicRequest({host:'futures.seacommons.org'},'GET',path),false,path);
    }
    assert.equal(isFuturesPublicRequest({host:'futures.seacommons.org'},'POST','/api/v1/status'),false);
  });
});
