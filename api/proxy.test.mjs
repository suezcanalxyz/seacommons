import test from 'node:test';
import assert from 'node:assert/strict';
import { selectUpstream } from './proxy.js';

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
