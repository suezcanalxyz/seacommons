import { normalizeEnvironment, upstreamUrls } from './environment.js';
import { LiveRoom, liveRoomStub } from './live.js';

const CACHE_SECONDS = 600;
const STALE_SECONDS = 7_200;
const RADIO_LISTEN_PREFIX = '/v1/radio/listen/';
const DEFAULT_RADIO_LISTEN_UPSTREAM = 'http://152.70.182.58';

function corsHeaders(request, env) {
  const allowed = new Set(String(env.ALLOWED_ORIGINS || '').split(',').map((item) => item.trim()));
  const origin = request.headers.get('Origin') || '';
  return {
    'Access-Control-Allow-Origin': allowed.has(origin) ? origin : 'https://play.seacommons.org',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,X-SeaCommons-Signature',
    'Vary': 'Origin',
  };
}

export function radioListenOriginAllowed(origin, env) {
  if (!origin) return true;
  const allowed = new Set(String(env.ALLOWED_ORIGINS || '').split(',').map((item) => item.trim()).filter(Boolean));
  return allowed.has(origin);
}

export function radioListenUpstreamUrl(publicUrl, upstreamBase = DEFAULT_RADIO_LISTEN_UPSTREAM) {
  if (!publicUrl.pathname.startsWith(RADIO_LISTEN_PREFIX)) throw new Error('invalid radio listen path');
  const encodedId = publicUrl.pathname.slice(RADIO_LISTEN_PREFIX.length);
  const receiverId = decodeURIComponent(encodedId);
  if (!receiverId) throw new Error('receiver id is required');
  const upstream = new URL(upstreamBase);
  upstream.pathname = `/api/v1/live/radio/listen/${encodeURIComponent(receiverId)}`;
  upstream.search = '';
  upstream.hash = '';
  return upstream.toString();
}

async function radioListenResponse(request, env, url) {
  if (request.method !== 'GET' || String(request.headers.get('Upgrade') || '').toLowerCase() !== 'websocket') {
    return json({ error: 'websocket upgrade required' }, 426, corsHeaders(request, env));
  }
  if (!radioListenOriginAllowed(request.headers.get('Origin') || '', env)) {
    return json({ error: 'origin not allowed' }, 403, corsHeaders(request, env));
  }
  let upstreamUrl;
  try {
    upstreamUrl = radioListenUpstreamUrl(url, env.RADIO_LISTEN_UPSTREAM || DEFAULT_RADIO_LISTEN_UPSTREAM);
  } catch {
    return json({ error: 'invalid receiver id' }, 400, corsHeaders(request, env));
  }
  const headers = new Headers(request.headers);
  headers.delete('Host');
  return fetch(new Request(upstreamUrl, { method: 'GET', headers }));
}

function json(payload, status, headers = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...headers },
  });
}

function withCors(response, request, env) {
  const wrapped = new Response(response.body, response);
  Object.entries(corsHeaders(request, env)).forEach(([key, value]) => wrapped.headers.set(key, value));
  return wrapped;
}

async function fetchUpstream(url) {
  const response = await fetch(url, {
    headers: { 'User-Agent': 'SeaCommons-Edge/0.2 (+https://seacommons.org)' },
    cf: { cacheTtl: CACHE_SECONDS, cacheEverything: true },
  });
  if (!response.ok) throw new Error(`Environmental upstream HTTP ${response.status}`);
  return response.json();
}

async function environmentResponse(request, env, context, url) {
  const lat = Number(url.searchParams.get('lat'));
  const lon = Number(url.searchParams.get('lon'));
  if (!Number.isFinite(lat) || lat < -90 || lat > 90 || !Number.isFinite(lon) || lon < -180 || lon > 180) {
    return json({ error: 'lat/lon out of range' }, 400, corsHeaders(request, env));
  }
  const sampleLat = Number(lat.toFixed(2));
  const sampleLon = Number(lon.toFixed(2));
  const bucket = Math.floor(Date.now() / (CACHE_SECONDS * 1000));
  const cacheUrl = new URL('/_cache/environment', url.origin);
  cacheUrl.searchParams.set('lat', sampleLat.toFixed(2));
  cacheUrl.searchParams.set('lon', sampleLon.toFixed(2));
  cacheUrl.searchParams.set('bucket', String(bucket));
  const cacheKey = new Request(cacheUrl, { method: 'GET' });
  const cached = await caches.default.match(cacheKey);
  if (cached) {
    const response = new Response(cached.body, cached);
    response.headers.set('X-SeaCommons-Cache', 'hit');
    Object.entries(corsHeaders(request, env)).forEach(([key, value]) => response.headers.set(key, value));
    return response;
  }

  try {
    const urls = upstreamUrls(sampleLat, sampleLon);
    const [weather, marine] = await Promise.all([fetchUpstream(urls.weather), fetchUpstream(urls.marine)]);
    const payload = normalizeEnvironment(weather, marine);
    payload.requested_origin = { lat, lon };
    payload.sampled_origin = { lat: sampleLat, lon: sampleLon };
    const headers = {
      ...corsHeaders(request, env),
      'Cache-Control': `public, max-age=300, s-maxage=${STALE_SECONDS}, stale-while-revalidate=86400`,
      'X-SeaCommons-Cache': 'miss',
    };
    const response = json(payload, 200, headers);
    context.waitUntil(caches.default.put(cacheKey, response.clone()));
    return response;
  } catch (error) {
    const staleUrl = new URL(cacheUrl);
    staleUrl.searchParams.set('bucket', String(bucket - 1));
    const stale = await caches.default.match(new Request(staleUrl, { method: 'GET' }));
    if (stale) {
      const response = new Response(stale.body, stale);
      response.headers.set('Warning', '110 - stale environmental snapshot');
      response.headers.set('X-SeaCommons-Cache', 'stale');
      Object.entries(corsHeaders(request, env)).forEach(([key, value]) => response.headers.set(key, value));
      return response;
    }
    return json({ error: error instanceof Error ? error.message : 'Environmental gateway failed' }, 502, corsHeaders(request, env));
  }
}

export { LiveRoom };

export default {
  async fetch(request, env, context) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders(request, env) });

    if (url.pathname.startsWith(RADIO_LISTEN_PREFIX)) {
      return radioListenResponse(request, env, url);
    }

    if (url.pathname.startsWith('/v1/live/')) {
      if (!env.LIVE_ROOM) return json({ error: 'LIVE_ROOM binding is not configured' }, 503, corsHeaders(request, env));
      return withCors(await liveRoomStub(env).fetch(request), request, env);
    }

    if (request.method !== 'GET') return json({ error: 'method not allowed' }, 405, corsHeaders(request, env));
    if (url.pathname === '/health') {
      return json({ status: 'ok', service: 'seacommons-edge', simulation: 'client-worker', live: 'durable-object' }, 200, corsHeaders(request, env));
    }
    if (url.pathname === '/v1/environment') return environmentResponse(request, env, context, url);
    return json({ error: 'not found' }, 404, corsHeaders(request, env));
  },
};
