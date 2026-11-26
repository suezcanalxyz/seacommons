import test from 'node:test';
import assert from 'node:assert/strict';
import handler from '../../../../../api/map-labels.js';

test('CARTO proxy classifies failures safely and retains authenticated success', async (t) => {
  const key = 'synthetic-test-key-not-real';
  const original = process.env.CARTO_BASEMAPS_API_KEY;
  const warnings = [];
  t.mock.method(console, 'warn', (...args) => warnings.push(args));
  const request = { method: 'GET', query: { style: 'dark_only_labels', z: '5', x: '17', y: '12' } };
  function response() {
    return { headers: {}, setHeader(k, v) { this.headers[k] = v; }, end(body) { this.body = body; } };
  }
  async function run(req = request) {
    const res = response();
    await handler(req, res);
    return res;
  }
  try {
    delete process.env.CARTO_BASEMAPS_API_KEY;
    let res = await run();
    assert.equal(res.statusCode, 503);
    assert.equal(res.headers['Cache-Control'], 'no-store');
    process.env.CARTO_BASEMAPS_API_KEY = key;
    const mock = t.mock.method(globalThis, 'fetch', async (url) => {
      assert.equal(url.searchParams.get('key'), key);
      return new Response('private provider error', { status: 403 });
    });
    res = await run();
    assert.equal(res.statusCode, 502);
    assert.equal(res.headers['Cache-Control'], 'no-store');
    await run();
    assert.equal(warnings.filter((a) => a[1].category === 'upstream_http').length, 1);
    assert.equal(warnings.find((a) => a[1].category === 'upstream_http')[1].upstreamStatus, 403);
    mock.mock.mockImplementation(async () => new Response('not a tile', { status: 200 }));
    assert.equal((await run()).statusCode, 502);
    mock.mock.mockImplementation(async () => { throw new DOMException(key, 'TimeoutError'); });
    assert.equal((await run()).statusCode, 502);
    mock.mock.mockImplementation(async () => { throw new Error(key); });
    assert.equal((await run()).statusCode, 502);
    assert.deepEqual(warnings.map((a) => a[1].category),
      ['missing_configuration', 'upstream_http', 'unexpected_content_type', 'upstream_timeout', 'upstream_transport']);
    assert.ok(!JSON.stringify(warnings).includes(key));
    assert.ok(!JSON.stringify(warnings).includes('private provider error'));
    mock.mock.mockImplementation(async () => new Response(new Uint8Array([1, 2, 3]),
      { headers: { 'content-type': 'image/png' } }));
    res = await run();
    assert.equal(res.statusCode, 200);
    assert.equal(res.headers['Content-Type'], 'image/png');
    assert.equal(res.headers['Cache-Control'], 'public, max-age=86400');
    assert.deepEqual([...res.body], [1, 2, 3]);
    assert.equal((await run({ ...request, query: { ...request.query, x: '99' } })).statusCode, 400);
  } finally {
    if (original === undefined) delete process.env.CARTO_BASEMAPS_API_KEY;
    else process.env.CARTO_BASEMAPS_API_KEY = original;
  }
});
