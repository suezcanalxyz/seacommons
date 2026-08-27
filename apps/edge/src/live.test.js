import test from 'node:test';
import assert from 'node:assert/strict';
import { INCIDENT_LIFECYCLES, LOCATION_PRECISIONS } from './live-contracts.js';
import { classifyLiveStatus, normalizeEvent, verifyIngestRequest } from './live.js';

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

test('normalizes a public event with an explicit live expiry', async () => {
  const before = Date.now();
  const event = await normalizeEvent({
    type: 'distress_observation',
    source: 'alarm-phone',
    node: 'oracle-collector-1',
    observed_at: '2026-08-02T12:00:00Z',
    confidence: 0.7,
    geometry: { type: 'Point', coordinates: [14.5, 35.5] },
  }, 'previous', 3600);

  assert.equal(event.schema, 'seacommons-event-v1');
  assert.equal(event.previous_hash, 'previous');
  assert.equal(event.visibility, 'public');
  assert.match(event.id, /^[a-f0-9]{64}$/);
  assert.match(event.hash, /^[a-f0-9]{64}$/);
  assert.ok(event.expires_at_ms >= before + 3_599_000);
});

test('exports the canonical lifecycle and precision vocabulary', () => {
  assert.deepEqual(INCIDENT_LIFECYCLES, ['active', 'resolved', 'needs_review', 'archived']);
  assert.deepEqual(LOCATION_PRECISIONS, [
    'unpositioned',
    'approximate',
    'regional_centroid',
    'reported_or_derived',
    'area',
    'area_low_confidence',
  ]);
});

test('rejects values outside the canonical Live vocabulary', async () => {
  const base = {
    type: 'distress_observation',
    source: 'alarm-phone',
    observed_at: '2026-08-02T12:00:00Z',
  };

  await assert.rejects(
    normalizeEvent({ ...base, confidence: 1.2 }),
    /confidence must be between 0 and 1/,
  );
  await assert.rejects(
    normalizeEvent({ ...base, properties: { incident_lifecycle: 'closed' } }),
    /invalid incident_lifecycle/,
  );
  await assert.rejects(
    normalizeEvent({ ...base, geometry: { type: 'LineString', coordinates: [] } }),
    /geometry type must be/,
  );
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

test('separates collector heartbeat health from event recency', () => {
  const now = Date.parse('2026-08-24T12:00:00Z');
  assert.equal(classifyLiveStatus({
    lastHeartbeatAt: '2026-08-24T11:59:20Z',
    eventCount: 0,
  }, now), 'live');
  assert.equal(classifyLiveStatus({
    lastHeartbeatAt: '2026-08-24T11:40:00Z',
    eventCount: 4,
  }, now), 'degraded');
  assert.equal(classifyLiveStatus({}, now), 'waiting');
});
