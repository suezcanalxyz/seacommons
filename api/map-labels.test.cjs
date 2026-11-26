const { test } = require('node:test');
const assert = require('node:assert/strict');
const handler = require('./map-labels.js');

test('map labels proxy regression', async (t) => {
  const originalFetch = global.fetch;
  const originalKey = process.env.CARTO_BASEMAPS_API_KEY;
  const originalWarn = console.warn;
  const warnings = [];
  console.warn = (...args) => warnings.push(args);
  t.after(() => {
    global.fetch = originalFetch;
    console.warn = originalWarn;
    if (originalKey === undefined) delete process.env.CARTO_BASEMAPS_API_KEY;
    else process.env.CARTO_BASEMAPS_API_KEY = originalKey;
  });
  const query = { style: 'dark_only_labels', z: '3', x: '4', y: '3' };
  async function request(overrides = {}) {
    const headers = {};
    const res = { setHeader(k,v) { headers[k] = v; }, end(body) { this.body = body; } };
    await handler({ method: 'GET', query, ...overrides }, res);
    return { ...res, headers };
  }
  delete process.env.CARTO_BASEMAPS_API_KEY;
  global.fetch = async () => assert.fail('unexpected upstream request');
  assert.equal((await request({method:'POST'})).statusCode, 405);
  assert.equal((await request({query:{...query,x:'8'}})).statusCode, 400);
  const missing = await request();
  assert.equal(missing.statusCode, 503);
  assert.equal(missing.headers['Cache-Control'], 'no-store');
  process.env.CARTO_BASEMAPS_API_KEY = 'test-secret-not-real';
  for (const [status,type] of [[403,'text/html'],[200,'text/html']]) {
    global.fetch = async () => new Response('error', {status,headers:{'content-type':type}});
    const result = await request();
    assert.equal(result.statusCode, 502);
    assert.equal(result.headers['Cache-Control'], 'no-store');
  }
  global.fetch = async () => { throw new Error('test-secret-not-real'); };
  assert.equal((await request()).headers['Cache-Control'], 'no-store');
  global.fetch = async (url, options) => {
    assert.equal(url.hostname, 'basemaps.cartocdn.com');
    assert.equal(url.searchParams.get('key'), 'test-secret-not-real');
    assert.equal(options.redirect, 'error');
    return new Response(Uint8Array.from([137,80,78,71]), {headers:{'content-type':'image/png'}});
  };
  const ok = await request();
  assert.equal(ok.statusCode, 200);
  assert.equal(ok.headers['Content-Type'], 'image/png');
  assert.equal(ok.headers['Cache-Control'], 'public, max-age=86400');
  assert.equal(JSON.stringify(warnings).includes('test-secret-not-real'), false);
});
