import test from 'node:test';
import assert from 'node:assert/strict';

import { apiUrl, fetchJson } from './client.js';

function browserWindow(token = '') {
  return {
    __SEACOMMONS_ACCESS_TOKEN__: token,
    setTimeout,
    clearTimeout,
  };
}

test('builds API URLs without duplicate boundary slashes', () => {
  assert.equal(apiUrl('https://api.example/', '/api/v1/live'), 'https://api.example/api/v1/live');
});

test('parses JSON and attaches the browser access token', async () => {
  const originalWindow = globalThis.window;
  const originalFetch = globalThis.fetch;
  globalThis.window = browserWindow('access-token');
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
  };
  try {
    const result = await fetchJson('https://api.example/', '/status');
    assert.deepEqual(result, { status: 'ok' });
    assert.equal(request.url, 'https://api.example/status');
    assert.equal(request.options.headers.Authorization, 'Bearer access-token');
    assert.ok(request.options.signal instanceof AbortSignal);
  } finally {
    globalThis.window = originalWindow;
    globalThis.fetch = originalFetch;
  }
});

test('does not expose an HTML proxy error as application JSON', async () => {
  const originalWindow = globalThis.window;
  const originalFetch = globalThis.fetch;
  globalThis.window = browserWindow();
  globalThis.fetch = async () => new Response('<html>cold start</html>', { status: 503 });
  try {
    await assert.rejects(
      fetchJson('https://api.example', '/api/v1/live'),
      /HTTP 503 — backend unavailable/,
    );
  } finally {
    globalThis.window = originalWindow;
    globalThis.fetch = originalFetch;
  }
});
