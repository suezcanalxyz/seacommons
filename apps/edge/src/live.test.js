import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeEvent, verifyIngestRequest } from './live.js';

async function hmac(secret, body) {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body));
  return [...new Uint8Array(signature)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

test('normalizes a public event into the versioned append-only contract', async () => {
  const event = await normalizeEvent({
    type: 'distress_observation',
    source: 'alarm-phone',
    node: 'oracle-collector-1',
    observed_at: '2026-08-02T12:00:00Z',
    confidence: 0.7,
    geometry: { type: 'Point', coordinates: [14.5, 35.5] },
  }, 'previous');

  assert.equal(event.schema, 'seacommons-event-v1');
  assert.equal(event.previous_hash, 'previous');
  assert.equal(event.visibility, 'public');
  assert.match(event.id, /^[a-f0-9]{64}$/);
  assert.match(event.hash, /^[a-f0-9]{64}$/);
});

test('accepts a correctly signed collector request', async () => {
  const secret = 'test-secret';
  const body = JSON.stringify({ type: 'source_health', source: 'gdacs', observed_at: '2026-08-02T12:00:00Z' });
  const request = new Request('https://edge.example/v1/live/events', {
    method: 'POST',
    headers: { 'X-SeaCommons-Signature': await hmac(secret, body) },
    body,
  });
  const result = await verifyIngestRequest(request, secret);
  assert.equal(result.ok, true);
  assert.equal(result.event.source, 'gdacs');
});

test('rejects a collector request with an invalid signature', async () => {
  const request = new Request('https://edge.example/v1/live/events', {
    method: 'POST',
    headers: { 'X-SeaCommons-Signature': 'bad' },
    body: '{}',
  });
  const result = await verifyIngestRequest(request, 'test-secret');
  assert.equal(result.ok, false);
  assert.equal(result.status, 401);
});
