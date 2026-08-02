const MAX_EVENTS = 500;
const DEFAULT_TTL_SECONDS = 6 * 60 * 60;

function json(payload, status = 200, headers = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...headers },
  });
}

async function sha256Hex(value) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function hmacHex(secret, value) {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(value));
  return [...new Uint8Array(signature)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function timingSafeEqual(left, right) {
  if (left.length !== right.length) return false;
  let mismatch = 0;
  for (let index = 0; index < left.length; index += 1) {
    mismatch |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return mismatch === 0;
}

function ttlSeconds(env) {
  const parsed = Number(env.LIVE_EVENT_TTL_SECONDS || DEFAULT_TTL_SECONDS);
  return Number.isFinite(parsed) && parsed >= 60 ? parsed : DEFAULT_TTL_SECONDS;
}

function isFresh(event, env, now = Date.now()) {
  const expiresAt = Number(event.expires_at_ms || 0);
  if (expiresAt) return expiresAt > now;
  const received = Date.parse(event.received_at || event.observed_at || '');
  return Number.isFinite(received) && received + ttlSeconds(env) * 1000 > now;
}

export async function verifyIngestRequest(request, secret) {
  if (!secret) return { ok: false, status: 503, error: 'INGEST_SECRET is not configured' };
  const body = await request.text();
  const supplied = request.headers.get('X-SeaCommons-Signature') || '';
  const expected = await hmacHex(secret, body);
  if (!timingSafeEqual(supplied.toLowerCase(), expected)) {
    return { ok: false, status: 401, error: 'invalid event signature' };
  }
  try {
    return { ok: true, body, event: JSON.parse(body) };
  } catch {
    return { ok: false, status: 400, error: 'invalid JSON' };
  }
}

export async function normalizeEvent(input, previousHash = null, ttl = DEFAULT_TTL_SECONDS) {
  if (!input || typeof input !== 'object') throw new Error('event must be an object');
  if (!input.type || !input.source || !input.observed_at) {
    throw new Error('type, source and observed_at are required');
  }
  const receivedAt = new Date().toISOString();
  const event = {
    schema: 'seacommons-event-v1',
    type: String(input.type),
    source: String(input.source),
    node: String(input.node || 'unknown'),
    observed_at: new Date(input.observed_at).toISOString(),
    received_at: receivedAt,
    expires_at_ms: Date.parse(receivedAt) + ttl * 1000,
    visibility: input.visibility === 'private' ? 'private' : 'public',
    confidence: Number.isFinite(Number(input.confidence)) ? Number(input.confidence) : null,
    geometry: input.geometry || null,
    properties: input.properties && typeof input.properties === 'object' ? input.properties : {},
    source_url: input.source_url ? String(input.source_url) : null,
    previous_hash: previousHash,
  };
  event.id = input.id ? String(input.id) : await sha256Hex(JSON.stringify(event));
  event.hash = await sha256Hex(JSON.stringify(event));
  return event;
}

export class LiveRoom {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname.endsWith('/stream')) return this.stream(request);
    if (url.pathname.endsWith('/snapshot')) return this.snapshot();
    if (url.pathname.endsWith('/status')) return this.status();
    if (url.pathname.endsWith('/reset') && request.method === 'POST') return this.reset(request);
    if (url.pathname.endsWith('/events') && request.method === 'POST') return this.ingest(request);
    return json({ error: 'not found' }, 404);
  }

  async stream(request) {
    if (request.headers.get('Upgrade') !== 'websocket') {
      return json({ error: 'websocket upgrade required' }, 426);
    }
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    this.state.acceptWebSocket(server);
    server.send(JSON.stringify({ type: 'snapshot', ...(await this.loadSnapshot()) }));
    return new Response(null, { status: 101, webSocket: client });
  }

  async snapshot() {
    return json(await this.loadSnapshot(), 200, {
      'Cache-Control': 'no-store, max-age=0',
    });
  }

  async status() {
    const snapshot = await this.loadSnapshot();
    const ageSeconds = snapshot.updated_at
      ? Math.max(0, Math.round((Date.now() - Date.parse(snapshot.updated_at)) / 1000))
      : null;
    return json({
      status: ageSeconds !== null && ageSeconds <= 120 ? 'live' : 'waiting',
      updated_at: snapshot.updated_at,
      age_seconds: ageSeconds,
      event_count: snapshot.events.length,
      ttl_seconds: ttlSeconds(this.env),
      websocket_clients: this.state.getWebSockets().length,
    });
  }

  async reset(request) {
    const verified = await verifyIngestRequest(request, this.env.INGEST_SECRET);
    if (!verified.ok) return json({ error: verified.error }, verified.status);
    await this.state.storage.deleteAll();
    for (const socket of this.state.getWebSockets()) {
      try { socket.send(JSON.stringify({ type: 'reset', at: new Date().toISOString() })); } catch { socket.close(1011, 'reset broadcast failed'); }
    }
    return json({ reset: true, at: new Date().toISOString() }, 200);
  }

  async ingest(request) {
    const verified = await verifyIngestRequest(request, this.env.INGEST_SECRET);
    if (!verified.ok) return json({ error: verified.error }, verified.status);

    const previousHash = await this.state.storage.get('head_hash') || null;
    let event;
    try {
      event = await normalizeEvent(verified.event, previousHash, ttlSeconds(this.env));
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : 'invalid event' }, 400);
    }
    if (event.visibility !== 'public') return json({ error: 'private events are not accepted by public Live' }, 403);

    const seen = await this.state.storage.get(`event:${event.id}`);
    if (seen) return json({ accepted: true, duplicate: true, event_id: event.id }, 200);

    const existing = await this.state.storage.get('events') || [];
    const fresh = existing.filter((item) => isFresh(item, this.env));
    const targetId = String(event.properties?.incident_id || event.id);
    const withoutPreviousVersion = fresh.filter((item) => String(item.properties?.incident_id || item.id) !== targetId);
    const resolved = Boolean(event.properties?.resolved || event.properties?.archived || event.type === 'incident_resolved');
    const events = resolved ? withoutPreviousVersion : [...withoutPreviousVersion, event].slice(-MAX_EVENTS);

    await this.state.storage.put({
      events,
      head_hash: event.hash,
      updated_at: event.received_at,
      [`event:${event.id}`]: true,
    });

    const message = JSON.stringify({ type: resolved ? 'remove' : 'event', event, incident_id: targetId });
    for (const socket of this.state.getWebSockets()) {
      try { socket.send(message); } catch { socket.close(1011, 'broadcast failed'); }
    }

    if (this.env.NOSTR_BRIDGE_URL) {
      this.state.waitUntil(fetch(this.env.NOSTR_BRIDGE_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.env.NOSTR_BRIDGE_TOKEN ? { Authorization: `Bearer ${this.env.NOSTR_BRIDGE_TOKEN}` } : {}),
        },
        body: JSON.stringify(event),
      }).catch(() => undefined));
    }

    if (this.env.LIVE_SNAPSHOTS) {
      const snapshot = JSON.stringify(await this.loadSnapshot());
      this.state.waitUntil(this.env.LIVE_SNAPSHOTS.put('live/latest.json', snapshot, {
        httpMetadata: { contentType: 'application/json' },
      }));
    }

    return json({ accepted: true, removed: resolved, event_id: event.id, hash: event.hash }, 202);
  }

  async loadSnapshot() {
    const stored = await this.state.storage.get('events') || [];
    const events = stored.filter((event) => isFresh(event, this.env));
    if (events.length !== stored.length) await this.state.storage.put('events', events);
    return {
      schema: 'seacommons-live-snapshot-v1',
      mode: 'ephemeral-live',
      updated_at: await this.state.storage.get('updated_at') || null,
      head_hash: await this.state.storage.get('head_hash') || null,
      ttl_seconds: ttlSeconds(this.env),
      events,
    };
  }
}

export function liveRoomStub(env) {
  const id = env.LIVE_ROOM.idFromName('mediterranean-public-live');
  return env.LIVE_ROOM.get(id);
}
