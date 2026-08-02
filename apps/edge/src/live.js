const MAX_EVENTS = 500;

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

export async function normalizeEvent(input, previousHash = null) {
  if (!input || typeof input !== 'object') throw new Error('event must be an object');
  if (!input.type || !input.source || !input.observed_at) {
    throw new Error('type, source and observed_at are required');
  }
  const event = {
    schema: 'seacommons-event-v1',
    type: String(input.type),
    source: String(input.source),
    node: String(input.node || 'unknown'),
    observed_at: new Date(input.observed_at).toISOString(),
    received_at: new Date().toISOString(),
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
    const snapshot = await this.loadSnapshot();
    server.send(JSON.stringify({ type: 'snapshot', ...snapshot }));
    return new Response(null, { status: 101, webSocket: client });
  }

  async snapshot() {
    return json(await this.loadSnapshot(), 200, {
      'Cache-Control': 'public, max-age=5, s-maxage=15, stale-while-revalidate=120',
    });
  }

  async ingest(request) {
    const verified = await verifyIngestRequest(request, this.env.INGEST_SECRET);
    if (!verified.ok) return json({ error: verified.error }, verified.status);

    const previousHash = await this.state.storage.get('head_hash') || null;
    let event;
    try {
      event = await normalizeEvent(verified.event, previousHash);
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : 'invalid event' }, 400);
    }
    if (event.visibility !== 'public') return json({ error: 'private events are not accepted by public Live' }, 403);

    const seen = await this.state.storage.get(`event:${event.id}`);
    if (seen) return json({ accepted: true, duplicate: true, event_id: event.id }, 200);

    const events = await this.state.storage.get('events') || [];
    events.push(event);
    const trimmed = events.slice(-MAX_EVENTS);
    await this.state.storage.put({
      events: trimmed,
      head_hash: event.hash,
      updated_at: event.received_at,
      [`event:${event.id}`]: true,
    });

    const message = JSON.stringify({ type: 'event', event });
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

    return json({ accepted: true, event_id: event.id, hash: event.hash }, 202);
  }

  async loadSnapshot() {
    return {
      schema: 'seacommons-live-snapshot-v1',
      updated_at: await this.state.storage.get('updated_at') || null,
      head_hash: await this.state.storage.get('head_hash') || null,
      events: await this.state.storage.get('events') || [],
    };
  }
}

export function liveRoomStub(env) {
  const id = env.LIVE_ROOM.idFromName('mediterranean-public-live');
  return env.LIVE_ROOM.get(id);
}
